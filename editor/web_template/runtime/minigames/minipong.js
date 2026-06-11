// ──────────────────────────────────────────────────────────────────────────
// MiniPongGame — port JS 1:1 di engine/minigames/minipong/minipong_game.py.
// ──────────────────────────────────────────────────────────────────────────
const PONG_DIGITS = {
  0: ["XXX", "X.X", "X.X", "X.X", "XXX"],
  1: ["..X", "..X", "..X", "..X", "..X"],
  2: ["XXX", "..X", "XXX", "X..", "XXX"],
  3: ["XXX", "..X", "XXX", "..X", "XXX"],
  4: ["X.X", "X.X", "XXX", "..X", "..X"],
  5: ["XXX", "X..", "XXX", "..X", "XXX"],
  6: ["XXX", "X..", "XXX", "X.X", "XXX"],
  7: ["XXX", "..X", "..X", "..X", "..X"],
  8: ["XXX", "X.X", "XXX", "X.X", "XXX"],
  9: ["XXX", "X.X", "XXX", "..X", "..X"]
};

class MiniPongGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    
    this.phase = "START";
    this.playerScore = 0;
    this.aiScore = 0;
    
    this.p1Y = (720 - 120) / 2;
    this.p2Y = (720 - 120) / 2;
    
    this.ballX = 1280 / 2;
    this.ballY = 720 / 2;
    this.ballVx = 0;
    this.ballVy = 0;
    this.ballSpeed = 600.0;
    
    this.stateTimer = 0.0;
    this.sounds = {};
    this.held = { up: false, down: false };
  }
  t(k, fb) { return this.strings[k] || fb || k; }
  
  load() {
    const loads = [];
    loads.push(loadImage(this.base + "marquee_pong.png").then(im => this.marquee = im));
    const snd = {
      hit: "paddle.wav",
      wall: "wall.wav",
      score: "score.wav"
    };
    for (const [k, f] of Object.entries(snd)) {
      this.sounds[k] = new Audio(this.base + "assets/sounds/" + f);
      this.sounds[k].preload = "auto";
    }
    return Promise.all(loads);
  }
  _sfx(k, vol = 0.3) {
    const a = this.sounds[k];
    if (!a) return;
    const n = a.cloneNode();
    n.volume = (this.host.audio.muted ? 0 : this.host.audio.sfxVol) * vol;
    n.play().catch(() => {});
  }
  
  start() {
    this.playerScore = 0;
    this.aiScore = 0;
    this.phase = "START";
    this._resetBall(true);
  }
  _resetBall(toPlayer) {
    this.ballX = 1280 / 2;
    this.ballY = 720 / 2;
    this.ballSpeed = 600.0;
    const angle = -0.4 + Math.random() * 0.8;
    const direction = toPlayer ? -1 : 1;
    const vx = direction * Math.cos(angle);
    const vy = Math.sin(angle);
    const len = Math.hypot(vx, vy);
    this.ballVx = vx / len;
    this.ballVy = vy / len;
  }
  
  pointer(sx, sy, type) {
    if (this.phase === "START") {
      if (type === "down") this.phase = "PLAY";
    }
    if (this.phase === "END" && this.stateTimer <= 0) {
      const success = this.playerScore >= 11;
      this.host._minigameDone({ success, score: success ? 1000 : 0 });
      return;
    }
    
    // Adatta sx, sy allo spazio virtuale 1280x720 centrato
    const scale = Math.min(this.host.canvas.clientWidth / 1280, this.host.canvas.clientHeight / 720);
    const offY = (this.host.canvas.clientHeight - 720 * scale) / 2;
    const ry = (sy - offY) / scale;
    
    this.p1Y = ry - 120 / 2;
    this._clampPaddles();
  }
  
  key(e, down) {
    if (down && this.phase === "START") {
      this.phase = "PLAY";
    }
    if (down && this.phase === "END" && this.stateTimer <= 0) {
      const success = this.playerScore >= 11;
      this.host._minigameDone({ success, score: success ? 1000 : 0 });
      return;
    }
    
    if (e.key === "ArrowUp") this.held.up = down;
    else if (e.key === "ArrowDown") this.held.down = down;
  }
  
  _clampPaddles() {
    this.p1Y = Math.max(30.0, Math.min(this.p1Y, 720.0 - 120.0));
    this.p2Y = Math.max(30.0, Math.min(this.p2Y, 720.0 - 120.0));
  }
  
  update(dt) {
    if (this.phase === "SCORED") {
      this.stateTimer -= dt;
      if (this.stateTimer <= 0) {
        if (this.playerScore >= 11 || this.aiScore >= 11) {
          this.phase = "END";
          this.stateTimer = 4.0;
        } else {
          this.phase = "PLAY";
        }
      }
      return;
    }
    
    if (this.phase === "PLAY") {
      // Movimento tastiera opzionale per P1
      if (this.held.up) this.p1Y -= 600.0 * dt;
      if (this.held.down) this.p1Y += 600.0 * dt;
      
      this._updatePhysics(dt);
      this._updateAI(dt);
    }
    
    if (this.phase === "END") {
      this.stateTimer -= dt;
      if (this.stateTimer <= 0) {
        const success = this.playerScore >= 11;
        this.host._minigameDone({ success, score: success ? 1000 : 0 });
      }
    }
  }
  
  _updatePhysics(dt) {
    this.ballX += this.ballVx * this.ballSpeed * dt;
    this.ballY += this.ballVy * this.ballSpeed * dt;
    
    if (this.ballY <= 0) {
      this.ballY = 0;
      this.ballVy *= -1;
      this._sfx("wall");
    } else if (this.ballY >= 720 - 20) {
      this.ballY = 720 - 20;
      this.ballVy *= -1;
      this._sfx("wall");
    }
    
    const ballRect = { x: this.ballX, y: this.ballY, w: 20, h: 20 };
    const p1Rect = { x: 60, y: this.p1Y, w: 16, h: 120 };
    const p2Rect = { x: 1280 - 60 - 16, y: this.p2Y, w: 16, h: 120 };
    
    const hit = (r1, r2) => r1.x < r2.x + r2.w && r1.x + r1.w > r2.x && r1.y < r2.y + r2.h && r1.y + r1.h > r2.y;
    
    if (this.ballVx < 0 && hit(ballRect, p1Rect)) {
      this._handlePaddleHit(p1Rect, true);
    } else if (this.ballVx > 0 && hit(ballRect, p2Rect)) {
      this._handlePaddleHit(p2Rect, false);
    }
    
    if (this.ballX < 0) {
      this.aiScore += 1;
      this._triggerScore(true);
    } else if (this.ballX > 1280) {
      this.playerScore += 1;
      this._triggerScore(false);
    }
  }
  
  _handlePaddleHit(paddleRect, isP1) {
    const hitPos = (this.ballY + 10) - (paddleRect.y + 60);
    let relativeHit = hitPos / 60;
    relativeHit = Math.max(-1.0, Math.min(1.0, relativeHit));
    
    const segment = Math.min(7, Math.floor((relativeHit + 1.0) * 4));
    const angles = [
      60 * Math.PI / 180,
      45 * Math.PI / 180,
      30 * Math.PI / 180,
      15 * Math.PI / 180,
      15 * Math.PI / 180,
      30 * Math.PI / 180,
      45 * Math.PI / 180,
      60 * Math.PI / 180
    ];
    
    const angle = angles[segment];
    const dirY = relativeHit < 0 ? -1 : 1;
    const newDirX = isP1 ? 1 : -1;
    
    this.ballVx = newDirX * Math.cos(angle);
    this.ballVy = dirY * Math.sin(angle);
    const len = Math.hypot(this.ballVx, this.ballVy);
    this.ballVx /= len;
    this.ballVy /= len;
    
    this.ballSpeed = Math.min(1800.0, this.ballSpeed + 50.0);
    
    if (isP1) this.ballX = paddleRect.x + paddleRect.w;
    else this.ballX = paddleRect.x - 20;
    
    this._sfx("hit");
  }
  
  _updateAI(dt) {
    const targetCenter = this.ballY + 10;
    const currentCenter = this.p2Y + 60;
    const dist = targetCenter - currentCenter;
    if (Math.abs(dist) > 15) {
      this.p2Y += 700.0 * dt * (dist > 0 ? 1 : -1);
    }
    this._clampPaddles();
  }
  
  _triggerScore(toPlayer) {
    this.phase = "SCORED";
    this.stateTimer = 1.2;
    this._sfx("score");
    this._resetBall(toPlayer);
  }
  
  draw(ctx, W, H) {
    ctx.save();
    const scale = Math.min(W / 1280, H / 720);
    const offX = (W - 1280 * scale) / 2;
    const offY = (H - 720 * scale) / 2;

    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);

    ctx.translate(offX, offY);
    ctx.scale(scale, scale);
    
    // Linea centrale
    ctx.fillStyle = "#fff";
    for (let y = 10; y < 720; y += 30 + 25) {
      ctx.fillRect(1280 / 2 - 6, y, 12, 30);
    }
    
    // Paddle 1
    ctx.fillRect(60, this.p1Y, 16, 120);
    // Paddle 2
    ctx.fillRect(1280 - 60 - 16, this.p2Y, 16, 120);
    // Ball
    ctx.fillRect(this.ballX, this.ballY, 20, 20);
    
    // Punteggi Pixel-Perfect
    this._drawScore(ctx, this.playerScore, 1280 / 2 - 150, true);
    this._drawScore(ctx, this.aiScore, 1280 / 2 + 150, false);
    
    if (this.phase === "START") {
      ctx.fillStyle = "#969696";
      ctx.font = "25px Courier New, monospace";
      ctx.textAlign = "center";
      ctx.fillText(this.t("pong_help", "MUOVI IL MOUSE PER GIOCARE"), 1280 / 2, 720 / 2 + 200);
    }
    
    if (this.phase === "END") {
      this._drawEndOverlay(ctx);
    }
    
    this._drawScanlines(ctx, 1280, 720);
    ctx.restore();
  }
  
  _drawScore(ctx, score, x, alignRight) {
    const s = String(score);
    const pixelSize = 25;
    const digitW = 3 * pixelSize;
    const gap = pixelSize;
    const totalW = s.length * digitW + (s.length - 1) * gap;
    
    let startX = alignRight ? x - totalW : x;
    for (let i = 0; i < s.length; i++) {
      const val = parseInt(s[i]);
      this._drawDigit(ctx, val, startX + i * (digitW + gap), 80, pixelSize);
    }
  }
  
  _drawDigit(ctx, val, x, y, size) {
    const map = PONG_DIGITS[val];
    if (!map) return;
    ctx.fillStyle = "#fff";
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 3; c++) {
        if (map[r][c] === 'X') {
          ctx.fillRect(x + c * size, y + r * size, size, size);
        }
      }
    }
  }
  
  _drawEndOverlay(ctx) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.78)";
    ctx.fillRect(0, 0, 1280, 720);
    
    const success = this.playerScore >= 11;
    const text = this.t(success ? "pong_win" : "pong_lose", success ? "VITTORIA" : "SCONFITTA");
    const color = success ? "rgb(100, 255, 100)" : "rgb(255, 100, 100)";
    
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "bold 80px Courier New, monospace";
    
    const pulsate = Math.abs(Math.sin(performance.now() * 0.005));
    ctx.fillStyle = pulsate > 0.8 ? "#fff" : color;
    ctx.fillText(text.toUpperCase(), 1280 / 2, 720 / 2);
  }
  
  _drawScanlines(ctx, W, H) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
    for (let y = 0; y < H; y += 3) {
      ctx.fillRect(0, y, W, 1);
    }
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["minipong"] = MiniPongGame;
