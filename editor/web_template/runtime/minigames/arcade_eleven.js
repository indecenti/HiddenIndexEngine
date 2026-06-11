// ──────────────────────────────────────────────────────────────────────────
// ArcadeEleven — port JS di engine/minigames/arcade_eleven. Usa le carte reali
// (PNG della cartella 'tower', copiate dall'exporter come dipendenza).
// ──────────────────────────────────────────────────────────────────────────
const AE_RANKS = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "jack", "queen", "king"];
const AE_SUITS = ["clubs", "diamonds", "hearts", "spades"];
const AE_VALUES = { ace: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, jack: 11, queen: 12, king: 13 };

class AEParticle {
  constructor(x, y, color) {
    const a = Math.random() * Math.PI * 2, sp = 150 + Math.random() * 250;
    this.x = x; this.y = y; this.vx = Math.cos(a) * sp; this.vy = Math.sin(a) * sp;
    this.alpha = 255; this.color = color; this.size = 2 + Math.random() * 3; this.g = 400;
  }
  update(dt) { this.vy += this.g * dt; this.x += this.vx * dt; this.y += this.vy * dt; this.alpha -= 600 * dt; return this.alpha > 0; }
}

class ArcadeEleven {
  constructor(host, base, strings) {
    this.host = host; this.base = base; this.strings = strings || {};
    this.towerBase = host.manifest._base + "assets/minigames/tower/";
    this.deck = []; this.grid = new Array(12).fill(null); this.selected = [];
    this.score = 0; this.particles = []; this.phase = "START"; this.timer = 0;
    this.gameTime = 0; this.shake = 0; this.timeBonus = 0; this.totalScore = 0;
    this.imgs = {}; this.back = null; this.sounds = {}; this._startBtn = null;
  }
  t(k, fb) { return this.strings[k] || fb || k; }

  load() {
    const loads = [];
    for (const r of AE_RANKS) for (const s of AE_SUITS) {
      const key = `${r}_${s}`;
      loads.push(loadImage(this.towerBase + `card_${r}_${s}.png`).then(im => { if (im) this.imgs[key] = im; }));
    }
    loads.push(loadImage(this.towerBase + "card_back_red.png").then(im => this.back = im));
    loads.push(loadImage(this.base + "background.png").then(im => this.bg = im));
    const snd = { click: "click.wav", score: "score.mp3", match: "bling5.mp3", win: "victory.mp3", error: "error4.mp3", lose: "ai_action.wav" };
    for (const [k, f] of Object.entries(snd)) { this.sounds[k] = new Audio(this.towerBase + "sounds/" + f); this.sounds[k].preload = "auto"; }
    return Promise.all(loads);
  }
  _sfx(k) { const a = this.sounds[k]; if (!a) return; const n = a.cloneNode(); n.volume = this.host.audio.muted ? 0 : this.host.audio.sfxVol; n.play().catch(() => {}); }

  start() {
    const full = [];
    for (const r of AE_RANKS) for (const s of AE_SUITS) full.push({ rank: r, suit: s, value: AE_VALUES[r], key: `${r}_${s}` });
    for (let i = full.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0;[full[i], full[j]] = [full[j], full[i]]; }
    this.deck = full;
    this._layout();
    this._fill(true);
  }
  _layout() {
    const W = this.host.canvas.clientWidth, H = this.host.canvas.clientHeight;
    const ch = Math.min((H * 0.70) / 3 - 16, (W * 0.85) / 4 * (170 / 120));
    const cw = ch * 120 / 170, gap = ch * 0.12;
    this.cw = cw; this.ch = ch;
    const gridW = 4 * cw + 3 * gap, gridH = 3 * ch + 2 * gap;
    const sx = (W - gridW) / 2 + cw / 2, sy = (H - gridH) / 2 + ch / 2 + 14;
    this.gridPos = [];
    for (let i = 0; i < 12; i++) { const c = i % 4, r = (i / 4) | 0; this.gridPos.push({ x: sx + c * (cw + gap), y: sy + r * (ch + gap) }); }
  }
  _fill(initial) {
    const H = this.host.canvas.clientHeight;
    for (let i = 0; i < 12; i++) {
      if (this.grid[i] == null && this.deck.length) {
        const card = this.deck.shift();
        card.x = this.gridPos[i].x; card.y = H + 200;
        card.tx = this.gridPos[i].x; card.ty = this.gridPos[i].y;
        card.scale = 0.1; card.tscale = 1.0; card.alpha = 0; card.talpha = 255;
        card.selected = false; card.entering = true; card.entryDelay = initial ? i * 0.06 : 0.08; card.errorPulse = 0;
        this.grid[i] = card;
      }
    }
  }
  _gameOver() {
    const present = this.grid.filter(c => c);
    if (!present.length && !this.deck.length) return false;
    const nums = present.filter(c => c.value <= 10);
    for (let i = 0; i < nums.length; i++) for (let j = i + 1; j < nums.length; j++) if (nums[i].value + nums[j].value === 11) return false;
    const figs = new Set(present.filter(c => c.value > 10).map(c => c.value));
    if (figs.has(11) && figs.has(12) && figs.has(13)) return false;
    return true;
  }

  pointer(sx, sy) {
    if (this.phase === "START") { this.phase = "PLAY"; return; }
    if (this.phase === "SUMMARY") { this.host._minigameDone({ success: this.totalScore > 0, score: this.totalScore }); return; }
    if (this.phase !== "PLAY") return;
    for (let i = 0; i < 12; i++) {
      const c = this.grid[i];
      if (c && !c.entering && Math.abs(sx - c.x) <= this.cw / 2 && Math.abs(sy - c.y) <= this.ch / 2) { this._toggle(i); return; }
    }
    this._reset();
  }
  _toggle(idx) {
    const card = this.grid[idx]; if (!card || card.entering) return;
    const pos = this.selected.indexOf(idx);
    if (pos >= 0) { this.selected.splice(pos, 1); card.selected = false; card.tscale = 1.0; }
    else {
      if (this.selected.length >= 3) { this._reset(true); return; }
      this.selected.push(idx); card.selected = true; card.tscale = 1.2; this._sfx("click");
    }
    this._validate();
  }
  _validate() {
    const sel = this.selected.map(i => this.grid[i]).filter(Boolean);
    if (sel.length === 2) {
      const nums = sel.filter(c => c.value <= 10), figs = sel.filter(c => c.value > 10);
      if (nums.length === 2) { if (nums[0].value + nums[1].value === 11) this._resolve(50); else { this._reset(true); this.shake = 5; } }
      else if (nums.length && figs.length) { this._reset(true); this.shake = 5; }
    } else if (sel.length === 3) {
      const vals = new Set(sel.map(c => c.value));
      if (vals.size === 3 && vals.has(11) && vals.has(12) && vals.has(13)) this._resolve(150);
      else { this._reset(true); this.shake = 8; }
    }
  }
  _resolve(points) {
    const color = points > 50 ? "rgb(255,215,0)" : "rgb(0,255,255)";
    for (const idx of this.selected) {
      const c = this.grid[idx];
      if (c) { for (let k = 0; k < 18; k++) this.particles.push(new AEParticle(c.x, c.y, color)); this.grid[idx] = null; }
    }
    this._sfx(points > 50 ? "match" : "score");
    this.score += points; this.selected = []; this._fill(false);
    if (!this.grid.some(c => c) && !this.deck.length) {
      this.phase = "VICTORY"; this.timer = 3.0;
      this.timeBonus = Math.max(0, Math.round((120 - this.gameTime) * 15));
      this.totalScore = this.score + this.timeBonus + 1000; this._sfx("win");
    } else if (this._gameOver()) {
      this.phase = "GAME_OVER"; this.totalScore = 0; this.timer = 4.0; this.shake = 25; this._sfx("lose");
    }
  }
  _reset(error) {
    if (error) this._sfx("error");
    for (const idx of this.selected) { const c = this.grid[idx]; if (c) { c.selected = false; c.tscale = 1.0; if (error) c.errorPulse = 1.0; } }
    this.selected = [];
  }
  key(e, down) { if (down) this.pointer(0, 0); } // qualsiasi tasto: avanza START/SUMMARY

  update(dt) {
    for (const c of this.grid) {
      if (!c) continue;
      if (c.entryDelay > 0) { c.entryDelay -= dt; continue; }
      const lf = 8 * dt;
      c.x += (c.tx - c.x) * lf; c.y += (c.ty - c.y) * lf;
      if (Math.abs(c.x - c.tx) < 0.5 && Math.abs(c.y - c.ty) < 0.5) c.entering = false;
      c.scale += (c.tscale - c.scale) * lf; c.alpha += (c.talpha - c.alpha) * lf;
      if (c.errorPulse > 0) c.errorPulse -= dt * 2.5;
    }
    this.particles = this.particles.filter(p => p.update(dt));
    if (this.phase === "PLAY") this.gameTime += dt;
    else if (this.phase === "VICTORY") { this.timer -= dt; if (this.timer <= 0) this.phase = "SUMMARY"; }
    else if (this.phase === "GAME_OVER") { this.timer -= dt; if (this.timer <= 0) this.host._minigameDone({ success: false, score: 0 }); }
    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 20);
  }

  _drawCard(ctx, c) {
    const w = this.cw * c.scale, h = this.ch * c.scale;
    ctx.save(); ctx.globalAlpha = Math.max(0, Math.min(1, c.alpha / 255));
    const lift = c.selected ? -this.ch * 0.12 : 0;
    if (c.selected) { ctx.shadowColor = "rgba(0,255,255,0.9)"; ctx.shadowBlur = 24; }
    else if (c.errorPulse > 0) { ctx.shadowColor = `rgba(255,40,60,${c.errorPulse})`; ctx.shadowBlur = 24; }
    const im = this.imgs[c.key];
    if (im) ctx.drawImage(im, c.x - w / 2, c.y - h / 2 + lift, w, h);
    else { ctx.fillStyle = "#fff"; this.host._roundRect(ctx, c.x - w / 2, c.y - h / 2 + lift, w, h, 8); ctx.fill(); }
    ctx.restore();
  }

  draw(ctx, W, H) {
    const shx = (Math.random() * 2 - 1) * this.shake, shy = (Math.random() * 2 - 1) * this.shake;
    ctx.save(); ctx.translate(shx, shy);
    if (this.bg) { const s = Math.max(W / this.bg.width, H / this.bg.height); const dw = this.bg.width * s, dh = this.bg.height * s; ctx.drawImage(this.bg, (W - dw) / 2, (H - dh) / 2, dw, dh); ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(-50, -50, W + 100, H + 100); }
    else { ctx.fillStyle = "#101024"; ctx.fillRect(-50, -50, W + 100, H + 100); }
    for (const p of this.particles) { ctx.globalAlpha = Math.max(0, p.alpha / 255); ctx.fillStyle = p.color; ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2); ctx.fill(); }
    ctx.globalAlpha = 1;
    for (const c of this.grid) if (c) this._drawCard(ctx, c);
    ctx.restore();

    // HUD
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#00ffff"; ctx.font = "bold 26px Verdana, sans-serif"; ctx.textAlign = "left";
    ctx.shadowColor = "rgba(0,255,255,0.7)"; ctx.shadowBlur = 12;
    ctx.fillText(this.t("mg_title", "ARCADE ELEVEN").toUpperCase(), 30, 44);
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#ffd700"; ctx.font = "bold 22px Impact, sans-serif"; ctx.textAlign = "right";
    ctx.fillText(`${this.t("arcade_eleven_score", "SCORE")}: ${this.score}`, W - 30, 42);

    if (this.phase === "START") this._overlay(ctx, W, H, this.t("mg_title", "ARCADE ELEVEN"), this.t("arcade_eleven_instructions", ""), this.t("arcade_eleven_click_to_start", "CLICCA PER INIZIARE"), "#00ffff");
    else if (this.phase === "VICTORY" || this.phase === "SUMMARY") this._overlay(ctx, W, H, this.t("arcade_eleven_win", "Vittoria!"), `+${this.timeBonus} bonus tempo`, `${this.totalScore} ${this.t("arcade_eleven_score", "PUNTI")}`, "#46ff8f");
    else if (this.phase === "GAME_OVER") this._overlay(ctx, W, H, this.t("arcade_eleven_game_over", "HAI PERSO"), "", "", "#ff4040");
  }

  _overlay(ctx, W, H, title, sub, cta, color) {
    ctx.fillStyle = "rgba(4,6,14,0.78)"; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";
    ctx.fillStyle = color; ctx.font = "bold 52px Impact, Arial, sans-serif";
    ctx.shadowColor = color; ctx.shadowBlur = 20; ctx.fillText(title, W / 2, H / 2 - 40); ctx.shadowBlur = 0;
    if (sub) { ctx.fillStyle = "#dde"; ctx.font = "18px system-ui, sans-serif"; this._wrap(ctx, sub, W / 2, H / 2 + 6, W * 0.7, 24); }
    if (cta) { ctx.fillStyle = "#fff"; ctx.font = "bold 24px system-ui, sans-serif"; const p = 0.6 + 0.4 * Math.abs(Math.sin(performance.now() / 500)); ctx.globalAlpha = p; ctx.fillText(cta, W / 2, H / 2 + 80); ctx.globalAlpha = 1; }
  }
  _wrap(ctx, text, cx, y, maxW, lh) {
    const words = text.split(" "); let line = "", yy = y;
    for (const w of words) { const t = line ? line + " " + w : w; if (ctx.measureText(t).width > maxW) { ctx.fillText(line, cx, yy); line = w; yy += lh; } else line = t; }
    if (line) ctx.fillText(line, cx, yy);
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["arcade_eleven"] = ArcadeEleven;
