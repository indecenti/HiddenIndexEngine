// ──────────────────────────────────────────────────────────────────────────
// SlotClassicGame — port JS 1:1 di engine/minigames/slot_classic/slot_classic_game.py.
// ──────────────────────────────────────────────────────────────────────────
const SLOT_PAYTABLE = {
  shiny_star: 500,
  golden_bell: 100,
  red_cherries: 50,
  lucky_seven: 20,
  blue_diamond: 10,
  green_clover: 5,
  grape_bunch: 2
};

class SlotClassicGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    
    this.credits = 2000;
    this.displayCredits = 2000.0;
    this.currentBet = 10;
    this.lastWin = 0;
    this.displayWin = 0.0;
    this.progressiveJackpot = 50000.0;
    
    this.numReels = 3;
    this.reelsPos = [0.0, 0.0, 0.0];
    this.reelsSpeed = [0.0, 0.0, 0.0];
    this.reelsOvershoot = [0.0, 0.0, 0.0];
    this.spinning = [false, false, false];
    this.reelStrips = this._generateStrips();
    this.targetIndices = [0, 0, 0];
    
    this.particles = [];
    this.screenShake = 0.0;
    this.neonCycle = 0.0;
    this.winAnimationTimer = 0.0;
    this.winTextScale = 1.0;
    this.winningLineAlpha = 0;
    this.freeSpinsLeft = 0;
    
    this.symbolsImages = {};
    this.btnScales = { spin: 1.0, plus: 1.0, minus: 1.0, pay: 1.0, exit: 1.0 };
    this.showPaytable = false;
    
    this.spinTimer = 0.0;
    this.tickTimer = 0.0;
    
    // Rettangoli bottoni virtuali nello spazio 1280x720
    this.btnExitRect = null;
    this.btnPayRect = null;
    this.btnBetMinusRect = null;
    this.btnBetPlusRect = null;
    this.btnSpinRect = null;
  }
  t(k, fb) { return this.strings[k] || fb || k; }
  
  _generateStrips() {
    const symbols = Object.keys(SLOT_PAYTABLE);
    const frequencies = [1, 2, 4, 6, 8, 12, 20];
    const strip = [];
    for (let i = 0; i < symbols.length; i++) {
      for (let f = 0; f < frequencies[i]; f++) {
        strip.push(symbols[i]);
      }
    }
    const reels = [];
    for (let r = 0; r < this.numReels; r++) {
      const currentStrip = strip.slice();
      for (let i = currentStrip.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [currentStrip[i], currentStrip[j]] = [currentStrip[j], currentStrip[i]];
      }
      reels.push(currentStrip);
    }
    return reels;
  }
  
  load() {
    const loads = [];
    const assetsMap = {
      shiny_star: "obj_slot_shiny_star.png",
      golden_bell: "obj_slot_golden_bell.png",
      red_cherries: "obj_slot_red_cherries.png",
      lucky_seven: "obj_slot_lucky_7.png",
      blue_diamond: "obj_slot_big_diamond.png",
      green_clover: "obj_slot_four_leaf_clover.png",
      grape_bunch: "obj_slot_purple_grapes.png"
    };
    for (const [key, filename] of Object.entries(assetsMap)) {
      loads.push(loadImage(this.base + "assets/" + filename).then(im => {
        if (im) this.symbolsImages[key] = im;
      }));
    }
    return Promise.all(loads);
  }
  
  _sfx(soundId) {
    // Sfrutta gli SFX globali dell'Engine Web (già caricati ed efficienti)
    const mapping = {
      spin_start: "click",
      reel_stop: "click",
      win_small: "found",
      win_big: "levelup",
      jackpot: "complete",
      click: "click",
      bet_change: "click"
    };
    const mapped = mapping[soundId];
    if (mapped) this.host.audio.sfx(mapped);
  }
  
  start() {
    this.credits = 2000;
    this.displayCredits = 2000.0;
    this.currentBet = 10;
    this.lastWin = 0;
    this.displayWin = 0.0;
    this.freeSpinsLeft = 0;
    this.spinning = [false, false, false];
    this.particles = [];
  }
  
  pointer(sx, sy, type) {
    if (type !== "down") return;
    
    // Adatta sx, sy allo spazio virtuale 1280x720
    const scale = Math.min(this.host.canvas.clientWidth / 1280, this.host.canvas.clientHeight / 720);
    const offX = (this.host.canvas.clientWidth - 1280 * scale) / 2;
    const offY = (this.host.canvas.clientHeight - 720 * scale) / 2;
    const rx = (sx - offX) / scale;
    const ry = (sy - offY) / scale;
    
    if (this.showPaytable) {
      this.showPaytable = false;
      this._sfx("click");
      return;
    }
    
    const hit = (rect) => rect && rx >= rect.x && rx <= rect.x + rect.w && ry >= rect.y && ry <= rect.y + rect.h;
    
    if (hit(this.btnSpinRect)) {
      this.btnScales.spin = 0.85;
      this._startSpin();
    } else if (hit(this.btnBetPlusRect)) {
      this.btnScales.plus = 0.8;
      this._changeBet(10);
    } else if (hit(this.btnBetMinusRect)) {
      this.btnScales.minus = 0.8;
      this._changeBet(-10);
    } else if (hit(this.btnPayRect)) {
      this.btnScales.pay = 0.8;
      this.showPaytable = true;
      this._sfx("click");
    } else if (hit(this.btnExitRect)) {
      this.btnScales.exit = 0.8;
      this._sfx("click");
      this.finishGame();
    }
  }
  
  key(e, down) {
    if (!down) return;
    if (e.key === "Escape") {
      this.finishGame();
    } else if (e.key === " " && !this.showPaytable) {
      this._startSpin();
    }
  }
  
  _changeBet(amount) {
    this.currentBet = Math.max(10, Math.min(500, this.currentBet + amount));
    this._sfx("click");
  }
  
  _startSpin() {
    if (this.credits < this.currentBet && this.freeSpinsLeft <= 0) return;
    
    if (this.spinning.some(x => x)) {
      this._forceStop();
      return;
    }
    
    if (this.freeSpinsLeft > 0) this.freeSpinsLeft -= 1;
    else this.credits -= this.currentBet;
    
    this.displayWin = 0.0;
    this.lastWin = 0;
    this.winAnimationTimer = 0;
    this.progressiveJackpot += this.currentBet * 0.02;
    
    this.targetIndices = [];
    for (let i = 0; i < this.numReels; i++) {
      this.targetIndices.push(Math.floor(Math.random() * this.reelStrips[i].length));
      this.spinning[i] = true;
      this.reelsSpeed[i] = 12.0 + i * 4.0; // Velocità per-frame rulli (simboli per secondo virtuali)
    }
    
    this.spinTimer = 2.5;
    this.tickTimer = 0.0;
    this._sfx("spin_start");
  }
  
  _forceStop() {
    for (let i = 0; i < this.numReels; i++) {
      if (this.spinning[i]) this._stopReel(i);
    }
    this.spinTimer = 0;
  }
  
  update(dt) {
    const lerpSpeed = 8.0;
    this.displayCredits += (this.credits - this.displayCredits) * dt * lerpSpeed;
    this.displayWin += (this.lastWin - this.displayWin) * dt * lerpSpeed;
    
    this.neonCycle += dt * 3.0;
    
    if (this.spinning.some(x => x)) {
      this.spinTimer -= dt;
      this.tickTimer -= dt;
      if (this.tickTimer <= 0) {
        this._sfx("click");
        const activeSpeeds = this.reelsSpeed.filter((s, i) => this.spinning[i]);
        if (activeSpeeds.length > 0) {
          const maxSpeed = Math.max(...activeSpeeds);
          this.tickTimer = Math.max(0.05, 1.0 / maxSpeed);
        } else {
          this.tickTimer = 0.15;
        }
      }
      
      for (let i = 0; i < this.numReels; i++) {
        if (this.spinning[i]) {
          const stopTime = -(i * 0.6);
          const timeUntilStop = this.spinTimer - stopTime;
          if (timeUntilStop < 0.8) {
            this.reelsSpeed[i] *= (1.0 - (dt * 2.5));
            this.reelsSpeed[i] = Math.max(3.0, this.reelsSpeed[i]);
          }
          this.reelsPos[i] = (this.reelsPos[i] + this.reelsSpeed[i] * dt * 4) % this.reelStrips[i].length;
          
          if (timeUntilStop <= 0) {
            this._stopReel(i);
          }
        }
      }
    }
    
    for (let i = 0; i < this.numReels; i++) {
      if (!this.spinning[i]) {
        this.reelsOvershoot[i] *= (1.0 - dt * 15.0);
      }
    }
    
    if (this.screenShake > 0) this.screenShake -= dt * 30;
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx * 60 * dt;
      p.y += p.vy * 60 * dt;
      p.vy += p.gravity * 60 * dt;
      p.angle += p.rotSpeed * 60 * dt;
      if (p.y > 800) this.particles.splice(i, 1);
    }
    
    if (this.winAnimationTimer > 0) {
      this.winAnimationTimer -= dt;
      this.winTextScale = 1.0 + 0.15 * Math.sin(performance.now() * 0.01);
      this.winningLineAlpha = Math.round(150 + 105 * Math.sin(performance.now() * 0.015));
    } else {
      this.winningLineAlpha = 0;
      this.winTextScale = 1.0;
    }
    
    for (const k in this.btnScales) {
      this.btnScales[k] += (1.0 - this.btnScales[k]) * dt * 12;
    }
  }
  
  _stopReel(i) {
    if (!this.spinning[i]) return;
    this.spinning[i] = false;
    this.reelsSpeed[i] = 0;
    this.reelsPos[i] = parseFloat(this.targetIndices[i]);
    this.reelsOvershoot[i] = 0.25;
    this.screenShake = Math.max(this.screenShake, 6.0);
    this._sfx("reel_stop");
    if (i === this.numReels - 1) this._checkWin();
  }
  
  _checkWin() {
    const centerSymbols = [];
    for (let i = 0; i < this.numReels; i++) {
      const idx = (this.targetIndices[i] + 1) % this.reelStrips[i].length;
      centerSymbols.push(this.reelStrips[i][idx]);
    }
    
    if (centerSymbols[0] === centerSymbols[1] && centerSymbols[1] === centerSymbols[2]) {
      const sym = centerSymbols[0];
      let mult = SLOT_PAYTABLE[sym] || 0;
      if (this.freeSpinsLeft > 0) mult *= 2;
      this.lastWin = this.currentBet * mult;
      this.credits += this.lastWin;
      this.winAnimationTimer = 3.5;
      
      if (sym === "shiny_star") {
        this.freeSpinsLeft += 10;
        this.lastWin += Math.floor(this.progressiveJackpot);
        this.credits += Math.floor(this.progressiveJackpot);
        this.progressiveJackpot = 50000.0;
        this._spawnCoins(150);
        this.screenShake = 25.0;
        this._sfx("jackpot");
      } else {
        this._spawnCoins(mult < 50 ? 40 : 100);
        this._sfx(mult >= 50 ? "win_big" : "win_small");
      }
    } else if (centerSymbols[0] === "red_cherries" && centerSymbols[1] === "red_cherries") {
      this.lastWin = this.currentBet;
      this.credits += this.lastWin;
      this.winAnimationTimer = 2.0;
      this._spawnCoins(10);
      this._sfx("win_small");
    }
  }
  
  _spawnCoins(count) {
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: 640,
        y: 360,
        vx: -6 + Math.random() * 12,
        vy: -12 + Math.random() * 8,
        rotSpeed: -8 + Math.floor(Math.random() * 16),
        angle: Math.random() * 360,
        gravity: 0.35,
        color: Math.random() > 0.3 ? [255, 215, 0] : [255, 255, 255]
      });
    }
  }
  
  _getNeonColor() {
    if (this.freeSpinsLeft > 0) {
      return `rgb(255, ${Math.round(150 + 50 * Math.cos(this.neonCycle * 2))}, 0)`;
    }
    return `rgb(${Math.round(100 + 50 * Math.sin(this.neonCycle))}, 50, 255)`;
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
    
    // Sunburst
    this._drawSunburst(ctx);
    this._drawAmbientGlow(ctx);
    
    // Cabinet Shake
    ctx.save();
    if (this.screenShake > 0) {
      const shx = -this.screenShake + Math.random() * this.screenShake * 2;
      const shy = -this.screenShake + Math.random() * this.screenShake * 2;
      ctx.translate(shx, shy);
    }
    
    // Draw Cabinet
    this._drawCabinet(ctx);
    this._drawJackpotPanel(ctx);
    
    // Reels Screen Area
    const cabW = 800, cabH = 480;
    const cabL = 640 - cabW / 2, cabT = 360 - cabH / 2;
    const reelsW = cabW * 0.82, reelsH = cabH * 0.52;
    const rx = 640 - reelsW / 2, ry = 360 - reelsH / 2 - 55;
    
    // Bordo schermo rulli
    ctx.fillStyle = "#000";
    this._roundRect(ctx, rx - 8, ry - 8, reelsW + 16, reelsH + 16, 14);
    ctx.fill();
    ctx.fillStyle = "#0f0f2d";
    this._roundRect(ctx, rx, ry, reelsW, reelsH, 8);
    ctx.fill();
    
    // Draw Reels Stems
    this._drawReels(ctx, rx, ry, reelsW, reelsH);
    this._drawOverlayAndUI(ctx, rx, ry, reelsW, reelsH, cabL, cabT, cabW, cabH);
    
    // Restore Cabinet Shake
    ctx.restore();
    
    // Draw Particles (non vincolate al shake del cabinet)
    this._drawParticles(ctx);
    
    if (this.showPaytable) {
      this._drawPaytable(ctx);
    }
    
    this._drawScanlines(ctx, 1280, 720);
    ctx.restore();
  }
  
  _drawSunburst(ctx) {
    const numRays = 12;
    const rayAngle = 360 / numRays;
    const timeOffset = performance.now() * 0.02 * (Math.PI / 180);
    ctx.fillStyle = "#190a32";
    for (let i = 0; i < numRays; i++) {
      const angle = i * rayAngle * (Math.PI / 180) + timeOffset;
      ctx.beginPath();
      ctx.moveTo(640, 360);
      ctx.lineTo(640 + Math.cos(angle - 0.2) * 1500, 360 + Math.sin(angle - 0.2) * 1500);
      ctx.lineTo(640 + Math.cos(angle + 0.2) * 1500, 360 + Math.sin(angle + 0.2) * 1500);
      ctx.closePath();
      ctx.fill();
    }
  }
  
  _drawAmbientGlow(ctx) {
    const grad = ctx.createRadialGradient(640, 360, 0, 640, 360, 600);
    const neon = this._getNeonColor();
    grad.addColorStop(0, neon.replace("rgb", "rgba").replace(")", ", 0.25)"));
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 1280, 720);
  }
  
  _drawCabinet(ctx) {
    const w = 800, h = 480;
    const x = 640 - w / 2, y = 360 - h / 2;
    
    // Bordo Nero Spesso
    ctx.fillStyle = "#000";
    this._roundRect(ctx, x - 10, y - 10, w + 20, h + 20, 32);
    ctx.fill();
    // Bordo Dorato
    ctx.fillStyle = "#ffd700";
    this._roundRect(ctx, x - 6, y - 6, w + 12, h + 12, 30);
    ctx.fill();
    ctx.fillStyle = "#b48c14";
    this._roundRect(ctx, x - 3, y - 3, w + 6, h + 6, 28);
    ctx.fill();
    // Sfondo Cabinet Grigio Profondo
    ctx.fillStyle = "#0f0f19";
    this._roundRect(ctx, x, y, w, h, 26);
    ctx.fill();
  }
  
  _drawJackpotPanel(ctx) {
    const neon = this._getNeonColor();
    const w = 800 * 0.7, h = 60;
    const x = 640 - w / 2, y = 360 - 240 - 20;
    
    ctx.fillStyle = "#000";
    this._roundRect(ctx, x - 2, y - 2, w + 4, h + 4, 17);
    ctx.fill();
    ctx.fillStyle = "#05050a";
    this._roundRect(ctx, x, y, w, h, 15);
    ctx.fill();
    ctx.strokeStyle = neon;
    ctx.lineWidth = 2;
    ctx.stroke();
    
    ctx.font = "bold 38px Impact, Arial, sans-serif";
    ctx.fillStyle = neon;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`JACKPOT: ${Math.floor(this.progressiveJackpot)}`, 640, y + 30);
  }
  
  _drawReels(ctx, rx, ry, rw, rh) {
    const reelW = rw / 3;
    const rowH = rh / 3;
    
    ctx.save();
    // Clip area rulli
    ctx.beginPath();
    ctx.rect(rx, ry, rw, rh);
    ctx.clip();
    
    for (let i = 0; i < this.numReels; i++) {
      const reelX = rx + i * reelW;
      const visualPos = this.reelsPos[i] + this.reelsOvershoot[i];
      const offY = (visualPos - Math.floor(visualPos)) * rowH;
      const stripIdx = Math.floor(visualPos);
      
      for (let j = -1; j <= 3; j++) {
        const symIdx = (stripIdx + j + this.reelStrips[i].length * 10) % this.reelStrips[i].length;
        const sym = this.reelStrips[i][symIdx];
        const img = this.symbolsImages[sym];
        
        if (img) {
          const fitSize = Math.min(reelW * 0.85, rowH * 0.85);
          const px = reelX + (reelW - fitSize) / 2;
          const py = ry + j * rowH - offY + (rowH - fitSize) / 2;
          
          if (this.reelsSpeed[i] > 5) {
            const stretch = 1.0 + (this.reelsSpeed[i] / 40.0);
            const stretchH = fitSize * stretch;
            ctx.drawImage(img, px, py - (stretchH - fitSize) / 2, fitSize, stretchH);
          } else {
            ctx.drawImage(img, px, py, fitSize, fitSize);
          }
        }
      }
      
      if (i < this.numReels - 1) {
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(reelX + reelW, ry);
        ctx.lineTo(reelX + reelW, ry + rh);
        ctx.stroke();
      }
    }
    ctx.restore();
  }
  
  _drawOverlayAndUI(ctx, rx, ry, rw, rh, cabL, cabT, cabW, cabH) {
    const py = ry + rh / 2;
    if (this.winningLineAlpha > 0) {
      ctx.fillStyle = `rgba(255, 255, 0, ${this.winningLineAlpha / 255 / 2})`;
      ctx.fillRect(rx, py - 12, rw, 24);
    }
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(rx, py);
    ctx.lineTo(rx + rw, py);
    ctx.stroke();
    
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
    
    if (this.winAnimationTimer > 0) {
      this._drawComicWin(ctx, ry - 40);
    }
    
    if (this.credits < 10 && !this.spinning.some(x => x) && this.freeSpinsLeft <= 0) {
      ctx.fillStyle = "rgba(0, 0, 0, 0.9)";
      ctx.fillRect(-200, -200, 1600, 1100);
      this._drawTextComic(ctx, this.t("game_over", "GAME OVER"), "bold 100px Impact", 640, 360, "rgb(255, 50, 50)");
    }
    
    this._drawUI(ctx, cabL, cabT, cabW, cabH);
  }
  
  _drawComicWin(ctx, y) {
    const text = (this.t("win_msg", "VINCI: {amount}")).replace("{amount}", this.lastWin);
    const textScale = this.winTextScale;
    const center = { x: 640, y };
    
    const numPoints = 18;
    const innerR = 115 * textScale;
    const outerR = 180 * textScale;
    
    ctx.save();
    ctx.beginPath();
    for (let i = 0; i < numPoints * 2; i++) {
      const r = i % 2 === 0 ? outerR : innerR;
      const angle = i * (360 / (numPoints * 2)) * (Math.PI / 180);
      const px = center.x + Math.cos(angle) * r;
      const py = center.y + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = "#000";
    ctx.lineWidth = 10;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.fillStyle = "#ffd700";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#000";
    ctx.stroke();
    
    this._drawTextComic(ctx, text, "bold 70px Impact", center.x, center.y, "#fff");
    ctx.restore();
  }
  
  _drawTextComic(ctx, text, fontStyleStr, x, y, colorStr) {
    ctx.save();
    ctx.font = fontStyleStr;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    
    // Disegna contorno nero simulato a doppio anello per evitare bug di strokeText su Chrome
    ctx.fillStyle = "#000";
    
    // Anello esterno (raggio 3, 12 passi)
    const radiusOut = 3;
    const stepsOut = 12;
    for (let i = 0; i < stepsOut; i++) {
      const angle = (i * 2 * Math.PI) / stepsOut;
      const dx = Math.round(Math.cos(angle) * radiusOut);
      const dy = Math.round(Math.sin(angle) * radiusOut);
      ctx.fillText(text, x + dx, y + dy);
    }
    
    // Anello interno (raggio 1.5, 8 passi)
    const radiusIn = 1.5;
    const stepsIn = 8;
    for (let i = 0; i < stepsIn; i++) {
      const angle = (i * 2 * Math.PI) / stepsIn;
      const dx = Math.round(Math.cos(angle) * radiusIn);
      const dy = Math.round(Math.sin(angle) * radiusIn);
      ctx.fillText(text, x + dx, y + dy);
    }
    
    // Testo centrale colorato
    ctx.fillStyle = colorStr;
    ctx.fillText(text, x, y);
    ctx.restore();
  }
  
  _drawUI(ctx, cabL, cabT, cabW, cabH) {
    const labels = ["CREDITI", "PUNTATA", "VINCITA"];
    const values = [`${Math.round(this.displayCredits)}`, `${this.currentBet}`, `${Math.round(this.displayWin)}`].map(String);
    const borderColors = ["#32c864", "#c83232", "#ffd700"];
    const textColors = ["#64ff96", "#ff9696", "#ffffc8"];
    
    const spacing = 15;
    let totalW = 0;
    
    ctx.font = "bold 24px Impact, Arial, sans-serif";
    const itemData = [];
    for (let i = 0; i < 3; i++) {
      const txt = `${labels[i]}: ${values[i]}`;
      const w = ctx.measureText(txt).width + 40;
      itemData.append ? itemData.append({ txt, w }) : itemData.push({ txt, w });
      totalW += w;
    }
    totalW += spacing * 2;
    
    let currX = 640 - totalW / 2;
    const yPos = cabT + cabH - 75 - 20;
    
    for (let i = 0; i < 3; i++) {
      const item = itemData[i];
      let w = item.w;
      let h = 55;
      let rx = currX;
      let ry = yPos;
      
      if (i === 2 && this.winAnimationTimer > 0) {
        const glow = 1.0 + 0.05 * Math.sin(performance.now() * 0.015);
        w *= glow;
        h *= glow;
        rx = rx - (w - item.w) / 2;
        ry = ry - (h - 55) / 2;
      }
      
      const roundedX = Math.round(rx);
      const roundedY = Math.round(ry);
      const roundedW = Math.round(w);
      const roundedH = Math.round(h);
      
      // Sfondo Box
      ctx.fillStyle = "#0f0f19";
      this._roundRect(ctx, roundedX, roundedY, roundedW, roundedH, 10);
      ctx.fill();
      
      // Bordo Box
      ctx.strokeStyle = borderColors[i];
      ctx.lineWidth = 4;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      this._roundRect(ctx, roundedX, roundedY, roundedW, roundedH, 10);
      ctx.stroke();
      
      ctx.fillStyle = textColors[i];
      ctx.fillText(item.txt, roundedX + roundedW / 2, roundedY + roundedH / 2);
      currX += item.w + spacing;
    }
    
    // Bottoni Flat
    const btnY = cabT + cabH + 40;
    
    this.btnExitRect = this._drawBtn(ctx, "ESCI", cabL + 120, btnY, "#8c8c96", "bold 16px Impact", false, "exit");
    this.btnPayRect = this._drawBtn(ctx, "PREMI", cabL + cabW - 120, btnY, "#8c8c96", "bold 16px Impact", false, "pay");
    this.btnBetMinusRect = this._drawBtn(ctx, "-", 640 - 150, btnY, "#e65050", "bold 20px Impact", false, "minus");
    this.btnBetPlusRect = this._drawBtn(ctx, "+", 640 - 90, btnY, "#50e650", "bold 20px Impact", false, "plus");
    
    const spinLabel = this.spinning.some(x => x) ? "STOP" : "GIOCA";
    const spinColor = this.spinning.some(x => x) ? "#3264e6" : "#e63c3c";
    this.btnSpinRect = this._drawBtn(ctx, spinLabel, 640 + 120, btnY, spinColor, "bold 28px Impact", true, "spin");
  }
  
  _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.closePath();
  }

  _drawBtn(ctx, label, cx, cy, color, font, isLarge, bId) {
    const sc = this.btnScales[bId] || 1.0;
    const w = Math.round((isLarge ? 165 : 60) * sc);
    const h = Math.round(60 * sc);
    const rx = Math.round(cx - w / 2);
    const ry = Math.round(cy - h / 2);
    const rad = Math.max(2, Math.round(12 * sc));
    
    // Ombra
    ctx.fillStyle = "#000";
    this._roundRect(ctx, rx + 2, ry + 2, w, h, rad);
    ctx.fill();
    
    // Corpo Bottone
    ctx.fillStyle = color;
    this._roundRect(ctx, rx, ry, w, h, rad);
    ctx.fill();
    
    // Bordo Bottone
    ctx.strokeStyle = "#000";
    ctx.lineWidth = Math.round(4 * sc) || 1;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    this._roundRect(ctx, rx, ry, w, h, rad);
    ctx.stroke();
    
    this._drawTextComic(ctx, label, font, cx, cy, "#fff");
    return { x: rx, y: ry, w, h };
  }
  
  _drawParticles(ctx) {
    for (const p of this.particles) {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.angle * Math.PI / 180);
      ctx.fillStyle = `rgb(${p.color[0]}, ${p.color[1]}, ${p.color[2]})`;
      ctx.beginPath();
      ctx.arc(0, 0, 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
    }
  }
  
  _drawPaytable(ctx) {
    ctx.fillStyle = "rgba(5, 5, 10, 0.96)";
    ctx.fillRect(0, 0, 1280, 720);
    
    this._drawTextComic(ctx, "TABELLA PAGAMENTI", "bold 65px Impact", 640, 80, "#ffd700");
    
    const items = Object.entries(SLOT_PAYTABLE);
    const cols = 3;
    const cardW = 245, cardH = 125;
    const marginX = 35, marginY = 30;
    const startX = 640 - ((cardW + marginX) * cols) / 2 + marginX / 2;
    const startY = 180;
    
    ctx.font = "bold 32px Impact, Arial, sans-serif";
    for (let idx = 0; idx < items.length; idx++) {
      const [sym, mult] = items[idx];
      const r = Math.floor(idx / cols);
      const c = idx % cols;
      const cx = startX + c * (cardW + marginX);
      const cy = startY + r * (cardH + marginY);
      
      ctx.fillStyle = "#000";
      this._roundRect(ctx, cx - 2, cy - 2, cardW + 4, cardH + 4, 17);
      ctx.fill();
      ctx.fillStyle = "#191923";
      this._roundRect(ctx, cx, cy, cardW, cardH, 15);
      ctx.fill();
      
      const img = this.symbolsImages[sym];
      if (img) {
        ctx.drawImage(img, cx + 20, cy + (cardH - 85) / 2, 85, 85);
      }
      
      const valText = sym === "shiny_star" ? "JACKPOT" : `x${mult}`;
      ctx.fillStyle = "#fff";
      ctx.fillText(valText, cx + cardW - 70, cy + cardH / 2);
      
      if (sym === "shiny_star") {
        ctx.font = "bold 14px Arial, sans-serif";
        ctx.fillStyle = "#ffd700";
        ctx.fillText("+10 FREE SPINS", cx + cardW - 70, cy + cardH / 2 + 25);
        ctx.font = "bold 32px Impact, Arial, sans-serif";
      }
    }
    
    ctx.font = "22px Arial, sans-serif";
    ctx.fillStyle = "#8c8c96";
    ctx.textAlign = "center";
    ctx.fillText("Clicca ovunque per tornare al gioco", 640, 720 - 60);
  }
  
  _drawScanlines(ctx, W, H) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
    for (let y = 0; y < H; y += 3) {
      ctx.fillRect(0, y, W, 1);
    }
  }
  
  finishGame() {
    const totalWin = this.credits - 2000;
    const results = {
      success: totalWin > 0,
      score: totalWin > 0 ? totalWin : 0,
      final_credits: this.credits,
      won_jackpot: this.progressiveJackpot === 50000.0 && this.lastWin > 10000,
      total_win: totalWin
    };
    this.host._minigameDone(results);
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["slot_classic"] = SlotClassicGame;
