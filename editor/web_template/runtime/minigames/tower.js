// ──────────────────────────────────────────────────────────────────────────
// TowerCard — replica di Card in tower_game.py
// ──────────────────────────────────────────────────────────────────────────
class TowerCard {
  constructor(value, suit, img, backImg) {
    this.value = value;
    this.suit = suit;
    this.img = img;
    this.backImg = backImg;
    this.isFaceUp = false;
    this.pos = { x: 0, y: 0 };
    this.targetPos = { x: 0, y: 0 };
    this.animT = 1.0;
    this.flipT = 1.0;
    this.isFlipping = false;
    this.isVanishing = false;
    this.vanishT = 0.0;
    this.fallVel = 0.0;
  }

  get isRoyal() {
    return this.value > 10;
  }

  startFlip(currentPos, targetPos) {
    this.pos = { x: currentPos.x, y: currentPos.y };
    this.targetPos = { x: targetPos.x, y: targetPos.y };
    this.animT = 0.0;
    this.flipT = 0.0;
    this.isFlipping = true;
  }

  startVanish() {
    this.isVanishing = true;
    this.vanishT = 0.0;
  }

  update(dt, phase) {
    if (phase === "LOSE") {
      this.fallVel += 1200 * dt;
      this.pos.y += this.fallVel * dt;
      return;
    }
    if (this.isVanishing) {
      this.vanishT = Math.min(1.0, this.vanishT + dt * 2.0);
      return;
    }
    if (this.animT < 1.0) {
      this.animT = Math.min(1.0, this.animT + dt * 4.0);
      const ease = 1 - Math.pow(1 - this.animT, 2);
      this.pos.x = this.pos.x + (this.targetPos.x - this.pos.x) * ease;
      this.pos.y = this.pos.y + (this.targetPos.y - this.pos.y) * ease;
    }
    if (this.isFlipping) {
      this.flipT += dt * 3.5;
      if (this.flipT >= 1.0) {
        this.flipT = 1.0;
        this.isFlipping = false;
      }
      if (this.flipT >= 0.5) {
        this.isFaceUp = true;
      }
    }
  }

  draw(ctx, scale, isSel = false, errPulse = 0) {
    const cw = Math.round(95 * scale);
    const ch = Math.round(138 * scale);
    const px = Math.round(this.pos.x);
    const py = Math.round(this.pos.y);

    if (this.isVanishing) {
      const alpha = 1.0 - this.vanishT;
      if (alpha <= 0.001) return;
      const sm = 1.1 + this.vanishT * 0.6;
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(px, py);
      ctx.rotate(this.vanishT * Math.PI);
      ctx.scale(sm, sm);
      ctx.drawImage(this.img, -cw / 2, -ch / 2, cw, ch);
      ctx.fillStyle = `rgba(0, 240, 255, ${0.4 * (1.0 - this.vanishT)})`;
      ctx.fillRect(-cw / 2, -ch / 2, cw, ch);
      ctx.restore();
      return;
    }

    const ay = this.isFlipping ? -70 * Math.sin(this.flipT * Math.PI) * scale : 0;
    const wm = Math.abs(Math.cos(Math.PI * this.flipT));
    const isFace = this.isFlipping ? (this.flipT > 0.5) : this.isFaceUp;
    const texture = isFace ? this.img : this.backImg;

    const dynScale = 1.0 + errPulse * 0.2;

    ctx.save();
    ctx.translate(px, py + Math.round(ay));
    if (dynScale > 1.0) {
      ctx.scale(dynScale, dynScale);
    }
    if (wm > 0) {
      ctx.scale(wm, 1.0);
    }

    ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
    ctx.shadowBlur = 4;
    ctx.shadowOffsetX = 3;
    ctx.shadowOffsetY = 3;

    ctx.drawImage(texture, -cw / 2, -ch / 2, cw, ch);

    if (errPulse > 0) {
      ctx.save();
      ctx.globalCompositeOperation = "source-atop";
      ctx.fillStyle = `rgba(255, 30, 80, ${errPulse * 0.6})`;
      ctx.fillRect(-cw / 2, -ch / 2, cw, ch);
      ctx.restore();
    }

    if (isSel) {
      ctx.strokeStyle = "#00f0ff";
      ctx.lineWidth = 3;
      ctx.strokeRect(-cw / 2, -ch / 2, cw, ch);
      ctx.fillStyle = "rgba(0, 240, 255, 0.3)";
      ctx.fillRect(-cw / 2, -ch / 2, cw, ch);
    }

    ctx.restore();
  }
}

// ──────────────────────────────────────────────────────────────────────────
// TowerGame — Porting 1:1 di TowerGame da Python
// ──────────────────────────────────────────────────────────────────────────
class TowerGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    
    this.deck = [];
    this.grid = {};
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        this.grid[`${r},${c}`] = null;
      }
    }
    this.vanishing = [];
    this.hand = null;
    this.selected = [];
    this.score = 0;
    this.phase = "PLAYING"; // PLAYING, WIN, LOSE, SUMMARY
    
    this.matchingMode = false;
    this.castleAlpha = 0;
    this.castleImg = null;
    this.particles = [];
    this.timerAnim = 0;
    this.phaseBannerT = 0;
    this.loseDelayTimer = 0;
    this.errorPulseT = 0;
    
    this.gameTime = 0.0;
    this.timeBonus = 0;
    this.totalScore = 0;
    
    // Costanti degli slot per Re, Regine, Fanti
    this.K_SLOTS = ["0,0", "0,3", "3,0", "3,3"];
    this.J_SLOTS = ["0,1", "0,2", "3,1", "3,2"];
    this.Q_SLOTS = ["1,0", "2,0", "1,3", "2,3"];
  }

  t(k, fb) { return this.strings[k] || fb || k; }

  _sfx(name) {
    this.host.audio.sfx(name);
  }

  load() {
    // Carica l'immagine del castello vittorioso se disponibile
    this.castleImg = new Image();
    this.castleImg.src = this.base + "castle_victory.png";
    
    // Inizializza il deck precaricando tutte le carte (Ace to King x 4 semi)
    const values = ["ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "jack", "queen", "king"];
    const suits = ["hearts", "diamonds", "clubs", "spades"];
    
    const backImg = new Image();
    backImg.src = this.base + "card_back_red.png";
    
    const promises = [];
    for (let i = 0; i < values.length; i++) {
      const vn = values[i];
      for (const suit of suits) {
        const img = new Image();
        img.src = this.base + `card_${vn}_${suit}.png`;
        const card = new TowerCard(i + 1, suit, img, backImg);
        this.deck.push(card);
        promises.push(new Promise(resolve => {
          img.onload = () => resolve();
          img.onerror = () => resolve(); // fallback di sicurezza
        }));
      }
    }
    
    return Promise.all(promises).then(() => {
      this._shuffle(this.deck);
      this._autoDraw();
    });
  }

  start() {}

  _shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const temp = arr[i];
      arr[i] = arr[j];
      arr[j] = temp;
    }
  }

  _getPos(r, c) {
    const W = 1280;
    const H = 720;
    const cw = 95;
    const ch = 138;
    const spacing = 10;
    
    // Centratura griglia
    const gx = (W - (cw + spacing) * 4) / 2 + (cw / 2);
    const gy = (H - (ch + spacing) * 4) / 2 + (ch / 2) + 50;
    return { x: gx + c * (cw + spacing), y: gy + r * (ch + spacing) };
  }

  _autoDraw() {
    if (this.deck.length === 0 || this.hand || this._isGridFull() || this.phase !== "PLAYING") return;
    this.hand = this.deck.pop();
    const dx = 1280 - 140;
    const dy = 720 - 220;
    const cp = { x: dx + 95 / 2, y: dy + 138 / 2 };
    this.hand.startFlip(cp, { x: dx + 95 / 2, y: dy - 5 });
    this._sfx("click"); // click.wav
  }

  _isGridFull() {
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        if (this.grid[`${r},${c}`] === null) return false;
      }
    }
    return true;
  }

  _placeTest(card, r, c) {
    const key = `${r},${c}`;
    if (this.grid[key]) return false;
    if (!card.isRoyal) return true;
    
    const val = card.value;
    if (val === 13) return this.K_SLOTS.includes(key);
    if (val === 12) return this.Q_SLOTS.includes(key);
    if (val === 11) return this.J_SLOTS.includes(key);
    return false;
  }

  pointer(sx, sy, type) {
    if (this.phase === "SUMMARY") {
      if (type === "down") {
        this.finishGame();
      }
      return;
    }
    
    if (this.phase !== "PLAYING" || this.loseDelayTimer > 0) return;
    if (type !== "down") return;
    
    const scale = Math.min(this.host.canvas.clientWidth / 1280, this.host.canvas.clientHeight / 720);
    const offX = (this.host.canvas.clientWidth - 1280 * scale) / 2;
    const offY = (this.host.canvas.clientHeight - 720 * scale) / 2;
    const mx = (sx - offX) / scale;
    const my = (sy - offY) / scale;
    
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        const p = this._getPos(r, c);
        const cw = 95;
        const ch = 138;
        if (mx >= p.x - cw / 2 && mx <= p.x + cw / 2 && my >= p.y - ch / 2 && my <= p.y + ch / 2) {
          const key = `${r},${c}`;
          if (this.hand) {
            if (this._placeTest(this.hand, r, c)) {
              this.grid[key] = this.hand;
              this.hand.targetPos = p;
              this.hand.animT = 0;
              this.score += 50;
              this.hand = null;
              if (this._isGridFull()) {
                this.matchingMode = true;
                this.phaseBannerT = 2.0;
                this._sfx("levelup"); // bling5.mp3 (match start)
              } else {
                this._autoDraw();
              }
              this._checkWin();
            } else {
              this.errorPulseT = 0.5;
              this._sfx("miss"); // ai_action.wav
            }
            return;
          }
          
          if (this.matchingMode) {
            const card = this.grid[key];
            if (card && !card.isRoyal) {
              if (card.value === 10) {
                card.startVanish();
                this.vanishing.push(card);
                this.grid[key] = null;
                this.score += 150;
                this._sfx("found");
                this.selected = [];
                this._checkMatchingFinished();
                return;
              }
              if (this.selected.includes(key)) {
                this.selected = this.selected.filter(k => k !== key);
              } else {
                this.selected.push(key);
                this._tryScartPairs();
                this._sfx("found");
              }
            }
            return;
          }
        }
      }
    }
  }

  _tryScartPairs() {
    if (this.selected.length === 2) {
      const p1 = this.selected[0];
      const p2 = this.selected[1];
      const v1 = this.grid[p1];
      const v2 = this.grid[p2];
      
      if (v1 && v2 && v1.value + v2.value === 10) {
        v1.startVanish();
        v2.startVanish();
        this.vanishing.push(v1, v2);
        this.grid[p1] = null;
        this.grid[p2] = null;
        this.score += 200;
        this._sfx("found"); // score.mp3
      } else {
        this.errorPulseT = 0.5;
        this._sfx("miss"); // error4.mp3
      }
      this.selected = [];
      this._checkMatchingFinished();
    }
  }

  _checkMatchingFinished() {
    const numerics = [];
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        const key = `${r},${c}`;
        const card = this.grid[key];
        if (card && !card.isRoyal) {
          numerics.push(key);
        }
      }
    }
    
    let moves = false;
    for (const p of numerics) {
      if (this.grid[p].value === 10) moves = true;
    }
    for (let i = 0; i < numerics.length; i++) {
      for (let j = i + 1; j < numerics.length; j++) {
        const p1 = numerics[i];
        const p2 = numerics[j];
        if (this.grid[p1].value + this.grid[p2].value === 10) moves = true;
      }
    }
    
    if (!moves) {
      this.matchingMode = false;
      this._autoDraw();
    }
  }

  _checkWin() {
    let royalsCount = 0;
    const allRoyalsSlots = [...this.K_SLOTS, ...this.Q_SLOTS, ...this.J_SLOTS];
    for (const key of allRoyalsSlots) {
      const card = this.grid[key];
      if (card && card.isRoyal) royalsCount++;
    }
    
    if (royalsCount === 12 && this.deck.length === 0 && !this.hand) {
      let onlyRoyals = true;
      for (let r = 0; r < 4; r++) {
        for (let c = 0; c < 4; c++) {
          const card = this.grid[`${r},${c}`];
          if (card && !card.isRoyal) onlyRoyals = false;
        }
      }
      
      if (onlyRoyals) {
        this.phase = "WIN";
        this.timerAnim = 0;
        this.timeBonus = Math.max(0, Math.floor((180 - this.gameTime) * 10));
        this.totalScore = this.score + this.timeBonus + 1000;
        this._sfx("complete");
        
        // Spawna particelle d'oro
        for (let i = 0; i < 60; i++) {
          this.particles.push({
            x: 640,
            y: 360,
            vx: -300 + Math.random() * 600,
            vy: -500 - Math.random() * 200,
            life: 1.0,
            color: "#ffd700",
            gravity: 800
          });
        }
      }
    }
  }

  update(dt) {
    this.timerAnim += dt;
    if (this.phase === "PLAYING" && this.loseDelayTimer <= 0) {
      this.gameTime += dt;
    }
    
    if (this.phaseBannerT > 0) this.phaseBannerT -= dt;
    if (this.errorPulseT > 0) this.errorPulseT -= dt * 2.0;
    
    if (this.loseDelayTimer > 0) {
      this.loseDelayTimer -= dt;
      if (this.loseDelayTimer <= 0) {
        this.phase = "LOSE";
        this.timerAnim = 0;
        this._sfx("miss");
      }
    }
    
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        const card = this.grid[`${r},${c}`];
        if (card) card.update(dt, this.phase);
      }
    }
    
    if (this.hand) this.hand.update(dt, this.phase);
    
    for (let i = this.vanishing.length - 1; i >= 0; i--) {
      const v = this.vanishing[i];
      v.update(dt);
      if (v.vanishT >= 1.0) {
        this.vanishing.splice(i, 1);
      }
    }
    
    if (this.phase === "PLAYING" && this.loseDelayTimer <= 0) {
      this._evaluateStallo();
    }
    
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.vy += p.gravity * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt * 0.5;
      if (p.life <= 0) {
        this.particles.splice(i, 1);
      }
    }
    
    if (this.phase === "WIN") {
      this.castleAlpha = Math.min(255, this.castleAlpha + dt * 100);
      if (this.castleAlpha >= 255) {
        this.phase = "SUMMARY";
      }
    }
  }

  _evaluateStallo() {
    if (this.deck.length > 0 || this.hand || this.matchingMode) {
      if (this.hand) {
        let canPlace = false;
        for (let r = 0; r < 4; r++) {
          for (let c = 0; c < 4; c++) {
            if (this._placeTest(this.hand, r, c)) canPlace = true;
          }
        }
        if (!canPlace && !this._isGridFull()) {
          this.loseDelayTimer = 2.0;
        }
      }
      return;
    }
    
    if (this.deck.length === 0 && !this.hand) {
      let gridFull = this._isGridFull();
      if (!gridFull || !this.matchingMode) {
        this.loseDelayTimer = 1.0;
      }
    }
  }

  finishGame() {
    const results = {
      success: this.phase !== "LOSE",
      score: this.totalScore
    };
    this.host._minigameDone(results);
  }

  _drawLogoText(ctx, text, x, y, size, color) {
    ctx.save();
    ctx.font = `bold ${Math.round(size)}px Verdana`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    
    // Outline
    ctx.fillStyle = "#000";
    for (const dx of [-1, 1]) {
      for (const dy of [-1, 1]) {
        ctx.fillText(text, x + dx, y + dy);
      }
    }
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
    ctx.restore();
  }

  _drawComicBanner(ctx, text, cx, cy, bannerScale = 1.0, life = 1.0) {
    const t = this.timerAnim;
    let sc = 1.0;
    let rot = 0;
    let alpha = 1.0;
    
    if (life < 2.0) {
      sc = (2.0 - life) < 0.5 ? 0.5 + (2.0 - life) * 3.0 : 2.0 + Math.sin(t * 15) * 0.1;
      rot = Math.sin(t * 10) * 5 * (Math.PI / 180);
      alpha = Math.min(1.0, life * 2);
    } else {
      sc = 1.8 + Math.sin(t * 10) * 0.05;
      rot = Math.sin(t * 5) * 2 * (Math.PI / 180);
    }
    
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rot);
    ctx.scale(sc * bannerScale, sc * bannerScale);
    ctx.globalAlpha = alpha;
    
    ctx.font = "bold 70px Impact";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    
    // Shadow outline
    ctx.fillStyle = "#000";
    for (const dx of [-4, -2, 2, 4]) {
      for (const dy of [-4, -2, 2, 4]) {
        ctx.fillText(text, dx, dy);
      }
    }
    
    let color = (Math.floor(t * 20) % 2 === 0) ? "#ffd700" : "#ff8c00";
    if (text.includes("GAME OVER")) {
      color = (Math.floor(t * 20) % 2 === 0) ? "#ff1e50" : "#ffffff";
    }
    
    ctx.fillStyle = color;
    ctx.fillText(text, 0, 0);
    ctx.restore();
  }

  draw(ctx, W, H) {
    ctx.save();
    const scale = Math.min(W / 1280, H / 720);
    const offX = (W - 1280 * scale) / 2;
    const offY = (H - 720 * scale) / 2;
    
    ctx.fillStyle = "#020208";
    ctx.fillRect(0, 0, W, H);
    
    ctx.translate(offX, offY);
    ctx.scale(scale, scale);
    
    ctx.fillStyle = "#05050c";
    ctx.fillRect(0, 0, 1280, 720);
    
    // HUD
    const titleText = this.t("mg_title", "TOWER OF LONDON").toUpperCase();
    this._drawLogoText(ctx, titleText, 50, 15, 28, "#00f0ff");
    
    // Instructions (Super Slim Column)
    ctx.save();
    ctx.font = "italic 15px Georgia";
    ctx.fillStyle = "#8c8c96";
    ctx.textBaseline = "top";
    
    const lines = [this.t("tower_instr_1"), this.t("tower_instr_2")];
    let yInstr = 75;
    const maxW = 210;
    
    for (const line of lines) {
      const words = line.split(" ");
      let curLine = "";
      for (const w of words) {
        const testLine = curLine + w + " ";
        if (ctx.measureText(testLine).width < maxW) {
          curLine = testLine;
        } else {
          ctx.fillText(curLine, 50, yInstr);
          yInstr += 18;
          curLine = w + " ";
        }
      }
      ctx.fillText(curLine, 50, yInstr);
      yInstr += 25;
    }
    ctx.restore();
    
    // Punti & Deck (Top Right)
    const scoreLabel = this.t("tower_score_label", "SCORE");
    const scoreStr = `${scoreLabel}: ${this.score}`;
    this._drawLogoText(ctx, scoreStr, 1280 - 240, 25, 22, "#ffd700");
    
    const deckLabel = this.t("tower_deck_label", "DECK");
    const deckStr = `${deckLabel}: ${this.deck.length}`;
    this._drawLogoText(ctx, deckStr, 1280 - 240, 60, 22, "#a0a0e0");
    
    // Grid cells
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        const p = this._getPos(r, c);
        const cw = 95;
        const ch = 138;
        
        ctx.save();
        ctx.translate(p.x, p.y);
        
        const glow = this.matchingMode ? Math.abs(Math.sin(this.timerAnim * 5)) : 0;
        const rVal = this.matchingMode ? Math.round(35 + 25 * glow) : 20;
        const gVal = this.matchingMode ? Math.round(35 + 25 * glow) : 20;
        const bVal = this.matchingMode ? Math.round(50 + 40 * glow) : 28;
        
        ctx.fillStyle = `rgb(${rVal}, ${gVal}, ${bVal})`;
        ctx.beginPath();
        ctx.roundRect(-cw / 2, -ch / 2, cw, ch, 10);
        ctx.fill();
        
        if (this.matchingMode) {
          ctx.strokeStyle = "#00f0ff";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.roundRect(-cw / 2, -ch / 2, cw, ch, 10);
          ctx.stroke();
        }
        ctx.restore();
        
        const card = this.grid[`${r},${c}`];
        if (card) {
          const isSel = this.selected.includes(`${r},${c}`);
          card.draw(ctx, 1.0, isSel);
        }
      }
    }
    
    for (const v of this.vanishing) {
      v.draw(ctx, 1.0);
    }
    
    // Deck stack drawing
    if (this.deck.length > 0) {
      const dx = 1280 - 140;
      const dy = 720 - 250;
      const cw = 95;
      const ch = 138;
      
      const stackCount = Math.min(4, this.deck.length);
      for (let i = 0; i < stackCount; i++) {
        ctx.save();
        ctx.translate(dx - i * 2, dy - i * 2);
        // Draw card back
        ctx.drawImage(this.deck[0].backImg, -cw / 2, -ch / 2, cw, ch);
        ctx.restore();
      }
    }
    
    if (this.hand) {
      const ep = this.errorPulseT > 0 ? Math.max(0, this.errorPulseT) : 0;
      this.hand.draw(ctx, 1.0, false, ep);
    }
    
    // Particles
    ctx.save();
    for (const p of this.particles) {
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
    
    // Timer
    if (this.phase === "PLAYING") {
      const tLabel = this.t("tower_time_label", "TIME");
      const tStr = `${tLabel}: ${Math.floor(this.gameTime)}s`;
      this._drawLogoText(ctx, tStr, 1280 - 240, 720 - 60, 22, this.gameTime < 120 ? "#c8c8ff" : "#ff6464");
    }
    
    if (this.phaseBannerT > 0) {
      this._drawComicBanner(ctx, "MATCH PHASE!", 640, 360, 1.0, this.phaseBannerT);
    }
    
    if (this.phase === "LOSE") {
      ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
      ctx.fillRect(0, 0, 1280, 720);
      this._drawComicBanner(ctx, "GAME OVER", 640, 360, 1.0, 1.0);
    }
    
    if (this.castleAlpha > 0 && this.castleImg) {
      ctx.save();
      ctx.globalAlpha = this.castleAlpha / 255;
      ctx.drawImage(this.castleImg, 0, 0, 1280, 720);
      ctx.restore();
      if (this.phase === "WIN") {
        this._drawComicBanner(ctx, this.t("tower_win"), 640, 360, 1.0, 1.0);
      }
    }
    
    if (this.phase === "SUMMARY") {
      this._drawSummary(ctx, scale);
    }
    
    ctx.restore();
  }

  _drawSummary(ctx, scale) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.85)";
    ctx.fillRect(0, 0, 1280, 720);
    this._drawComicBanner(ctx, "RESULTS", 640, 210, 1.0, 2.0);
    
    let y = 310;
    const items = [
      ["BASE SCORE:", this.score],
      ["TIME BONUS:", this.timeBonus],
      ["WIN BONUS:", 1000],
      ["TOTAL:", this.totalScore]
    ];
    
    ctx.save();
    ctx.textAlign = "left";
    
    for (const [label, val] of items) {
      const isTotal = label.includes("TOTAL");
      const c = isTotal ? "#ffd700" : "#ffffff";
      const fs = isTotal ? 32 : 24;
      ctx.font = `bold ${fs}px Impact`;
      
      const text = `${label} ${val}`;
      const textW = ctx.measureText(text).width;
      
      // Shadow
      ctx.fillStyle = "#000";
      ctx.fillText(text, 640 - 200 + 2, y + 2);
      ctx.fillStyle = c;
      ctx.fillText(text, 640 - 200, y);
      y += 50;
    }
    
    ctx.font = "italic 18px Verdana";
    ctx.fillStyle = "#c8c8c8";
    ctx.textAlign = "center";
    ctx.fillText("CLICK TO CONTINUE", 640, 720 - 60);
    ctx.restore();
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["tower"] = TowerGame;
