class Game {
  constructor(manifest, canvas) {
    this.manifest = manifest;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.sm = new ScalingManager();
    this.audio = new AudioEngine(manifest);
    this.theme = new Theme(manifest);
    // Skin dei menu (overlay DOM/CSS pluggabile per-tema). Fallback: rendering canvas.
    this.menuSkin = (typeof makeMenuSkin === "function") ? makeMenuSkin(this) : null;
    this.save = Save.load(manifest.game_id);
    // Costanti di gioco: fonte unica = engine (manifest.rules), fallback ai default.
    this.R = Object.assign({}, RULES_DEFAULTS, manifest.rules || {});
    // Poster del menu (fallback/preview del video di sfondo)
    if (manifest.menu_poster) {
      this._menuPosterImg = new Image();
      this._menuPosterImg.onload = () => { if (this.state === "LEVEL_SELECT") this.invalidate(); };
      this._menuPosterImg.src = manifest._base + manifest.menu_poster;
    }
    this.state = "START";
    const urlParams = new URLSearchParams(window.location.search);
    const mgParam = urlParams.get("minigame");
    if (mgParam && MINIGAME_CLASSES[mgParam]) {
      // Avvio ritardato per far completare l'inizializzazione del canvas e del resizing
      setTimeout(() => this._launchMinigame(mgParam, null), 50);
    }

    // Impostazioni persistite (lingua + volumi)
    const settings = this._loadSettings();
    this.lang = settings.lang || manifest.default_language || "it";
    this.audio.musicVol = settings.musicVol != null ? settings.musicVol : 0.6;
    this.audio.sfxVol = settings.sfxVol != null ? settings.sfxVol : 0.8;
    this._prevState = "LEVEL_SELECT"; // per tornare dopo le impostazioni

    // Scena attiva
    this.level = null;
    this.sceneDef = null;
    this.objects = [];
    this.bgImg = null;
    this.timeLeft = 0;
    this.timeTotal = 0;
    this.score = 0;
    this.lastTs = 0;
    this.feedback = null; // {x,y,t, ok}

    this._renderScheduled = false;
    this._bindEvents();
    this._resize();

    // Timer a bassa frequenza: aggiorna il countdown senza un loop rAF continuo.
    // Intervallo fisso 200ms; decrementa solo in SCENE (la pausa congela il tempo).
    setInterval(() => {
      if (this.state !== "SCENE") return;
      this.timeLeft -= 0.2;
      if (this.timeLeft <= 0) { this.timeLeft = 0; this._completeScene(); }
      this.invalidate();
    }, 200);
  }

  // Render-on-demand: programma un singolo frame. La pagina resta idle quando
  // nulla cambia (necessario per screenshot headless e per risparmio CPU).
  invalidate() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame((t) => this._frame(t));
  }

  t(key, fallback) {
    const tbl = (this.manifest.strings && this.manifest.strings[this.lang]) || {};
    if (tbl[key] != null) return tbl[key];
    const ui = UI_STRINGS[this.lang] && UI_STRINGS[this.lang][key];
    if (ui != null) return ui;
    if (UI_STRINGS.en[key] != null) return UI_STRINGS.en[key];
    return fallback != null ? fallback : key;
  }

  // ── Loading screen (overlay DOM #loader) ─────────────────────────────────
  _loader() { return document.getElementById("loader"); }
  _showLoader() { const el = this._loader(); if (el) el.classList.remove("hidden"); this._setLoaderProgress(0); }
  _hideLoader() { const el = this._loader(); if (el) el.classList.add("hidden"); }
  _setLoaderProgress(p) {
    const f = document.getElementById("loader-fill");
    if (f) f.style.width = Math.round(Math.max(0, Math.min(1, p)) * 100) + "%";
  }

  // ── Transizione fade-from-black tra stati ────────────────────────────────
  _beginFade() { this._fadeUntil = performance.now() + FADE_MS; this.invalidate(); }

  _loadSettings() {
    try { return JSON.parse(localStorage.getItem("hie_settings") || "{}"); } catch (e) { return {}; }
  }
  _saveSettings() {
    try {
      localStorage.setItem("hie_settings", JSON.stringify({
        lang: this.lang, musicVol: this.audio.musicVol, sfxVol: this.audio.sfxVol,
      }));
    } catch (e) {}
  }

  _bindEvents() {
    window.addEventListener("resize", () => this._resize());
    this.canvas.addEventListener("pointerdown", (e) => this._onPointer(e));
    // Posizione puntatore per la torcia (flashlight)
    this.ptrX = -1; this.ptrY = -1;
    this.canvas.addEventListener("pointermove", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.ptrX = e.clientX - rect.left;
      this.ptrY = e.clientY - rect.top;
      if (this.state === "LEVEL_SELECT" ||
          (this.state === "SCENE" && this.sceneDef && this.sceneDef.flashlight)) this.invalidate();
    });
    // Rilascio puntatore: per i controlli touch "tieni premuto" dei minigiochi
    this.canvas.addEventListener("pointerup", (e) => {
      if (this.state === "MINIGAME" && this.minigame && this.minigame.pointer) {
        const rect = this.canvas.getBoundingClientRect();
        this.minigame.pointer(e.clientX - rect.left, e.clientY - rect.top, "up");
      }
    });
    // Tastiera: instradata al minigioco attivo
    window.addEventListener("keydown", (e) => {
      if (this.state === "MINIGAME" && this.minigame) {
        this.minigame.key(e, true);
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(e.key)) e.preventDefault();
      }
    });
    window.addEventListener("keyup", (e) => {
      if (this.state === "MINIGAME" && this.minigame) this.minigame.key(e, false);
    });
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.sm.updateScreenSize(w, h);
    if (this.sceneDef) this.sm.setBackground(this.sceneDef.bg_w, this.sceneDef.bg_h, this.sceneDef.background_scale);
    this.invalidate();
  }

  // ── Avvio scena ──────────────────────────────────────────────────────────
  async startScene(level, sceneDef) {
    this.level = level;
    this.sceneDef = sceneDef;
    this.score = 0;
    this.timeTotal = sceneDef.time_limit || 120;
    this.timeLeft = this.timeTotal;

    // Stato hint per la scena
    this.hintsAvailable = this.R.hint_free;
    this.hintsUsedTotal = 0;
    this.progressToNextHint = 0;
    this.earnedHintsThisScene = 0;
    this.hintReadyAt = 0;          // performance.now() in cui finisce il cooldown
    this.hintGlowUntil = 0;        // glow manuale attivo fino a questo ts
    this.hintTarget = null;        // oggetto evidenziato dall'hint manuale
    this.lastFindAt = performance.now(); // per l'auto-glow da inattivita

    // Stato penalita' miss progressiva (parita' engine.level_manager.register_miss):
    // miss entro miss_combo_window secondi l'uno dall'altro escalano la penalita'.
    this._consecutiveMisses = 0;
    this._lastMissAt = 0;

    this.sm.updateScreenSize(this.canvas.clientWidth, this.canvas.clientHeight);
    this.sm.setBackground(sceneDef.bg_w, sceneDef.bg_h, sceneDef.background_scale);

    // Effetti ambientali (clona con accumulatore tempo per-effetto)
    this.effects = (sceneDef.effects || []).map(e => Object.assign({ _t: 0 }, e));
    this.fxTime = 0;
    this._fxTs = performance.now();

    // Torcia: hint-flash che illumina tutto temporaneamente
    this.hintFlashUntil = 0;
    if (this.ptrX < 0) { this.ptrX = this.canvas.clientWidth / 2; this.ptrY = this.canvas.clientHeight / 2; }

    // Fumetti: coda. A inizio scena mostra quelli con trigger start_scene.
    this.bubbleQueue = [];
    this.activeBubble = null;
    this._bubblesDoneCb = null;
    this._completing = false;
    this.popups = [];
    this.findParticles = [];
    this.shake = 0;
    this._showBubbles((sceneDef.bubble_tips || []).filter(b => b.trigger === "start_scene"), null);

    // Costruzione oggetti con selezione casuale (replica engine/scene_loader.py).
    // Avviene ad OGNI avvio scena, quindi la scena cambia ad ogni partita.
    this.objects = this._buildSceneObjects(sceneDef)
      .sort((a, b) => a.layer_z - b.layer_z);

    // Caricamento asset con loading screen + progress.
    this._showLoader();
    const withIcon = this.objects.filter(o => o.icon);
    let loaded = 0;
    const total = withIcon.length + 1; // +1 per lo sfondo
    const tick = () => this._setLoaderProgress(++loaded / total);

    // Sfondo: immagine o video. Per il video usiamo un elemento <video> in loop.
    this._pauseInactiveVideos(sceneDef.bg_is_video ? sceneDef.background : null);
    if (sceneDef.bg_is_video) {
      this.bgImg = null;
      this.bgVideo = this._getVideo(sceneDef.background);
    } else {
      this.bgVideo = null;
      this.bgImg = await loadImage(this.manifest._base + sceneDef.background);
    }
    tick();
    await Promise.all(this.objects.map(async (o) => {
      o._img = o.icon ? await loadImage(this.manifest._base + o.icon) : null;
      if (o.icon) tick();
    }));

    this.state = "SCENE";
    this.lastTs = performance.now();
    this.audio.playMusic(sceneDef.music);
    this._hideLoader();
    this._beginFade();
    this.invalidate();
  }

  // Replica _load_scene_internal (random_layer_selection) + _select_objects
  // (auto_random_finds): scelta del layer e degli obiettivi casuale ad ogni avvio.
  _buildSceneObjects(sceneDef) {
    let raw = sceneDef.objects;

    // 1. Random Layer Mode: mantiene un solo layer principale a caso (+ layer non "objects_")
    if (sceneDef.random_layer_selection) {
      const chosen = ["objects_low", "objects_mid", "objects_high"][Math.floor(Math.random() * 3)];
      const filtered = raw.filter(o => {
        const ly = o.layer || "objects_mid";
        return ly === chosen || !ly.startsWith("objects_");
      });
      if (filtered.length) raw = filtered; // guardia: non svuotare la scena
    }

    const objs = raw.map(o => Object.assign({ found: false, _img: null }, o));

    // 2. Auto Random Finds: ridisegna gli obiettivi (is_goal) casualmente
    if (sceneDef.auto_random_finds) {
      const numGoals = sceneDef.num_random_finds != null ? sceneDef.num_random_finds : objs.length;
      objs.forEach(o => { o.is_goal = false; });
      const fixed = objs.filter(o => o.always_show);
      const pool = objs.filter(o => !o.always_show);
      const finalGoals = fixed.slice(0, numGoals);
      finalGoals.forEach(o => { o.is_goal = true; });
      let remaining = numGoals - finalGoals.length;
      if (remaining > 0 && pool.length) {
        // Fisher-Yates shuffle
        for (let i = pool.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [pool[i], pool[j]] = [pool[j], pool[i]];
        }
        pool.slice(0, remaining).forEach(o => { o.is_goal = true; });
      }
    }
    return objs;
  }

  get goals() { return this.objects.filter(o => o.is_goal); }

  // Mostra una sequenza di fumetti; a coda esaurita esegue cb (puo' essere null).
  _showBubbles(list, cb) {
    this.bubbleQueue = (list || []).map(b => Object.assign({ _chars: 0, _ts: performance.now() }, b));
    this._bubblesDoneCb = cb || null;
    this.activeBubble = this.bubbleQueue.length ? this.bubbleQueue[0] : null;
    if (!this.activeBubble && cb) cb();
    this.invalidate();
  }
  _closeBubble() {
    this.bubbleQueue.shift();
    if (this.bubbleQueue.length) {
      this.activeBubble = this.bubbleQueue[0];
      this.activeBubble._ts = performance.now();
    } else {
      this.activeBubble = null;
      const cb = this._bubblesDoneCb;
      this._bubblesDoneCb = null;
      if (cb) cb();
    }
    this.invalidate();
  }

  _onPointer(e) {
    const rect = this.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    this.audio.unlock(); // primo gesto: sblocca l'audio (autoplay policy)

    if (this.state === "START") {
      this.state = "LEVEL_SELECT";
      this.audio.sfx("click");
      this.audio.playMusic(this.manifest.menu_music);
      this._beginFade();
      return;
    }
    if (this.state === "LEVEL_SELECT") return this._clickMenu(sx, sy);
    if (this.state === "RESULTS") return this._clickResults(sx, sy);
    if (this.state === "SETTINGS") return this._clickSettings(sx, sy);
    if (this.state === "PAUSE") return this._clickPause(sx, sy);
    if (this.state === "MINIGAME") { if (this.minigame) this.minigame.pointer(sx, sy, "down"); return; }
    if (this.state !== "SCENE") return;

    // Un fumetto aperto consuma i click finche' non viene chiuso (replica engine).
    if (this.activeBubble) {
      if (this._bubbleCloseBtn && this._inRect(sx, sy, this._bubbleCloseBtn)) {
        this.audio.sfx("click");
        this._closeBubble();
      }
      return;
    }

    // Pulsanti UI (precedenza sul click di gioco)
    if (this._pauseBtn && this._inRect(sx, sy, this._pauseBtn)) {
      this.audio.sfx("click");
      this._togglePause();
      return;
    }
    if (this._hintBtn && this._inRect(sx, sy, this._hintBtn)) {
      this._useHint();
      return;
    }

    const [bx, by] = this.sm.screenToBg(sx, sy);
    const candidates = this.objects.filter(o =>
      !o.found &&
      (o.is_goal || o.minigame_trigger) &&
      o.layer !== "overlay" &&
      hitTest(o, bx, by)
    );
    candidates.sort((a, b) => b.layer_z - a.layer_z);

    if (candidates.length) {
      const hit = candidates[0];
      // Oggetto con minigioco: lancia il minigioco invece di segnarlo trovato.
      if (hit.minigame_trigger && hit.minigame_trigger.minigame_id &&
          (this.manifest.minigames || []).includes(hit.minigame_trigger.minigame_id)) {
        this._launchMinigame(hit.minigame_trigger.minigame_id, hit);
        return;
      }
      hit.found = true;
      this.score += this.R.points_per_object;
      this.feedback = { x: sx, y: sy, t: performance.now(), ok: true };
      this._spawnPopup(sx, sy, "+" + this.R.points_per_object, "#5dff8f");
      this._spawnBurst(sx, sy, "#ffe87a");
      this.lastFindAt = performance.now();
      this._awardHintProgress();
      const allFound = this.goals.every(o => o.found);
      this.audio.sfx(allFound ? "complete" : "found");
      if (allFound) { this.shake = 16; this._completeScene(); }
    } else {
      this.audio.sfx("miss");
      // Penalita' PROGRESSIVA sui miss consecutivi (parita' engine.register_miss):
      // miss entro miss_combo_window secondi escalano lungo miss_penalty_curve.
      const now = performance.now();
      if (now - this._lastMissAt < this.R.miss_combo_window * 1000) this._consecutiveMisses++;
      else this._consecutiveMisses = 1;
      this._lastMissAt = now;
      const penalty = this._missPenalty(this._consecutiveMisses);
      this.score -= penalty;  // NIENTE floor: il punteggio puo' andare negativo, come l'engine
      this.timeLeft = Math.max(0, this.timeLeft - this.R.miss_time_penalty);
      this.feedback = { x: sx, y: sy, t: performance.now(), ok: false };
      this._spawnPopup(sx, sy, "-" + penalty, "#ff6b6b");
    }
    this.invalidate();
  }

  // Completamento scena: se completata con fumetti end_scene, mostrali prima dei results.
  _completeScene() {
    if (this._completing) return;
    this._completing = true;
    const allFound = this.goals.every(o => o.found);
    const endBubbles = allFound
      ? (this.sceneDef.bubble_tips || []).filter(b => b.trigger === "end_scene")
      : [];
    if (endBubbles.length) this._showBubbles(endBubbles, () => this._doFinish());
    else this._doFinish();
  }

  _doFinish() {
    const allFound = this.goals.every(o => o.found);
    const ratio = this.timeTotal > 0 ? Math.max(0, this.timeLeft / this.timeTotal) : 0;
    // Parita' con engine.level_manager.compute_scene_score:
    //  - bonus: troncamento verso zero (Python int()), NON arrotondamento;
    //  - finalScore: aritmetica intera pura, nessun arrotondamento esterno.
    const bonus = allFound ? Math.trunc(ratio * this.R.bonus_time_max) : 0;
    let stars = 1;
    if (allFound && bonus / this.R.bonus_time_max >= this.R.bonus_ratio_3star) stars = 3;
    else if (allFound) stars = 2;
    const finalScore = (this.score + bonus) * (this.R.star_multiplier[stars] || 1);
    const sceneIdx = this.level.scenes.indexOf(this.sceneDef);
    this.result = {
      score: finalScore, base: this.score, bonus, stars, allFound,
      timeElapsed: Math.max(0, this.timeTotal - this.timeLeft),
      found: this.goals.filter(o => o.found).length, total: this.goals.length,
      sceneIdx,
    };
    // Autosave: tiene il migliore e sblocca scena/livello successivi
    this.save = Save.record(this.manifest.game_id, this.manifest, this.level.id, sceneIdx, this.sceneDef.id, finalScore, stars);
    this._resultsTs = performance.now();
    this._confetti = stars >= 2 ? this._makeConfetti() : [];
    this.audio.stopMusic();
    this.state = "RESULTS";
    this._beginFade();
  }

  // ── Host minigiochi ──────────────────────────────────────────────────────
  async _launchMinigame(mgId, triggerObj) {
    const Cls = MINIGAME_CLASSES[mgId];
    if (!Cls) {
      // Minigioco non ancora portato in JS: trattalo come una scoperta normale
      // (l'oggetto viene comunque consumato, niente blocco del livello).
      console.warn("Minigioco non implementato, fallback a 'trovato':", mgId);
      this._minigameTrigger = triggerObj;
      this._minigameDone({ success: true, score: this.R.points_per_object });
      return;
    }
    const base = this.manifest._base + "assets/minigames/" + mgId + "/";
    const strings = (this.manifest.minigame_strings &&
      this.manifest.minigame_strings[mgId] &&
      this.manifest.minigame_strings[mgId][this.lang]) || {};
    this.audio.stopMusic();
    const mg = new Cls(this, base, strings);
    try { await mg.load(); } catch (e) { console.warn("Load minigioco fallito:", e); }
    this._minigameTrigger = triggerObj;
    this.minigame = mg;
    this.state = "MINIGAME";
    mg.start();
    this._mgLastTs = performance.now();
    this._minigameLoop(this._mgLastTs);
  }

  _minigameLoop(ts) {
    if (this.state !== "MINIGAME" || !this.minigame) return;
    let dt = (ts - (this._mgLastTs || ts)) / 1000;
    this._mgLastTs = ts;
    if (dt > 0.1) dt = 0.1;
    this.minigame.update(dt);
    // se il minigioco si e' concluso durante l'update, fermati
    if (this.state !== "MINIGAME") return;
    const ctx = this.ctx, W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    ctx.clearRect(0, 0, W, H);
    this.minigame.draw(ctx, W, H);
    requestAnimationFrame((t) => this._minigameLoop(t));
  }

  // Replica engine/core.py:_on_minigame_complete
  _minigameDone(result) {
    const obj = this._minigameTrigger;
    this.minigame = null;
    const success = !!(result && result.success);
    const addedScore = (result && result.score) || 0;
    if (addedScore > 0) this.score += addedScore;
    if (obj) {
      obj.found = true;            // consumato comunque (replica engine)
      this.lastFindAt = performance.now();
      this.feedback = { x: this.canvas.clientWidth / 2, y: this.canvas.clientHeight / 2, t: performance.now(), ok: success };
    }
    this.audio.sfx(success ? "complete" : "found");
    this._mgLastTs = 0;
    if (this.sceneDef) {
      this.state = "SCENE";
      this.audio.playMusic(this.sceneDef.music);
      if (this.goals && this.goals.every(o => o.found)) this._completeScene();
      else this.invalidate();
    } else {
      this.state = "LEVEL_SELECT";
      this.audio.playMusic(this.manifest.menu_music);
      this._beginFade();
    }
  }

  _spawnPopup(x, y, text, color) {
    this.popups = this.popups || [];
    this.popups.push({ x, y, text, color, born: performance.now() });
  }
  _spawnBurst(x, y, color) {
    this.findParticles = this.findParticles || [];
    for (let i = 0; i < 14; i++) {
      const a = Math.random() * Math.PI * 2, sp = 60 + Math.random() * 220;
      this.findParticles.push({ x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, life: 0.4 + Math.random() * 0.4, max: 0.8, color, size: 2 + Math.random() * 3 });
    }
  }
  _updateFindFx(dt) {
    if (this.findParticles && this.findParticles.length) {
      for (const p of this.findParticles) { p.vy += 300 * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt; }
      this.findParticles = this.findParticles.filter(p => p.life > 0);
    }
    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 40);
  }
  _renderFindFx(ctx) {
    const now = performance.now();
    if (this.findParticles) for (const p of this.findParticles) {
      ctx.globalAlpha = Math.max(0, p.life / p.max);
      ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    if (this.popups && this.popups.length) {
      ctx.textAlign = "center"; ctx.font = "bold 24px system-ui, sans-serif";
      this.popups = this.popups.filter(pp => {
        const age = (now - pp.born) / 1000;
        if (age > 0.9) return false;
        ctx.globalAlpha = 1 - age / 0.9;
        ctx.fillStyle = "rgba(0,0,0,0.55)"; ctx.fillText(pp.text, pp.x + 1, pp.y - age * 50 + 1);
        ctx.fillStyle = pp.color; ctx.fillText(pp.text, pp.x, pp.y - age * 50);
        return true;
      });
      ctx.globalAlpha = 1;
    }
  }

  _makeConfetti() {
    const cols = [this.theme.accent(), this.theme.accent2(), "#ffd479", "#5dff8f", "#8fe3e8"];
    const W = this.canvas.clientWidth;
    const out = [];
    for (let i = 0; i < 90; i++) {
      out.push({
        x: Math.random() * W, y: -20 - Math.random() * 200,
        vx: (Math.random() - 0.5) * 60, vy: 80 + Math.random() * 140,
        size: 5 + Math.random() * 7, rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 8,
        color: cols[(Math.random() * cols.length) | 0],
      });
    }
    return out;
  }

  // ── Hint / Pausa ─────────────────────────────────────────────────────────
  _inRect(x, y, r) { return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h; }

  // Penalita' punteggio per un miss data la sequenza consecutiva.
  // Parita' con engine.level_manager.LevelManager.miss_penalty (curva progressiva).
  _missPenalty(consecutive) {
    const curve = (Array.isArray(this.R.miss_penalty_curve) && this.R.miss_penalty_curve.length)
      ? this.R.miss_penalty_curve : [this.R.miss_point_penalty];
    const idx = Math.min(Math.max(consecutive, 1) - 1, curve.length - 1);
    return curve[idx];
  }

  // Replica RewardTracker.on_object_found (senza combo_thresholds configurati).
  _awardHintProgress() {
    const earned = this.earnedHintsThisScene;
    const inc = earned === 0 ? 0.20 : earned === 1 ? 0.143 : earned === 2 ? 0.112 : 0.05;
    this.progressToNextHint = Math.min(1, this.progressToNextHint + inc);
    if (this.progressToNextHint >= 1) {
      this.hintsAvailable++;
      this.earnedHintsThisScene++;
      this.progressToNextHint = 0;
    }
  }

  _useHint() {
    const now = performance.now();
    if (this.hintsUsedTotal >= this.R.hint_max_uses) return;
    if (this.hintsAvailable <= 0) return;
    if (now < this.hintReadyAt) return; // cooldown attivo
    const target = this.goals.find(o => !o.found);
    if (!target) return;
    const penalty = this.R.hint_penalties[Math.min(this.hintsUsedTotal, this.R.hint_penalties.length - 1)];
    this.score = Math.max(0, this.score - penalty);
    this.hintsAvailable--;
    this.hintsUsedTotal++;
    this.hintReadyAt = now + this.R.hint_cooldown * 1000;
    this.hintTarget = target;
    this.hintGlowUntil = now + HINT_GLOW_MS;
    // In scena con torcia, un hint illumina tutto per 5s (replica core.py hint-flash).
    if (this.sceneDef && this.sceneDef.flashlight) this.hintFlashUntil = now + 5000;
    this.audio.sfx("click");
    this.invalidate();
  }

  // Auto-glow per inattivita (replica hint_system.update auto-target).
  _autoHintTarget() {
    const target = this.goals.find(o => !o.found);
    if (!target) return null;
    const delay = target.hint_delay || HINT_AUTO_DEFAULT_DELAY;
    const inact = (performance.now() - this.lastFindAt) / 1000;
    if (inact < delay) return null;
    const intensity = Math.min(1, 0.3 + ((inact - delay) / 10) * 0.7);
    return { obj: target, intensity };
  }

  _togglePause() {
    this.state = this.state === "SCENE" ? "PAUSE" : "SCENE";
    this.invalidate();
  }

  _clickPause(sx, sy) {
    if (!this._pauseMenuHit) return;
    for (const b of this._pauseMenuHit) {
      if (this._inRect(sx, sy, b)) {
        this.audio.sfx("click");
        if (b.action === "resume") this.state = "SCENE";
        else if (b.action === "settings") { this._openSettings(); return; }
        else if (b.action === "restart") { this.startScene(this.level, this.sceneDef); return; }
        else if (b.action === "quit") {
          this.state = "LEVEL_SELECT";
          this.audio.playMusic(this.manifest.menu_music);
          this._beginFade();
        }
        this.invalidate();
        return;
      }
    }
  }

  _clickMenu(sx, sy) {
    if (this._gearBtn && this._inRect(sx, sy, this._gearBtn)) {
      this.audio.sfx("click"); this._openSettings(); return;
    }
    if (!this._menuHit) return;
    for (const item of this._menuHit) {
      if (this._inRect(sx, sy, item)) {
        if (item.locked) { this.audio.sfx("miss"); return; } // scena bloccata
        this.audio.sfx("click");
        this.startScene(item.level, item.scene);
        return;
      }
    }
  }

  _openSettings() {
    this._prevState = this.state;
    this.state = "SETTINGS";
    this.invalidate();
  }

  // Avvio dal menu START quando i menu sono gestiti dallo skin DOM: l'overlay
  // copre il canvas, quindi il click arriva dal DOM e non da _onPointer.
  _startFromMenu() {
    this.audio.unlock();
    this.state = "LEVEL_SELECT";
    this.audio.sfx("click");
    this.audio.playMusic(this.manifest.menu_music);
    this.invalidate();
  }

  // ── Render-on-demand ─────────────────────────────────────────────────────
  _frame() {
    this._renderScheduled = false;

    // Menu via skin DOM/CSS: se lo skin gestisce lo stato, mostra l'overlay e
    // salta il rendering canvas dei menu (scena/minigioco restano su canvas).
    const skin = this.menuSkin;
    if (skin && skin.handles(this.state)) { skin.show(this.state); return; }
    if (skin) skin.hide();

    const ctx = this.ctx;
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);

    if (this.state === "START") this._renderStart(ctx, W, H);
    else if (this.state === "LEVEL_SELECT") this._renderMenu(ctx, W, H);
    else if (this.state === "SCENE") this._renderScene(ctx, W, H);
    else if (this.state === "PAUSE") { this._renderScene(ctx, W, H); this._renderPause(ctx, W, H); }
    else if (this.state === "RESULTS") this._renderResults(ctx, W, H);
    else if (this.state === "SETTINGS") this._renderSettings(ctx, W, H);
    else if (this.state === "MINIGAME") { if (this.minigame) this.minigame.draw(ctx, W, H); }

    // Transizione fade-from-black (sopra tutto)
    const nowF = performance.now();
    if (nowF < this._fadeUntil) {
      ctx.fillStyle = `rgba(0,0,0,${(this._fadeUntil - nowF) / FADE_MS})`;
      ctx.fillRect(0, 0, W, H);
    }

    // Anima glow/feedback/effetti/fumetti/results finche' attivi.
    const now = performance.now();
    const inScene = this.state === "SCENE";
    const fxActive = inScene && this.effects && this.effects.length > 0;
    const glowActive = inScene && (now < this.hintGlowUntil || this._autoHintTarget());
    const flashActive = inScene && this.sceneDef && this.sceneDef.flashlight && now < this.hintFlashUntil + 200;
    const bubbleTyping = inScene && this.activeBubble && this.activeBubble._typing;
    const resultsAnim = this.state === "RESULTS" &&
      ((now - (this._resultsTs || 0)) < 1500 || (this._confetti && this._confetti.length));
    const sceneVideo = this.state === "SCENE" && this.sceneDef && this.sceneDef.bg_is_video;
    const menuVideo = this.state === "LEVEL_SELECT" && this.manifest.menu_video;
    const findFx = inScene && ((this.findParticles && this.findParticles.length) || (this.popups && this.popups.length) || this.shake > 0);
    const fading = now < this._fadeUntil;
    if (this.feedback || glowActive || fxActive || flashActive || bubbleTyping || resultsAnim || sceneVideo || menuVideo || findFx || fading) this.invalidate();
  }

  _bgGradient(ctx, W, H) {
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, this.theme.bgTop());
    grad.addColorStop(1, this.theme.bgBottom());
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
  }

  // Pulsante ingranaggio (impostazioni) in alto a destra; ritorna il rect.
  _drawGear(ctx, W) {
    const s = Math.max(0.7, Math.min(W / 1280, this.canvas.clientHeight / 720));
    const r = 16 * s, cx = W - 30 * s, cy = 30 * s;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.beginPath(); ctx.arc(0, 0, r + 8 * s, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = this.theme.accent(); ctx.lineWidth = 2.5 * s;
    ctx.fillStyle = this.theme.accent();
    // denti
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      ctx.save(); ctx.rotate(a);
      ctx.fillRect(-2 * s, -r - 3 * s, 4 * s, 6 * s);
      ctx.restore();
    }
    ctx.beginPath(); ctx.arc(0, 0, r * 0.7, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, r * 0.32, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    this._gearBtn = { x: cx - r - 8 * s, y: cy - r - 8 * s, w: (r + 8 * s) * 2, h: (r + 8 * s) * 2 };
  }

  _renderStart(ctx, W, H) {
    this._bgGradient(ctx, W, H);
    ctx.textAlign = "center";
    ctx.fillStyle = "#fff";
    ctx.font = "bold 56px system-ui, sans-serif";
    ctx.fillText(this.t(this.manifest.title_key, this.manifest.game_id), W / 2, H / 2 - 30);
    ctx.fillStyle = "#7fa8ff";
    ctx.font = "22px system-ui, sans-serif";
    const pulse = 0.6 + 0.4 * Math.abs(Math.sin(performance.now() / 600));
    ctx.globalAlpha = pulse;
    ctx.fillText(this.t("start_prompt", "Clicca per iniziare"), W / 2, H / 2 + 30);
    ctx.globalAlpha = 1;
    this.invalidate(); // anima il pulse
  }

  _renderScene(ctx, W, H) {
    const now = performance.now();
    let dt = (now - (this._sceneTs || now)) / 1000; this._sceneTs = now; if (dt > 0.1) dt = 0.1;
    this._updateFindFx(dt);

    // Screen shake (applicato a sfondo+oggetti+effetti, non alla HUD)
    const sh = this.shake || 0;
    ctx.save();
    if (sh) ctx.translate((Math.random() * 2 - 1) * sh, (Math.random() * 2 - 1) * sh);

    // Background letterboxato — identico a bg_to_screen mapping (immagine o video)
    const bx = this.sm.bgScreenX, by = this.sm.bgScreenY, bw = this.sm.bgScreenW, bh = this.sm.bgScreenH;
    if (this.bgVideo && this.bgVideo.readyState >= 2) {
      ctx.drawImage(this.bgVideo, bx, by, bw, bh);
    } else if (this.bgImg) {
      ctx.drawImage(this.bgImg, bx, by, bw, bh);
    } else {
      ctx.fillStyle = "#000"; ctx.fillRect(bx, by, bw, bh);
    }
    // Oggetti non trovati (decorativi inclusi), ordine layer_z
    for (const obj of this.objects) {
      if (obj.found || !obj._img) continue;
      drawObject(ctx, this.sm, obj, obj._img);
    }
    const flashlightActive = !!(this.sceneDef.flashlight) && now >= this.hintFlashUntil;

    // Effetti: se NON c'e' la torcia attiva, si disegnano normalmente qui.
    if (!flashlightActive) this._updateAndDrawEffects(ctx);
    // Oscurita' torcia con buco sfumato attorno al puntatore.
    if (flashlightActive) this._renderFlashlight(ctx, W, H);
    // Se la torcia e' attiva, gli effetti vanno SOPRA l'oscurita' (brillano).
    if (flashlightActive) this._updateAndDrawEffects(ctx);

    this._renderHintGlow(ctx);
    this._renderFindFx(ctx);
    ctx.restore();

    this._renderBubble(ctx, W, H);
    this._renderHud(ctx, W, H);
    this._renderFeedback(ctx);
  }

  // Fumetto con coda, testo a macchina da scrivere e pulsante CHIUDI.
  _renderBubble(ctx, W, H) {
    const b = this.activeBubble;
    if (!b) return;
    const now = performance.now();
    const zoom = Math.max(0.4, this.sm.bgDisplayScale);
    const [sx, sy] = this.sm.bgToScreen(b.x, b.y);
    const bw = Math.max(160, b.width * this.sm.bgDisplayScale);
    const bh = Math.max(90, b.height * this.sm.bgDisplayScale);
    const pad = 16 * zoom;
    const bx = sx - bw / 2;
    const by = sy - bh - 36 * zoom;
    const [cr, cg, cb] = b.color;
    const fill = `rgba(${cr},${cg},${cb},${b.alpha / 255})`;
    const border = `rgb(${Math.max(0, cr - 40)},${Math.max(0, cg - 40)},${Math.max(0, cb - 40)})`;

    ctx.save();
    // Ombra morbida
    ctx.shadowColor = "rgba(0,0,0,0.4)";
    ctx.shadowBlur = 16 * zoom;
    ctx.shadowOffsetY = 5 * zoom;
    // Coda verso il punto
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.moveTo(sx - 12 * zoom, by + bh - 1);
    ctx.lineTo(sx + 12 * zoom, by + bh - 1);
    ctx.lineTo(sx, by + bh + 28 * zoom);
    ctx.closePath();
    ctx.fill();
    // Corpo
    this._roundRect(ctx, bx, by, bw, bh, 18 * zoom);
    ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.strokeStyle = border;
    ctx.lineWidth = 2;
    this._roundRect(ctx, bx, by, bw, bh, 18 * zoom);
    ctx.stroke();

    // Testo localizzato con effetto macchina da scrivere
    const fontPx = Math.max(11, b.font_size * zoom);
    ctx.font = `${fontPx}px "Segoe UI", system-ui, sans-serif`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    const full = this.t(b.text_key, b.text_key);
    b._chars = ((now - b._ts) / 1000) * 25.0;
    b._typing = b._chars < full.length;
    const shown = full.slice(0, Math.floor(b._chars));
    const maxW = bw - pad * 2;
    const words = shown.split(" ");
    const lines = [];
    let cur = "";
    for (const w of words) {
      const test = cur ? cur + " " + w : w;
      if (ctx.measureText(test).width <= maxW) cur = test;
      else { if (cur) lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    const lh = fontPx * 1.3;
    ctx.fillStyle = `rgb(${b.font_color[0]},${b.font_color[1]},${b.font_color[2]})`;
    lines.forEach((ln, i) => ctx.fillText(ln, bx + pad, by + pad + i * lh));

    // Pulsante CHIUDI
    const btnW = 96 * zoom, btnH = 30 * zoom;
    const btnX = sx - btnW / 2, btnY = by + bh - btnH - 10 * zoom;
    ctx.fillStyle = "#3cb96d";
    this._roundRect(ctx, btnX, btnY, btnW, btnH, 8 * zoom);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `bold ${Math.max(10, 14 * zoom)}px system-ui, sans-serif`;
    ctx.fillText(this.t("btn_close", "CHIUDI"), sx, btnY + btnH / 2);
    this._bubbleCloseBtn = { x: btnX, y: btnY, w: btnW, h: btnH };
    ctx.restore();
  }

  // Maschera d'oscuramento con buco radiale morbido (replica _draw_flashlight_effect).
  // La maschera si costruisce su un canvas offscreen (nero + buco trasparente)
  // e poi si disegna SOPRA la scena, cosi' il destination-out non cancella la scena.
  _renderFlashlight(ctx, W, H) {
    const s = Math.max(0.5, Math.min(W / 1280, H / 720));
    const radius = this.sceneDef.flashlight_radius * 1.15 * s;
    const mx = this.ptrX, my = this.ptrY;

    if (!this._flMask || this._flMask.width !== Math.round(W) || this._flMask.height !== Math.round(H)) {
      this._flMask = document.createElement("canvas");
      this._flMask.width = Math.round(W);
      this._flMask.height = Math.round(H);
    }
    const m = this._flMask.getContext("2d");
    m.setTransform(1, 0, 0, 1, 0, 0);
    m.clearRect(0, 0, W, H);
    m.globalCompositeOperation = "source-over";
    m.fillStyle = "rgba(0,0,0,1)";
    m.fillRect(0, 0, W, H);
    // Scava il buco: erase = 1 - dist^1.4 (centro trasparente, bordo nero).
    m.globalCompositeOperation = "destination-out";
    const grad = m.createRadialGradient(mx, my, 0, mx, my, radius);
    const stops = [[0, 1], [0.3, 0.815], [0.5, 0.621], [0.7, 0.385], [0.85, 0.201], [1, 0]];
    for (const [p, a] of stops) grad.addColorStop(p, `rgba(0,0,0,${a})`);
    m.fillStyle = grad;
    m.beginPath(); m.arc(mx, my, radius, 0, Math.PI * 2); m.fill();
    m.globalCompositeOperation = "source-over";

    ctx.drawImage(this._flMask, 0, 0, W, H);
  }

  // Avanza il tempo degli effetti (solo in SCENE) e li disegna sopra gli oggetti.
  _updateAndDrawEffects(ctx) {
    if (!this.effects || !this.effects.length) return;
    const now = performance.now();
    let dt = (now - (this._fxTs || now)) / 1000;
    this._fxTs = now;
    if (dt > 0.1) dt = 0.1; // evita salti dopo pausa/tab inattiva
    if (this.state === "SCENE") {
      this.fxTime += dt;
      for (const fx of this.effects) {
        const period = Math.max(0.01, fx.pulse_period || 2.0);
        if (fx.type === "glint") fx._t += dt / period; // replica update_effect_state
        else fx._t += dt * period;
      }
    }
    const sorted = [...this.effects].sort((a, b) => (a.layer_z || 40) - (b.layer_z || 40));
    for (const fx of sorted) {
      const [sx, sy] = this.sm.bgToScreen(fx.x, fx.y);
      const sr = fx.radius * this.sm.bgDisplayScale;
      if (fx.type === "glint") drawGlint(ctx, sx, sy, sr, fx.color, fx.intensity, fx._t, fx.phase, fx.pulse_min);
      else if (fx.type === "smoke") drawSmoke(ctx, sx, sy, sr, fx.color, fx.intensity, fx._t, fx.phase, fx.pulse_min);
      else if (fx.type === "flies") drawFlies(ctx, sx, sy, sr, fx.color, fx.intensity, fx._t, this.fxTime, fx.pulse_min);
    }
  }

  // Glow sull'oggetto target: manuale (forte, 1.2s) o automatico (da inattivita).
  _renderHintGlow(ctx) {
    const now = performance.now();
    let target = null, intensity = 0;
    if (now < this.hintGlowUntil && this.hintTarget && !this.hintTarget.found) {
      target = this.hintTarget;
      intensity = 1.0;
    } else {
      const auto = this._autoHintTarget();
      if (auto) { target = auto.obj; intensity = auto.intensity; }
    }
    if (!target) return;
    const g = objCenterAndSize(target);
    const [sx, sy] = this.sm.bgToScreen(g.cx, g.cy);
    const objR = Math.max(g.w, g.h) * this.sm.bgDisplayScale * 0.5;
    const pulse = 0.5 + 0.5 * Math.sin(now / 160); // 0..1

    ctx.save();
    // 1. Alone luminoso additivo attorno all'oggetto
    const haloR = Math.max(40, objR * 2.2);
    const halo = ctx.createRadialGradient(sx, sy, objR * 0.3, sx, sy, haloR);
    halo.addColorStop(0, `rgba(255,240,150,${0.55 * intensity})`);
    halo.addColorStop(0.5, `rgba(255,225,90,${0.28 * intensity})`);
    halo.addColorStop(1, "rgba(255,225,90,0)");
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(sx, sy, haloR, 0, Math.PI * 2); ctx.fill();
    ctx.globalCompositeOperation = "source-over";

    // 2. Anello pulsante ben visibile (contrasto su qualsiasi sfondo)
    const ringR = objR * (1.15 + 0.25 * pulse);
    ctx.lineWidth = Math.max(2, objR * 0.12);
    ctx.strokeStyle = `rgba(255,255,255,${0.85 * intensity})`;
    ctx.shadowColor = "rgba(255,210,60,0.9)";
    ctx.shadowBlur = Math.max(8, objR * 0.5);
    ctx.beginPath(); ctx.arc(sx, sy, ringR, 0, Math.PI * 2); ctx.stroke();
    // secondo anello dorato interno
    ctx.lineWidth = Math.max(1.5, objR * 0.08);
    ctx.strokeStyle = `rgba(255,200,40,${0.9 * intensity})`;
    ctx.beginPath(); ctx.arc(sx, sy, ringR * 0.78, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
  }

  _renderHud(ctx, W, H) {
    const s = Math.max(0.6, Math.min(W / 1280, H / 720));
    const found = this.goals.filter(o => o.found).length;
    const total = this.goals.length;
    const hudH = Math.round(110 * s);
    const top = H - hudH;

    ctx.save();
    ctx.textBaseline = "middle";

    // Barra inferiore
    ctx.fillStyle = "rgba(8,14,26,0.78)";
    ctx.fillRect(0, top, W, hudH);
    ctx.fillStyle = "rgba(127,168,255,0.5)";
    ctx.fillRect(0, top, W, 2);

    // Timer + contatore al centro
    const cy = top + hudH * 0.32;
    const tm = Math.max(0, Math.ceil(this.timeLeft));
    ctx.textAlign = "center";
    ctx.font = `bold ${Math.round(26 * s)}px system-ui, sans-serif`;
    ctx.fillStyle = this.timeLeft < 15 ? "#ff6b6b" : "#fff";
    ctx.fillText(`${String(Math.floor(tm / 60)).padStart(2, "0")}:${String(tm % 60).padStart(2, "0")}`, W / 2, cy);
    ctx.font = `${Math.round(14 * s)}px system-ui, sans-serif`;
    ctx.fillStyle = "#9fb3d8";
    ctx.fillText(`${found}/${total}`, W / 2, cy + Math.round(22 * s));

    // Nomi degli oggetti da trovare (goal non trovati, max 7), italici colorati.
    // Replica engine: blocco sinistro [0:4] e destro [4:7], ciascuno su 2 righe.
    const names = this.goals.filter(o => !o.found).slice(0, HUD_MAX_VISIBLE);
    const rowY = [top + hudH * 0.40, top + hudH * 0.74];
    const timerClear = 70 * s;
    ctx.font = `italic ${Math.round(18 * s)}px Georgia, "Times New Roman", serif`;
    const drawCell = (obj, baseIdx, x, y) => {
      const color = HUD_NAME_COLORS[baseIdx % HUD_NAME_COLORS.length];
      const label = this.t(obj.label_key, obj.catalog_id).toLowerCase();
      ctx.textAlign = "center";
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.fillText(label, x + 1, y + 1);
      ctx.fillStyle = color;
      ctx.fillText(label, x, y);
    };
    const drawBlock = (items, baseOffset, x0, x1) => {
      if (!items.length) return;
      const nTop = Math.ceil(items.length / 2);
      const span = x1 - x0;
      const placeRow = (rowItems, startK, y) => {
        rowItems.forEach((obj, j) => {
          const x = x0 + span * ((j + 0.5) / rowItems.length);
          drawCell(obj, baseOffset + startK + j, x, y);
        });
      };
      placeRow(items.slice(0, nTop), 0, rowY[0]);
      placeRow(items.slice(nTop), nTop, rowY[1]);
    };
    drawBlock(names.slice(0, 4), 0, 16 * s, W / 2 - timerClear);
    drawBlock(names.slice(4, 7), 4, W / 2 + timerClear, W - 64 * s);
    ctx.restore();

    this._renderHudButtons(ctx, W, H, s, top, hudH);
  }

  _renderHudButtons(ctx, W, H, s, top, hudH) {
    const now = performance.now();
    // Pulsante pausa: alto-sinistra
    const pb = Math.round(34 * s), pm = Math.round(10 * s);
    this._pauseBtn = { x: pm, y: pm, w: pb, h: pb };
    ctx.save();
    ctx.fillStyle = "rgba(8,14,26,0.6)";
    this._roundRect(ctx, pm, pm, pb, pb, 6 * s); ctx.fill();
    ctx.fillStyle = "#cdd";
    const barW = pb * 0.16, barH = pb * 0.46, gap = pb * 0.16;
    const bx = pm + pb / 2 - barW - gap / 2, by = pm + pb / 2 - barH / 2;
    ctx.fillRect(bx, by, barW, barH);
    ctx.fillRect(bx + barW + gap, by, barW, barH);
    ctx.restore();

    // Pulsante hint: barra inferiore destra, cerchio "?"
    const hr = Math.round(24 * s);
    const hx = W - hr - Math.round(24 * s), hy = top + hudH / 2;
    this._hintBtn = { x: hx - hr, y: hy - hr, w: hr * 2, h: hr * 2 };
    const cooldownLeft = Math.max(0, (this.hintReadyAt - now) / 1000);
    const disabled = this.hintsUsedTotal >= this.R.hint_max_uses || this.hintsAvailable <= 0;
    const onCooldown = cooldownLeft > 0;
    ctx.save();
    ctx.beginPath();
    ctx.arc(hx, hy, hr, 0, Math.PI * 2);
    ctx.fillStyle = (disabled || onCooldown) ? "#3a4257" : "#2f7d4f";
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.3)"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#fff";
    ctx.font = `bold ${Math.round(26 * s)}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("?", hx, hy + 1);
    // arco di cooldown
    if (onCooldown) {
      ctx.beginPath();
      ctx.arc(hx, hy, hr + 3, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (1 - cooldownLeft / this.R.hint_cooldown));
      ctx.strokeStyle = "#7fa8ff"; ctx.lineWidth = 3; ctx.stroke();
    }
    // conteggio hint disponibili
    if (!disabled) {
      ctx.fillStyle = "#ffd479";
      ctx.font = `bold ${Math.round(13 * s)}px system-ui, sans-serif`;
      ctx.fillText(String(this.hintsAvailable), hx + hr * 0.7, hy - hr * 0.7);
    }
    ctx.restore();
  }

  _renderPause(ctx, W, H) {
    ctx.save();
    ctx.fillStyle = "rgba(5,9,18,0.82)";
    ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";
    ctx.fillStyle = this.theme.text();
    ctx.font = "bold 40px Georgia, serif";
    ctx.shadowColor = this._withAlpha(this.theme.accent(), 0.6); ctx.shadowBlur = 16;
    ctx.fillText(this.t("hud_paused"), W / 2, H / 2 - 150);
    ctx.shadowBlur = 0;

    const opts = [
      { action: "resume", label: this.t("btn_resume") },
      { action: "settings", label: this.t("settings_title") },
      { action: "restart", label: this.t("btn_restart") },
      { action: "quit", label: this.t("btn_quit_to_main") },
    ];
    const bw = 300, bh = 52, gap = 16;
    this._pauseMenuHit = [];
    opts.forEach((o, i) => {
      const x = W / 2 - bw / 2;
      const y = H / 2 - 90 + i * (bh + gap);
      const primary = o.action === "resume";
      ctx.fillStyle = primary ? this.theme.accent() : "rgba(255,255,255,0.08)";
      this._roundRect(ctx, x, y, bw, bh, 10); ctx.fill();
      ctx.strokeStyle = primary ? "#fff" : this.theme.cardBorder(); ctx.lineWidth = primary ? 2 : 1.5;
      this._roundRect(ctx, x, y, bw, bh, 10); ctx.stroke();
      ctx.fillStyle = primary ? "#0c0c0c" : this.theme.text();
      ctx.font = "bold 21px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      ctx.fillText(o.label, W / 2, y + bh / 2);
      ctx.textBaseline = "alphabetic";
      this._pauseMenuHit.push({ x, y, w: bw, h: bh, action: o.action });
    });
    ctx.restore();
  }

  _renderFeedback(ctx) {
    if (!this.feedback) return;
    const age = (performance.now() - this.feedback.t) / 1000;
    if (age > 0.6) { this.feedback = null; return; }
    const r = 10 + age * 40;
    ctx.save();
    ctx.globalAlpha = 1 - age / 0.6;
    ctx.lineWidth = 3;
    ctx.strokeStyle = this.feedback.ok ? "#5dff8f" : "#ff5d5d";
    ctx.beginPath();
    ctx.arc(this.feedback.x, this.feedback.y, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  _renderMenu(ctx, W, H) {
    // Sfondo: video del menu (cover) + velo scuro, altrimenti gradiente a tema.
    const mv = this.manifest.menu_video ? this._getVideo(this.manifest.menu_video) : null;
    const poster = this._menuPosterImg && this._menuPosterImg.complete ? this._menuPosterImg : null;
    if (mv && mv.readyState >= 2) {
      const sc = Math.max(W / mv.videoWidth, H / mv.videoHeight);
      const dw = mv.videoWidth * sc, dh = mv.videoHeight * sc;
      ctx.drawImage(mv, (W - dw) / 2, (H - dh) / 2, dw, dh);
      ctx.fillStyle = "rgba(6,10,20,0.55)"; ctx.fillRect(0, 0, W, H);
    } else if (poster) {
      const sc = Math.max(W / poster.naturalWidth, H / poster.naturalHeight);
      const dw = poster.naturalWidth * sc, dh = poster.naturalHeight * sc;
      ctx.drawImage(poster, (W - dw) / 2, (H - dh) / 2, dw, dh);
      ctx.fillStyle = "rgba(6,10,20,0.55)"; ctx.fillRect(0, 0, W, H);
    } else {
      this._bgGradient(ctx, W, H);
    }
    // bagliore d'accento decorativo in alto
    const gl = ctx.createRadialGradient(W / 2, -40, 20, W / 2, -40, 360);
    gl.addColorStop(0, this._withAlpha(this.theme.accent(), 0.18));
    gl.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gl; ctx.fillRect(0, 0, W, 300);

    ctx.textAlign = "center";
    ctx.fillStyle = this.theme.text();
    ctx.font = "bold 38px Georgia, serif";
    ctx.shadowColor = this._withAlpha(this.theme.accent(), 0.6); ctx.shadowBlur = 18;
    ctx.fillText(this.t(this.manifest.title_key, this.manifest.game_id), W / 2, 58);
    ctx.shadowBlur = 0;
    ctx.fillStyle = this.theme.accent();
    ctx.font = "16px system-ui, sans-serif";
    ctx.fillText(this.t("menu_select_scene"), W / 2, 86);

    this._drawGear(ctx, W);

    this._menuHit = [];
    this._thumbs = this._thumbs || {};
    const cw = 250, ch = 168, gap = 24;
    const cols = Math.min(4, Math.max(1, Math.floor((W - 40) / (cw + gap))));
    const data = this.save;
    let y = 132;

    for (const lvl of this.manifest.levels) {
      ctx.textAlign = "left";
      ctx.fillStyle = this.theme.accent2();
      ctx.font = "bold 19px Georgia, serif";
      const totalW = cols * cw + (cols - 1) * gap;
      const startX = (W - totalW) / 2;
      ctx.fillText(this.t(lvlName(lvl), lvl.id), startX + 4, y);
      y += 18;

      let i = 0;
      for (const sc of lvl.scenes) {
        const col = i % cols, row = Math.floor(i / cols);
        const x = startX + col * (cw + gap);
        const cardY = y + row * (ch + gap);
        const locked = !Save.isSceneUnlocked(data, this.manifest, lvl.id, i);
        const stars = Save.getStars(data, lvl.id, sc.id);
        const hovered = !locked && this.ptrX >= x && this.ptrX <= x + cw && this.ptrY >= cardY && this.ptrY <= cardY + ch;

        ctx.save();
        if (hovered) { ctx.shadowColor = this._withAlpha(this.theme.accent(), 0.85); ctx.shadowBlur = 26; }
        this._roundRect(ctx, x, cardY, cw, ch, 14);
        ctx.fillStyle = "rgba(0,0,0,0.01)"; ctx.fill(); // applica l'ombra
        ctx.shadowColor = "transparent";
        this._roundRect(ctx, x, cardY, cw, ch, 14);
        ctx.clip();
        ctx.fillStyle = this.theme.bgBottom();
        ctx.fillRect(x, cardY, cw, ch);
        const thumb = this._getThumb(sc);
        if (thumb) {
          const sc2 = Math.max(cw / thumb.width, ch / thumb.height);
          const dw = thumb.width * sc2, dh = thumb.height * sc2;
          if (locked) ctx.filter = "grayscale(1) brightness(0.5)";
          ctx.drawImage(thumb, x + (cw - dw) / 2, cardY + (ch - dh) / 2, dw, dh);
          ctx.filter = "none";
        }
        // velo + gradiente
        if (locked) { ctx.fillStyle = "rgba(4,6,12,0.55)"; ctx.fillRect(x, cardY, cw, ch); }
        const grad = ctx.createLinearGradient(0, cardY + ch - 70, 0, cardY + ch);
        grad.addColorStop(0, "rgba(6,10,20,0)");
        grad.addColorStop(1, "rgba(6,10,20,0.94)");
        ctx.fillStyle = grad;
        ctx.fillRect(x, cardY + ch - 70, cw, 70);
        // stelle guadagnate (in alto a destra)
        if (!locked && stars > 0) {
          for (let s = 0; s < 3; s++) {
            this._drawStar(ctx, x + cw - 18 - s * 20, cardY + 18, 8,
              s < stars ? this.theme.accent2() : "rgba(255,255,255,0.18)", null);
          }
        }
        // testi
        ctx.textAlign = "left";
        ctx.fillStyle = "#fff";
        ctx.font = "bold 19px Georgia, serif";
        ctx.fillText(this.t(sc.id + "_name", sc.id), x + 14, cardY + ch - 30);
        ctx.fillStyle = this.theme.accent();
        ctx.font = "13px system-ui, sans-serif";
        const n = sc.objects.filter(o => o.is_goal).length;
        ctx.fillText(`${n} ${this.t("menu_objects")}`, x + 14, cardY + ch - 12);
        // lucchetto centrale se bloccato
        if (locked) {
          ctx.textAlign = "center"; ctx.fillStyle = this.theme.lock();
          ctx.font = "34px system-ui, sans-serif";
          ctx.fillText("🔒", x + cw / 2, cardY + ch / 2 + 4);
        }
        ctx.restore();
        // bordo (evidenziato in hover)
        ctx.strokeStyle = locked ? "rgba(255,255,255,0.12)" : (hovered ? this.theme.cardBorderHover() : this.theme.cardBorder());
        ctx.lineWidth = hovered ? 3 : 2;
        this._roundRect(ctx, x, cardY, cw, ch, 14); ctx.stroke();

        this._menuHit.push({ x, y: cardY, w: cw, h: ch, level: lvl, scene: sc, locked });
        i++;
      }
      const rows = Math.ceil(lvl.scenes.length / cols);
      y += rows * (ch + gap) + 28;
    }
  }

  _withAlpha(rgb, a) {
    const m = rgb.match(/\d+/g);
    return `rgba(${m[0]},${m[1]},${m[2]},${a})`;
  }

  // Elemento <video> in loop, muto, riutilizzato per src. Usato come sorgente
  // di drawImage (sfondo scena/menu). Muto => autoplay consentito dai browser.
  _getVideo(relSrc) {
    if (!relSrc) return null;
    this._videos = this._videos || {};
    let v = this._videos[relSrc];
    if (!v) {
      v = document.createElement("video");
      v.muted = true; v.loop = true; v.autoplay = true; v.playsInline = true;
      v.setAttribute("playsinline", ""); v.preload = "auto";
      v.style.cssText = "position:fixed;left:-10px;top:-10px;width:2px;height:2px;opacity:0;pointer-events:none;";
      v.src = this.manifest._base + relSrc;
      document.body.appendChild(v);
      v.addEventListener("loadeddata", () => this.invalidate());
      this._videos[relSrc] = v;
    }
    if (v.paused) v.play().catch(() => {});
    return v;
  }
  _pauseInactiveVideos(keepSrc) {
    if (!this._videos) return;
    for (const [src, v] of Object.entries(this._videos)) {
      if (src !== keepSrc && !v.paused) try { v.pause(); } catch (e) {}
    }
  }

  // Carica (lazy) e cache la thumbnail di una scena; ridisegna al caricamento.
  _getThumb(sc) {
    if (!sc.thumb) return null;
    const key = sc.thumb;
    const entry = this._thumbs[key];
    if (entry) return entry.img;
    this._thumbs[key] = { img: null };
    const img = new Image();
    img.onload = () => { this._thumbs[key].img = img; if (this.state === "LEVEL_SELECT") this.invalidate(); };
    img.src = this.manifest._base + sc.thumb;
    return null;
  }

  _drawStar(ctx, cx, cy, r, fill, stroke) {
    ctx.beginPath();
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + i * 2 * Math.PI / 5;
      const a2 = a + Math.PI / 5;
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.lineTo(cx + Math.cos(a2) * r * 0.45, cy + Math.sin(a2) * r * 0.45);
    }
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = Math.max(1.5, r * 0.08); ctx.stroke(); }
  }

  _renderResults(ctx, W, H) {
    const r = this.result || { score: 0, stars: 0, allFound: false, found: 0, total: 0, timeElapsed: 0 };
    const t = (performance.now() - (this._resultsTs || performance.now())) / 1000;
    const accent = this.theme.accent2();

    // Sfondo a tema scurito
    this._bgGradient(ctx, W, H);
    ctx.fillStyle = "rgba(4,6,12,0.7)";
    ctx.fillRect(0, 0, W, H);

    // Coriandoli (per 2-3 stelle)
    if (this._confetti && this._confetti.length) {
      const dt = Math.min(0.05, (performance.now() - (this._confettiTs || performance.now())) / 1000);
      this._confettiTs = performance.now();
      ctx.save();
      for (const p of this._confetti) {
        p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.vr * dt; p.vy += 60 * dt;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
        ctx.fillStyle = p.color; ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }
      this._confetti = this._confetti.filter(p => p.y < H + 30);
      ctx.restore();
    }

    // Pannello
    const pw = Math.min(460, W - 60), ph = Math.min(560, H - 60);
    const px = (W - pw) / 2;
    const drop = Math.min(1, t / 0.4);
    const py = (H - ph) / 2 - (1 - (1 - Math.pow(1 - drop, 3))) * 60;
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.6)"; ctx.shadowBlur = 30;
    ctx.fillStyle = this.theme.bgBottom();
    this._roundRect(ctx, px, py, pw, ph, 18); ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.strokeStyle = accent; ctx.lineWidth = 2;
    this._roundRect(ctx, px, py, pw, ph, 18); ctx.stroke();
    ctx.restore();

    const cx = W / 2;
    let cy = py + 56;
    ctx.textAlign = "center";
    // Titolo
    ctx.fillStyle = r.allFound ? "#46d27e" : "#e0563f";
    ctx.font = "bold 30px Georgia, serif";
    ctx.fillText(r.allFound ? this.t("mission_complete") : this.t("mission_failed"), cx, cy);
    cy += 64;

    // Stelle con pop sequenziale
    const starR = 30, gap = 78;
    for (let i = 0; i < 3; i++) {
      const sx = cx + (i - 1) * gap;
      const delay = 0.4 + i * 0.18;
      const filled = i < r.stars;
      let scale = 1;
      if (filled) {
        const p = Math.max(0, Math.min(1, (t - delay) / 0.3));
        scale = p <= 0 ? 0 : Math.sin(p * Math.PI * 0.8) * 0.4 + (p >= 1 ? 1 : 0.85);
        if (p >= 1) scale = 1;
      }
      ctx.save(); ctx.translate(sx, cy); ctx.scale(scale, scale);
      if (filled) {
        ctx.shadowColor = accent; ctx.shadowBlur = 18;
        this._drawStar(ctx, 0, 0, starR, accent, "#fff6c8");
      } else {
        this._drawStar(ctx, 0, 0, starR, "rgba(255,255,255,0.10)", "rgba(255,255,255,0.25)");
      }
      ctx.restore();
    }
    cy += 78;

    // Punteggio animato
    const scoreProg = Math.min(1, t / 0.7);
    const shown = Math.round(r.score * scoreProg);
    ctx.fillStyle = accent;
    ctx.font = "italic 16px Georgia, serif";
    ctx.fillText(this.t("total_score"), cx, cy); cy += 44;
    ctx.fillStyle = "#fff";
    ctx.font = "bold 52px Georgia, serif";
    ctx.fillText(String(shown), cx, cy); cy += 36;

    // Bonus perfetto
    if (r.allFound) {
      ctx.fillStyle = "#46d27e";
      ctx.font = "italic 17px Georgia, serif";
      ctx.fillText(this.t("perfect_score"), cx, cy);
    }
    cy += 30;

    // Statistiche
    ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(px + 40, cy); ctx.lineTo(px + pw - 40, cy); ctx.stroke();
    cy += 30;
    const mm = String(Math.floor(r.timeElapsed / 60)).padStart(2, "0");
    const ss = String(Math.floor(r.timeElapsed % 60)).padStart(2, "0");
    ctx.font = "15px system-ui, sans-serif";
    ctx.fillStyle = this.theme.textDim();
    ctx.textAlign = "left"; ctx.fillText(this.t("time_elapsed"), px + 50, cy);
    ctx.fillStyle = "#fff"; ctx.textAlign = "right"; ctx.fillText(`${mm}:${ss}`, px + pw - 50, cy);
    cy += 28;
    ctx.fillStyle = this.theme.textDim(); ctx.textAlign = "left"; ctx.fillText(this.t("objects_found"), px + 50, cy);
    ctx.fillStyle = "#fff"; ctx.textAlign = "right"; ctx.fillText(`${r.found}/${r.total}`, px + pw - 50, cy);
    cy += 40;

    // Pulsanti (compaiono dopo 0.6s)
    this._resultBtns = [];
    if (t >= 0.6) {
      const hasNext = r.allFound && this.level.scenes[r.sceneIdx + 1];
      const btnH = 46, btnGap = 14;
      const btns = [{ action: "retry", label: this.t("btn_retry"), accent: false }];
      if (hasNext) btns.push({ action: "next", label: this.t("btn_next"), accent: true });
      else btns.push({ action: "menu", label: this.t("btn_continue"), accent: true });
      const totalW = pw - 80, bw = (totalW - btnGap * (btns.length - 1)) / btns.length;
      btns.forEach((b, i) => {
        const bx = px + 40 + i * (bw + btnGap);
        const by = py + ph - 64;
        ctx.fillStyle = b.accent ? accent : "rgba(255,255,255,0.10)";
        this._roundRect(ctx, bx, by, bw, btnH, 10); ctx.fill();
        ctx.fillStyle = b.accent ? "#1a1207" : "#fff";
        ctx.font = "bold 18px system-ui, sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(b.label, bx + bw / 2, by + btnH / 2);
        ctx.textBaseline = "alphabetic";
        this._resultBtns.push({ x: bx, y: by, w: bw, h: btnH, action: b.action });
      });
    }
  }

  _renderSettings(ctx, W, H) {
    // sfondo: se veniamo dal gioco, mostra la scena offuscata sotto
    if (this._prevState === "PAUSE" || this._prevState === "SCENE") {
      this._renderScene(ctx, W, H);
      ctx.fillStyle = "rgba(4,6,12,0.82)"; ctx.fillRect(0, 0, W, H);
    } else {
      this._bgGradient(ctx, W, H);
    }
    const pw = Math.min(520, W - 50), ph = Math.min(440, H - 50);
    const px = (W - pw) / 2, py = (H - ph) / 2;
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.6)"; ctx.shadowBlur = 28;
    ctx.fillStyle = this.theme.bgBottom();
    this._roundRect(ctx, px, py, pw, ph, 18); ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.strokeStyle = this.theme.accent(); ctx.lineWidth = 2;
    this._roundRect(ctx, px, py, pw, ph, 18); ctx.stroke();
    ctx.restore();

    ctx.textAlign = "center";
    ctx.fillStyle = this.theme.text();
    ctx.font = "bold 26px Georgia, serif";
    ctx.fillText(this.t("settings_title"), W / 2, py + 44);

    this._setHit = { sliders: [], langBtns: [], back: null };
    const cx0 = px + 40, rowW = pw - 80;
    let yy = py + 92;

    const drawSlider = (label, value, key) => {
      ctx.textAlign = "left"; ctx.fillStyle = this.theme.textDim();
      ctx.font = "15px system-ui, sans-serif";
      ctx.fillText(label, cx0, yy - 8);
      ctx.textAlign = "right"; ctx.fillStyle = this.theme.text();
      ctx.fillText(Math.round(value * 100) + "%", cx0 + rowW, yy - 8);
      const tx = cx0, ty = yy + 4, tw = rowW, th = 8;
      ctx.fillStyle = this.theme.sliderBg();
      this._roundRect(ctx, tx, ty, tw, th, 4); ctx.fill();
      ctx.fillStyle = this.theme.sliderFill();
      this._roundRect(ctx, tx, ty, tw * value, th, 4); ctx.fill();
      // handle
      ctx.beginPath(); ctx.fillStyle = "#fff";
      ctx.arc(tx + tw * value, ty + th / 2, 11, 0, Math.PI * 2); ctx.fill();
      this._setHit.sliders.push({ x: tx, y: ty - 12, w: tw, h: th + 24, key });
      yy += 56;
    };
    drawSlider(this.t("label_music_volume"), this.audio.musicVol, "music");
    drawSlider(this.t("label_sfx_volume"), this.audio.sfxVol, "sfx");

    // Lingua
    ctx.textAlign = "left"; ctx.fillStyle = this.theme.textDim();
    ctx.font = "15px system-ui, sans-serif";
    ctx.fillText(this.t("label_language"), cx0, yy);
    yy += 16;
    const langs = (this.manifest.languages && this.manifest.languages.length)
      ? this.manifest.languages : ["it", "en", "de", "es", "fr"];
    const bw = Math.min(80, (rowW - (langs.length - 1) * 10) / langs.length), bh = 40, bgap = 10;
    const totW = langs.length * bw + (langs.length - 1) * bgap;
    let lx = px + (pw - totW) / 2;
    for (const lg of langs) {
      const active = lg === this.lang;
      ctx.fillStyle = active ? this.theme.accent() : "rgba(255,255,255,0.08)";
      this._roundRect(ctx, lx, yy, bw, bh, 8); ctx.fill();
      if (active) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; this._roundRect(ctx, lx, yy, bw, bh, 8); ctx.stroke(); }
      ctx.fillStyle = active ? "#0c0c0c" : this.theme.text();
      ctx.font = "bold 16px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(lg.toUpperCase(), lx + bw / 2, yy + bh / 2);
      ctx.textBaseline = "alphabetic";
      this._setHit.langBtns.push({ x: lx, y: yy, w: bw, h: bh, lang: lg });
      lx += bw + bgap;
    }
    yy += bh + 28;

    // Back
    const backW = 180, backH = 46, backX = (W - backW) / 2, backY = py + ph - backH - 22;
    ctx.fillStyle = this.theme.accent();
    this._roundRect(ctx, backX, backY, backW, backH, 10); ctx.fill();
    ctx.fillStyle = "#0c0c0c"; ctx.font = "bold 18px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(this.t("btn_back"), W / 2, backY + backH / 2);
    ctx.textBaseline = "alphabetic";
    this._setHit.back = { x: backX, y: backY, w: backW, h: backH };
  }

  _clickSettings(sx, sy) {
    const h = this._setHit;
    if (!h) return;
    for (const sl of h.sliders) {
      if (this._inRect(sx, sy, sl)) {
        const v = Math.max(0, Math.min(1, (sx - sl.x) / sl.w));
        if (sl.key === "music") { this.audio.musicVol = v; if (this.audio.musicEl) this.audio.musicEl.volume = this.audio.muted ? 0 : v; }
        else { this.audio.sfxVol = v; this.audio.sfx("found"); }
        this._saveSettings();
        this.invalidate();
        return;
      }
    }
    for (const lb of h.langBtns) {
      if (this._inRect(sx, sy, lb)) {
        this.lang = lb.lang; this._saveSettings(); this.audio.sfx("click"); this.invalidate();
        return;
      }
    }
    if (h.back && this._inRect(sx, sy, h.back)) {
      this.audio.sfx("click");
      this.state = (this._prevState === "PAUSE") ? "PAUSE" : "LEVEL_SELECT";
      this.invalidate();
    }
  }

  _clickResults(sx, sy) {
    if (!this._resultBtns) return;
    for (const b of this._resultBtns) {
      if (this._inRect(sx, sy, b)) {
        this.audio.sfx("click");
        if (b.action === "retry") { this.startScene(this.level, this.sceneDef); return; }
        if (b.action === "next") {
          const next = this.level.scenes[this.result.sceneIdx + 1];
          if (next) { this.startScene(this.level, next); return; }
        }
        // menu
        this.state = "LEVEL_SELECT";
        this.audio.playMusic(this.manifest.menu_music);
        this._beginFade();
        return;
      }
    }
  }
}

function lvlName(lvl) { return lvl.name_key || lvl.id; }

