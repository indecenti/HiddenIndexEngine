// ──────────────────────────────────────────────────────────────────────────
// TetranGame — port JS 1:1 di engine/minigames/tetran/tetran_game.py.
// Usa i PNG reali copiati dall'exporter in assets/minigames/tetran/.
// ──────────────────────────────────────────────────────────────────────────
const TET_GW = 10, TET_GH = 20, TET_TICK = 0.5, TET_COMBO_TIMEOUT = 2.5;
const TETROMINOS = {
  I: { shape: [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]], color: "purple" },
  J: { shape: [[1, 0, 0], [1, 1, 1], [0, 0, 0]], color: "blue" },
  L: { shape: [[0, 0, 1], [1, 1, 1], [0, 0, 0]], color: "green" },
  O: { shape: [[1, 1], [1, 1]], color: "red" },
  S: { shape: [[0, 1, 1], [1, 1, 0], [0, 0, 0]], color: "yellow" },
  T: { shape: [[0, 1, 0], [1, 1, 1], [0, 0, 0]], color: "pink" },
  Z: { shape: [[1, 1, 0], [0, 1, 1], [0, 0, 0]], color: "cyan" },
};
const TET_COLORS = ["blue", "cyan", "green", "pink", "purple", "red", "yellow"];

class TetranGame {
  constructor(host, base, strings) {
    this.host = host; this.base = base; this.strings = strings || {};
    this.grid = Array.from({ length: TET_GH }, () => Array(TET_GW).fill(null));
    this.score = 0; this.timeLeft = 60.0; this.multiplier = 1.0;
    this.comboCount = 0; this.lastClear = 0;
    this.bag = []; this.current = null; this.nextType = this._fromBag(); this.heldType = null; this.canHold = true;
    this.fallTimer = 0; this.gameOver = false; this.floaters = []; this.lastTickSec = 10;
    this.dasTimer = 0; this.dasDir = 0; this.DAS_DELAY = 0.18; this.DAS_REPEAT = 0.05;
    this.overTimer = 0; this.softDrop = false;
    this.imgs = { blocks: {}, ui: {} }; this.sounds = {}; this._btns = [];
  }
  t(k) { return this.strings[k] || k; }
  _now() { return performance.now() / 1000; }

  load() {
    const loads = [];
    const li = (key, path) => loads.push(loadImage(this.base + path).then(im => { if (im) key(im); }));
    for (const c of TET_COLORS) li(im => this.imgs.blocks[c] = im, `assets/blocks/${c}_block/${c}_block.png`);
    li(im => this.imgs.ui.border = im, "assets/UI/border/border.png");
    li(im => this.imgs.ui.hold = im, "assets/UI/hold/hold.png");
    li(im => this.imgs.ui.next = im, "assets/UI/next/next.png");
    li(im => this.imgs.bg = im, "assets/background/background.png");
    for (const s of ["click", "drop", "rotation", "hold", "no_hold", "line_clear", "tetris_clear", "game_over"]) {
      this.sounds[s] = new Audio(this.base + `assets/sound/${s}.mp3`); this.sounds[s].preload = "auto";
    }
    return Promise.all(loads);
  }
  _sfx(k) {
    const a = this.sounds[k]; if (!a) return;
    const n = a.cloneNode(); n.volume = this.host.audio.muted ? 0 : this.host.audio.sfxVol; n.play().catch(() => {});
  }
  start() { this.spawn(); }

  _fromBag() {
    if (!this.bag.length) { this.bag = Object.keys(TETROMINOS); for (let i = this.bag.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0;[this.bag[i], this.bag[j]] = [this.bag[j], this.bag[i]]; } }
    return this.bag.pop();
  }
  _pickSpecial() { const r = Math.random() * 100; return r < 75 ? "none" : r < 85 ? "T1" : r < 95 ? "T2" : "T3"; }
  spawn() {
    const type = this.nextType; this.nextType = this._fromBag();
    const d = TETROMINOS[type];
    this.current = { type, shape: d.shape.map(r => r.slice()), color: d.color, x: (TET_GW / 2 | 0) - (d.shape[0].length / 2 | 0), y: 0, special: this._pickSpecial() };
    if (this.collision(this.current.x, this.current.y)) { this._sfx("game_over"); this.gameOver = true; }
  }
  collision(nx, ny, shape) {
    shape = shape || this.current.shape;
    for (let y = 0; y < shape.length; y++) for (let x = 0; x < shape[y].length; x++) {
      if (shape[y][x]) { const tx = nx + x, ty = ny + y; if (tx < 0 || tx >= TET_GW || ty >= TET_GH) return true; if (ty >= 0 && this.grid[ty][tx]) return true; }
    }
    return false;
  }
  rotate() {
    if (this.current.type === "O") return;
    const old = this.current.shape;
    const ns = old[0].map((_, i) => old.map(r => r[i]).reverse());
    this.current.shape = ns;
    for (const dx of [0, -1, 1, -2, 2]) { if (!this.collision(this.current.x + dx, this.current.y)) { this.current.x += dx; this._sfx("rotation"); return; } }
    this.current.shape = old;
  }
  moveH(dx) { if (this.current && !this.collision(this.current.x + dx, this.current.y)) { this.current.x += dx; this._sfx("click"); } }
  hardDrop() { while (!this.collision(this.current.x, this.current.y + 1)) { this.current.y++; this.score += 2; } this.lock(); this._sfx("drop"); }
  hold() {
    if (!this.canHold) { this._sfx("no_hold"); return; }
    const cur = this.current.type;
    if (this.heldType == null) { this.heldType = cur; this.spawn(); }
    else { const nt = this.heldType; this.heldType = cur; const d = TETROMINOS[nt]; this.current = { type: nt, shape: d.shape.map(r => r.slice()), color: d.color, x: (TET_GW / 2 | 0) - (d.shape[0].length / 2 | 0), y: 0, special: "none" }; }
    this.canHold = false; this._sfx("hold");
  }
  lock() {
    for (let y = 0; y < this.current.shape.length; y++) for (let x = 0; x < this.current.shape[y].length; x++) {
      if (this.current.shape[y][x]) { const ty = this.current.y + y, tx = this.current.x + x; if (ty >= 0) this.grid[ty][tx] = { color: this.current.color, special: this.current.special }; }
    }
    this.clearLines(); this.spawn(); this.canHold = true;
  }
  clearLines() {
    const full = []; for (let y = 0; y < TET_GH; y++) if (this.grid[y].every(c => c)) full.push(y);
    if (!full.length) { if (this._now() - this.lastClear > TET_COMBO_TIMEOUT) this.comboCount = 0; return; }
    const extra = new Set();
    for (const y of full) for (let x = 0; x < TET_GW; x++) {
      const b = this.grid[y][x];
      if (b.special === "T1") { this.timeLeft += 2; this._float("+2 SEC", x, y, "rgb(0,255,100)"); }
      else if (b.special === "T2") { this.multiplier += 0.2; this._float("MULT UP!", x, y, "rgb(255,215,0)"); }
      else if (b.special === "T3") { if (y > 0) extra.add(y - 1); if (y < TET_GH - 1) extra.add(y + 1); this._float("BOMB!", x, y, "rgb(255,80,0)"); }
    }
    const finalSet = [...new Set([...full, ...extra])].sort((a, b) => b - a);
    const n = finalSet.length;
    const basePts = { 1: 100, 2: 300, 3: 500, 4: 800 }[Math.min(4, n)] || n * 200;
    const gain = Math.round(basePts * this.multiplier);
    this.score += gain; this.comboCount++; this.multiplier += n * 0.05; this.lastClear = this._now();
    this._float(`+${gain}`, TET_GW / 2 | 0, full[0], "rgb(255,255,255)");
    for (const y of finalSet) { this.grid.splice(y, 1); this.grid.unshift(Array(TET_GW).fill(null)); }
    this._sfx(n >= 4 ? "tetris_clear" : "line_clear");
  }
  _float(text, x, y, color) { this.floaters.push({ text, x, y, color, life: 1.5 }); }

  key(e, down) {
    if (this.gameOver) { if (down && this.overTimer > 1.0) this.host._minigameDone({ success: this.score > 5000, score: this.score }); return; }
    if (down) {
      if (e.key === "ArrowLeft") { this.dasDir = -1; this.dasTimer = 0; this.moveH(-1); }
      else if (e.key === "ArrowRight") { this.dasDir = 1; this.dasTimer = 0; this.moveH(1); }
      else if (e.key === "ArrowUp") this.rotate();
      else if (e.key === "ArrowDown") this.softDrop = true;
      else if (e.key === " ") this.hardDrop();
      else if (e.key === "c" || e.key === "C") this.hold();
    } else {
      if (e.key === "ArrowLeft" && this.dasDir === -1) this.dasDir = 0;
      else if (e.key === "ArrowRight" && this.dasDir === 1) this.dasDir = 0;
      else if (e.key === "ArrowDown") this.softDrop = false;
    }
  }
  pointer(sx, sy) {
    if (this.gameOver) { if (this.overTimer > 1.0) this.host._minigameDone({ success: this.score > 5000, score: this.score }); return; }
    for (const b of this._btns) {
      if (sx >= b.x && sx <= b.x + b.w && sy >= b.y && sy <= b.y + b.h) {
        if (b.a === "left") this.moveH(-1);
        else if (b.a === "right") this.moveH(1);
        else if (b.a === "rotate") this.rotate();
        else if (b.a === "down") { this.softDrop = true; setTimeout(() => this.softDrop = false, 250); }
        else if (b.a === "drop") this.hardDrop();
        else if (b.a === "hold") this.hold();
        else if (b.a === "quit") this.host._minigameDone({ success: this.score > 5000, score: this.score });
        return;
      }
    }
  }

  update(dt) {
    if (this.gameOver) { this.overTimer += dt; return; }
    this.timeLeft -= dt;
    if (this.timeLeft <= 0) { this.gameOver = true; return; }
    if (this.timeLeft < 10.5) { const s = Math.ceil(this.timeLeft); if (s < this.lastTickSec) { this._sfx("click"); this.lastTickSec = s; } }
    let tick = TET_TICK * (0.2 + 0.8 * (Math.max(0, this.timeLeft) / 60));
    if (this.softDrop) tick = Math.min(tick, 0.05);
    this.fallTimer += dt;
    if (this.fallTimer >= tick) {
      if (!this.collision(this.current.x, this.current.y + 1)) { this.current.y++; if (this.softDrop) this.score += 1; }
      else this.lock();
      this.fallTimer = 0;
    }
    if (this._now() - this.lastClear > TET_COMBO_TIMEOUT) this.multiplier = Math.max(1, this.multiplier - dt * 0.05);
    if (this.dasDir !== 0) { this.dasTimer += dt; if (this.dasTimer >= this.DAS_DELAY + this.DAS_REPEAT) { this.moveH(this.dasDir); this.dasTimer = this.DAS_DELAY; } }
    for (let i = this.floaters.length - 1; i >= 0; i--) { this.floaters[i].y -= dt * 1.0; this.floaters[i].life -= dt; if (this.floaters[i].life <= 0) this.floaters.splice(i, 1); }
  }

  _drawBlock(ctx, x, y, color, ox, oy, bs, alpha) {
    if (y < 0) return;
    const im = this.imgs.blocks[color];
    ctx.save(); if (alpha != null && alpha < 1) ctx.globalAlpha = alpha;
    if (im) ctx.drawImage(im, ox + x * bs, oy + y * bs, bs, bs);
    else { ctx.fillStyle = color; ctx.fillRect(ox + x * bs + 1, oy + y * bs + 1, bs - 2, bs - 2); }
    ctx.restore();
  }
  _drawShape(ctx, shape, color, px, py, ox, oy, bs, alpha) {
    for (let y = 0; y < shape.length; y++) for (let x = 0; x < shape[y].length; x++) if (shape[y][x]) this._drawBlock(ctx, px + x, py + y, color, ox, oy, bs, alpha);
  }
  _drawPreview(ctx, type, px, py, bs) {
    const d = TETROMINOS[type]; const im = this.imgs.blocks[d.color];
    for (let y = 0; y < d.shape.length; y++) for (let x = 0; x < d.shape[y].length; x++) if (d.shape[y][x]) { if (im) ctx.drawImage(im, px + x * bs, py + y * bs, bs, bs); }
  }
  _panel(ctx, x, y, w, h) {
    ctx.fillStyle = "rgba(20,20,30,0.75)"; this.host._roundRect(ctx, x, y, w, h, 10); ctx.fill();
    ctx.strokeStyle = "rgba(120,120,160,0.9)"; ctx.lineWidth = 2; this.host._roundRect(ctx, x, y, w, h, 10); ctx.stroke();
  }

  draw(ctx, W, H) {
    ctx.fillStyle = "#0f0f12"; ctx.fillRect(0, 0, W, H);
    if (this.imgs.bg) { const s = Math.max(W / this.imgs.bg.width, H / this.imgs.bg.height); const dw = this.imgs.bg.width * s, dh = this.imgs.bg.height * s; ctx.globalAlpha = 0.25; ctx.drawImage(this.imgs.bg, (W - dw) / 2, (H - dh) / 2, dw, dh); ctx.globalAlpha = 1; }

    const ctrlH = 86;
    const bs = Math.floor(Math.min((H - 110 - ctrlH) / TET_GH, (W * 0.46) / TET_GW));
    const gw = TET_GW * bs, gh = TET_GH * bs;
    const ox = Math.round((W - gw) / 2), oy = Math.round((H - ctrlH - gh) / 2 + 10);

    if (this.imgs.ui.border) ctx.drawImage(this.imgs.ui.border, ox - 10, oy - 10, gw + 20, gh + 20);
    else { ctx.strokeStyle = "rgba(120,120,160,0.8)"; ctx.lineWidth = 3; ctx.strokeRect(ox - 4, oy - 4, gw + 8, gh + 8); }

    // ghost
    if (this.current) { let gy = this.current.y; while (!this.collision(this.current.x, gy + 1)) gy++; this._drawShape(ctx, this.current.shape, this.current.color, this.current.x, gy, ox, oy, bs, 0.25); }
    // grid
    for (let y = 0; y < TET_GH; y++) for (let x = 0; x < TET_GW; x++) if (this.grid[y][x]) this._drawBlock(ctx, x, y, this.grid[y][x].color, ox, oy, bs, 1);
    // pezzo
    if (this.current) this._drawShape(ctx, this.current.shape, this.current.color, this.current.x, this.current.y, ox, oy, bs, 1);
    // floaters
    ctx.font = "bold 18px Arial, sans-serif"; ctx.textAlign = "center";
    for (const ft of this.floaters) { ctx.globalAlpha = Math.max(0, ft.life / 1.5); ctx.fillStyle = ft.color; ctx.fillText(ft.text, ox + ft.x * bs, oy + ft.y * bs); }
    ctx.globalAlpha = 1;

    this._drawDash(ctx, W, H, ox, oy, gw, gh, bs);
    this._drawControls(ctx, W, H, ctrlH);

    if (this.gameOver) this._drawOver(ctx, W, H);
  }

  _drawDash(ctx, W, H, ox, oy, gw, gh, bs) {
    const dashW = 180, gap = 24;
    const leftX = ox - dashW - gap, rightX = ox + gw + gap;
    const sideOk = leftX > 6 && rightX + dashW < W - 6;
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    if (sideOk) {
      // Sinistra: tempo + hold
      this._panel(ctx, leftX, oy, dashW, 64);
      const danger = this.timeLeft < 10;
      ctx.fillStyle = danger ? "#ff5050" : "#fff"; ctx.font = "bold 26px Arial"; ctx.textAlign = "center";
      ctx.fillText((this.t("time_left") || "Tempo: {time}s").replace("{time}", Math.max(0, Math.ceil(this.timeLeft))), leftX + dashW / 2, oy + 40);
      this._panel(ctx, leftX, oy + 80, dashW, 150);
      ctx.fillStyle = "#9aa"; ctx.font = "bold 16px Arial"; ctx.textAlign = "left"; ctx.fillText("HOLD", leftX + 16, oy + 104);
      if (this.heldType) this._drawPreview(ctx, this.heldType, leftX + 40, oy + 120, bs * 0.6);
      // Destra: score + mult + next
      this._panel(ctx, rightX, oy, dashW, 108);
      ctx.fillStyle = "#c8c8f0"; ctx.font = "bold 16px Arial"; ctx.fillText("SCORE", rightX + 16, oy + 26);
      ctx.fillStyle = "#fff"; ctx.font = "bold 26px Arial"; ctx.fillText(String(this.score), rightX + 16, oy + 58);
      ctx.fillStyle = "#ffae00"; ctx.font = "bold 22px Arial"; ctx.fillText("x" + (Math.round(this.multiplier * 10) / 10), rightX + 16, oy + 92);
      this._panel(ctx, rightX, oy + 124, dashW, 150);
      ctx.fillStyle = "#9aa"; ctx.font = "bold 16px Arial"; ctx.fillText("NEXT", rightX + 16, oy + 148);
      this._drawPreview(ctx, this.nextType, rightX + 40, oy + 164, bs * 0.6);
      if (this.comboCount > 1) { this._panel(ctx, rightX, oy + 284, dashW, 50); ctx.fillStyle = "#00ffb4"; ctx.font = "bold 20px Arial"; ctx.textAlign = "center"; ctx.fillText("COMBO x" + this.comboCount, rightX + dashW / 2, oy + 316); }
    } else {
      // Compatto in alto (mobile)
      ctx.fillStyle = "rgba(10,12,20,0.7)"; ctx.fillRect(0, 0, W, 40);
      ctx.fillStyle = this.timeLeft < 10 ? "#ff5050" : "#fff"; ctx.font = "bold 20px Arial"; ctx.textAlign = "left";
      ctx.fillText("⏱ " + Math.max(0, Math.ceil(this.timeLeft)) + "s", 12, 27);
      ctx.textAlign = "center"; ctx.fillStyle = "#fff"; ctx.fillText("SCORE " + this.score, W / 2, 27);
      ctx.textAlign = "right"; ctx.fillStyle = "#ffae00"; ctx.fillText("x" + (Math.round(this.multiplier * 10) / 10), W - 12, 27);
    }
  }

  _drawControls(ctx, W, H, ctrlH) {
    const y = H - ctrlH + 8, h = ctrlH - 16;
    const labels = [["left", "◀"], ["right", "▶"], ["rotate", "⟳"], ["down", "▼"], ["drop", "⤓"], ["hold", "H"]];
    const n = labels.length, gap = 8, bw = Math.min(96, (W - 24 - gap * (n - 1)) / n);
    const totW = n * bw + (n - 1) * gap, x0 = (W - totW) / 2;
    this._btns = [];
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    labels.forEach(([a, lbl], i) => {
      const x = x0 + i * (bw + gap);
      ctx.fillStyle = "rgba(60,70,110,0.6)"; this.host._roundRect(ctx, x, y, bw, h, 10); ctx.fill();
      ctx.strokeStyle = "rgba(160,180,255,0.5)"; ctx.lineWidth = 1.5; this.host._roundRect(ctx, x, y, bw, h, 10); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.font = "bold 24px system-ui, sans-serif"; ctx.fillText(lbl, x + bw / 2, y + h / 2 + 1);
      this._btns.push({ a, x, y, w: bw, h });
    });
    ctx.textBaseline = "alphabetic";
  }

  _drawOver(ctx, W, H) {
    ctx.fillStyle = "rgba(0,0,0,0.8)"; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center"; ctx.fillStyle = "#ff3232"; ctx.font = "bold 56px Arial";
    ctx.fillText(this.t("game_over") || "GAME OVER", W / 2, H / 2 - 60);
    ctx.fillStyle = "#fff"; ctx.font = "bold 30px Arial";
    ctx.fillText((this.t("final_score") || "Punteggio: {score}").replace("{score}", this.score), W / 2, H / 2);
    ctx.fillStyle = "#bbb"; ctx.font = "18px Arial";
    ctx.fillText(this.t("mg_tap_exit") || (this.score > 5000 ? "Tap per uscire (vittoria!)" : "Tap per uscire"), W / 2, H / 2 + 56);
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["tetran"] = TetranGame;
