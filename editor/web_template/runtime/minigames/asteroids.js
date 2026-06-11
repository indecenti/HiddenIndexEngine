// ──────────────────────────────────────────────────────────────────────────
// AsteroidsGame — port JS di engine/minigames/asteroids (vettoriale, 1280x720
// con wrap-around, scalato in letterbox sul canvas). Suoni .wav reali.
// ──────────────────────────────────────────────────────────────────────────
const AST = { REF_W: 1280, REF_H: 720, SHIP_R: 15, THRUST: 600, ROT: 280, DRAG: 0.99, MAXV: 500, INVUL: 3.0, BULLET_V: 800, BULLET_LIFE: 1.0, BULLET_MAX: 4, EXTRA_LIFE: 10000, LIVES: 3 };
const AST_TEMPLATES = [
  [[0.5, -1], [1, -0.5], [1, 0.2], [0.3, 1], [-0.3, 1], [-1, 0.5], [-1, -0.2], [-0.5, -1]],
  [[1, -0.3], [1, 0.3], [0.5, 1], [-0.2, 1], [-1, 0.3], [-1, -0.3], [-0.5, -1], [0.2, -1]],
  [[1, -0.5], [0.5, 0.2], [1, 0.5], [0.3, 1], [-0.2, 0.5], [-1, 1], [-1, -0.5], [-0.5, -1], [0.2, -0.5]],
  [[1, -0.5], [1, 0.5], [0.2, 0.3], [0.5, 1], [-0.5, 1], [-0.2, 0.5], [-1, 0.5], [-1, -0.5], [-0.5, -1], [0.5, -0.3]],
];
const _rnd = (a, b) => a + Math.random() * (b - a);
function _wrap(p) { p.x = ((p.x % AST.REF_W) + AST.REF_W) % AST.REF_W; p.y = ((p.y % AST.REF_H) + AST.REF_H) % AST.REF_H; }

class AsteroidsGame {
  constructor(host, base, strings) {
    this.host = host; this.base = base; this.strings = strings || {};
    this.reset();
    this.imgs = {}; this.sounds = {};
    this.held = { left: false, right: false, up: false, fire: false };
    this.mouseFire = 0; this._btns = [];
  }
  t(k, fb) { return this.strings[k] || fb || k; }
  reset() {
    this.ship = null; this.asteroids = []; this.bullets = []; this.ufos = []; this.fragments = []; this.particles = [];
    this.score = 0; this.lastExtra = 0; this.lives = AST.LIVES; this.level = 0; this.phase = "START";
    this.stateTimer = 0; this.beatTimer = 1; this.beatState = 0; this.ufoTimer = 15; this.thrustSfx = 0;
  }
  load() {
    const snd = ["fire", "thrust", "bang_large", "bang_medium", "bang_small", "beat1", "beat2", "extra_ship"];
    for (const s of snd) { this.sounds[s] = new Audio(this.base + `assets/sounds/${s}.wav`); this.sounds[s].preload = "auto"; }
    return Promise.resolve();
  }
  _sfx(k, vol) { const a = this.sounds[k]; if (!a) return; const n = a.cloneNode(); n.volume = (this.host.audio.muted ? 0 : this.host.audio.sfxVol) * (vol != null ? vol : 0.5); n.play().catch(() => {}); }
  start() { this.reset(); this._spawnLevel(); }

  _spawnLevel() {
    this.level++; const n = 4 + this.level; this.asteroids = [];
    for (let i = 0; i < n; i++) {
      let x, y;
      do { x = _rnd(0, AST.REF_W); y = _rnd(0, AST.REF_H); } while (Math.hypot(x - AST.REF_W / 2, y - AST.REF_H / 2) <= 200);
      this.asteroids.push(this._mkAsteroid(x, y, 3));
    }
  }
  _mkAsteroid(x, y, size) {
    const R = size === 3 ? 50 : size === 2 ? 25 : 12;
    const spd = size === 3 ? _rnd(80, 150) : size === 2 ? _rnd(150, 220) : _rnd(220, 320);
    const a = _rnd(0, Math.PI * 2);
    const pts = size === 3 ? 20 : size === 2 ? 50 : 100;
    const tpl = AST_TEMPLATES[(Math.random() * AST_TEMPLATES.length) | 0];
    const poly = tpl.map(([px, py]) => [px * R + _rnd(-R * 0.1, R * 0.1), py * R + _rnd(-R * 0.1, R * 0.1)]);
    return { kind: "ast", size, x, y, vx: Math.cos(a) * spd, vy: Math.sin(a) * spd, r: R, angle: 0, points: pts, poly };
  }
  _mkShip() { return { x: AST.REF_W / 2, y: AST.REF_H / 2, vx: 0, vy: 0, r: AST.SHIP_R, angle: -90, thrusting: false, invul: AST.INVUL }; }
  _mkBullet(x, y, angle, owner) { const r = angle * Math.PI / 180; return { kind: "bul", x, y, vx: Math.cos(r) * AST.BULLET_V, vy: Math.sin(r) * AST.BULLET_V, r: 2, life: AST.BULLET_LIFE, owner }; }
  _mkUfo(size) {
    const y = _rnd(50, AST.REF_H - 50), side = Math.random() < 0.5 ? -1 : 1, x = side === 1 ? 0 : AST.REF_W;
    const spd = size === 2 ? 150 : 250;
    return { kind: "ufo", size, x, y, vx: side * spd, vy: 0, r: size === 2 ? 20 : 10, points: size === 2 ? 200 : 1000, fireTimer: _rnd(1, 2), dirTimer: _rnd(1, 3) };
  }

  pointer(sx, sy, type) {
    if (type === "up") { this.held.left = this.held.right = this.held.up = this.held.fire = false; return; }
    if (this.phase === "START") { this.phase = "PLAY"; this.ship = this._mkShip(); return; }
    if (this.phase === "GAMEOVER") { this.host._minigameDone({ success: this.score > 0, score: this.score }); return; }
    if (this.phase !== "PLAY") return;
    for (const b of this._btns) {
      if (sx >= b.x && sx <= b.x + b.w && sy >= b.y && sy <= b.y + b.h) {
        if (b.a === "fire") { this._fire(); this.held.fire = true; }
        else this.held[b.a] = true;
        return;
      }
    }
    this._fire(); // tap nell'area di gioco = sparo
  }
  key(e, down) {
    if (down && (this.phase === "START")) { this.phase = "PLAY"; this.ship = this._mkShip(); return; }
    if (down && this.phase === "GAMEOVER") { this.host._minigameDone({ success: this.score > 0, score: this.score }); return; }
    if (this.phase !== "PLAY") return;
    if (e.key === "ArrowLeft") this.held.left = down;
    else if (e.key === "ArrowRight") this.held.right = down;
    else if (e.key === "ArrowUp") this.held.up = down;
    else if (e.key === " " && down) this._fire();
    else if ((e.key === "h" || e.key === "H") && down) this._hyper();
  }
  _fire() {
    if (!this.ship || this.bullets.filter(b => b.owner === "ship").length >= AST.BULLET_MAX) return;
    const r = this.ship.angle * Math.PI / 180;
    this.bullets.push(this._mkBullet(this.ship.x + Math.cos(r) * 20, this.ship.y + Math.sin(r) * 20, this.ship.angle, "ship"));
    this._sfx("fire");
  }
  _hyper() { if (!this.ship) return; this.ship.x = _rnd(0, AST.REF_W); this.ship.y = _rnd(0, AST.REF_H); this.ship.vx = this.ship.vy = 0; if (Math.random() < 0.1) this._shipDeath(); }

  update(dt) {
    dt = Math.min(dt, 0.05);
    for (const b of this.bullets) { b.x += b.vx * dt; b.y += b.vy * dt; _wrap(b); b.life -= dt; if (b.life <= 0) b.dead = true; }
    this.bullets = this.bullets.filter(b => !b.dead);
    for (const f of this.fragments) { f.x += f.vx * dt; f.y += f.vy * dt; _wrap(f); f.angle += f.rot * dt; f.life -= dt; }
    this.fragments = this.fragments.filter(f => f.life > 0);
    for (const p of this.particles) { p.x += p.vx * dt; p.y += p.vy * dt; _wrap(p); p.life -= dt; }
    this.particles = this.particles.filter(p => p.life > 0);

    if (this.phase === "PLAY") this._play(dt);
    else {
      this.stateTimer -= dt;
      for (const a of this.asteroids) { a.x += a.vx * dt; a.y += a.vy * dt; _wrap(a); }
      if (this.phase === "DYING" && this.stateTimer <= 0) {
        if (this.lives > 0) { this.phase = "PLAY"; this.ship = this._mkShip(); }
        else { this.phase = "GAMEOVER"; this.stateTimer = 6.0; }
      } else if (this.phase === "GAMEOVER" && this.stateTimer <= 0) {
        this.host._minigameDone({ success: this.score > 0, score: this.score });
      }
    }
  }
  _play(dt) {
    const sh = this.ship; if (!sh) return;
    if (this.held.left) sh.angle -= AST.ROT * dt;
    if (this.held.right) sh.angle += AST.ROT * dt;
    sh.thrusting = this.held.up;
    if (sh.thrusting) {
      const r = sh.angle * Math.PI / 180;
      sh.vx += Math.cos(r) * AST.THRUST * dt; sh.vy += Math.sin(r) * AST.THRUST * dt;
      const sp = Math.hypot(sh.vx, sh.vy); if (sp > AST.MAXV) { sh.vx = sh.vx / sp * AST.MAXV; sh.vy = sh.vy / sp * AST.MAXV; }
      this.thrustSfx -= dt; if (this.thrustSfx <= 0) { this.thrustSfx = 0.1; this._sfx("thrust", 0.2); }
    }
    if (this.held.fire) { this.mouseFire -= dt; if (this.mouseFire <= 0) { this._fire(); this.mouseFire = 0.2; } }
    sh.x += sh.vx * dt; sh.y += sh.vy * dt; _wrap(sh); sh.vx *= AST.DRAG; sh.vy *= AST.DRAG; if (sh.invul > 0) sh.invul -= dt;
    for (const a of this.asteroids) { a.x += a.vx * dt; a.y += a.vy * dt; _wrap(a); }
    for (const u of this.ufos) {
      u.x += u.vx * dt; u.y += u.vy * dt;
      if (u.x < -50 || u.x > AST.REF_W + 50) u.dead = true;
      u.dirTimer -= dt; if (u.dirTimer <= 0) { u.dirTimer = _rnd(1, 4); u.vy = [-1, 0, 1][(Math.random() * 3) | 0] * 100; }
      u.fireTimer -= dt; if (u.fireTimer <= 0 && !u.dead) { u.fireTimer = _rnd(1.5, 2.5); this.bullets.push(this._mkBullet(u.x, u.y, this._ufoShotAngle(u), "ufo")); }
    }
    this.ufos = this.ufos.filter(u => !u.dead);
    this.ufoTimer -= dt;
    if (this.ufoTimer <= 0 && !this.ufos.length) { this.ufoTimer = 15 + _rnd(0, 10); this.ufos.push(this._mkUfo(this.score < 10000 ? 2 : [1, 2][(Math.random() * 2) | 0])); }

    const hit = (a, b) => Math.hypot(a.x - b.x, a.y - b.y) < a.r + b.r;
    for (const b of this.bullets) {
      for (const a of this.asteroids) { if (hit(b, a)) { b.dead = true; this._split(a, b.owner === "ship"); break; } }
      if (b.owner === "ufo" && sh && sh.invul <= 0 && hit(b, sh)) { b.dead = true; this._shipDeath(); }
      if (b.owner === "ship") for (const u of this.ufos) { if (hit(b, u)) { b.dead = true; this._ufoDeath(u); break; } }
    }
    this.bullets = this.bullets.filter(b => !b.dead);
    if (this.ship && this.ship.invul <= 0) {
      for (const a of this.asteroids) if (hit(this.ship, a)) { this._shipDeath(); break; }
      if (this.ship) for (const u of this.ufos) if (hit(this.ship, u)) { this._shipDeath(); this._ufoDeath(u); break; }
    }
    if (!this.asteroids.length) this._spawnLevel();
    const num = this.asteroids.length, delay = 0.2 + num * 0.05;
    this.beatTimer -= dt; if (this.beatTimer <= 0) { this.beatTimer = delay; this.beatState = 1 - this.beatState; this._sfx(this.beatState === 0 ? "beat1" : "beat2", 0.3); }
  }
  _ufoShotAngle(u) {
    if (u.size === 2 || !this.ship) return _rnd(0, 360);
    const ang = Math.atan2(this.ship.y - u.y, this.ship.x - u.x) * 180 / Math.PI;
    const err = Math.max(2, 40 - this.score / 1000);
    return ang + _rnd(-err, err);
  }
  _split(a, scored) {
    if (scored) this._addScore(a.points);
    for (let i = 0; i < 5; i++) this.particles.push({ x: a.x, y: a.y, vx: a.vx + _rnd(-50, 50), vy: a.vy + _rnd(-50, 50), r: 1, life: _rnd(0.3, 0.6), maxLife: 0.6 });
    if (a.size > 1) for (let i = 0; i < 2; i++) this.asteroids.push(this._mkAsteroid(a.x, a.y, a.size - 1));
    this.asteroids.splice(this.asteroids.indexOf(a), 1);
    this._sfx(a.size === 3 ? "bang_large" : a.size === 2 ? "bang_medium" : "bang_small");
  }
  _ufoDeath(u) { this._addScore(u.points); this.ufos.splice(this.ufos.indexOf(u), 1); this._sfx("bang_medium"); }
  _addScore(p) { this.score += p; if ((this.score / AST.EXTRA_LIFE | 0) > this.lastExtra) { this.lives++; this.lastExtra = this.score / AST.EXTRA_LIFE | 0; this._sfx("extra_ship"); } }
  _shipDeath() {
    if (!this.ship) return;
    for (let i = 0; i < 6; i++) this.fragments.push({ x: this.ship.x, y: this.ship.y, vx: this.ship.vx + _rnd(-150, 150), vy: this.ship.vy + _rnd(-150, 150), angle: _rnd(0, 360), rot: _rnd(-200, 200), life: 1, poly: [[-5, 0], [5, 0]] });
    for (let i = 0; i < 12; i++) this.particles.push({ x: this.ship.x, y: this.ship.y, vx: this.ship.vx + _rnd(-200, 200), vy: this.ship.vy + _rnd(-200, 200), r: 1, life: _rnd(0.3, 0.6), maxLife: 0.6 });
    this.lives--; this.ship = null; this.phase = "DYING"; this.stateTimer = 2.0; this._sfx("bang_large");
  }

  // ── Rendering vettoriale ─────────────────────────────────────────────────
  draw(ctx, W, H) {
    const scale = Math.min(W / AST.REF_W, H / AST.REF_H);
    const offX = (W - AST.REF_W * scale) / 2, offY = (H - AST.REF_H * scale) / 2;
    this._sc = scale; this._ox = offX; this._oy = offY;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
    const r2s = (x, y) => [x * scale + offX, y * scale + offY];

    ctx.fillStyle = "#fff";
    for (const b of this.bullets) { const [x, y] = r2s(b.x, b.y); ctx.beginPath(); ctx.arc(x, y, Math.max(1, 2 * scale), 0, Math.PI * 2); ctx.fill(); }
    for (const a of this.asteroids) this._poly(ctx, a.x, a.y, a.poly, 0, "255,255,255");
    for (const u of this.ufos) this._poly(ctx, u.x, u.y, this._ufoPoly(u), 0, "255,255,255");
    for (const f of this.fragments) { const al = Math.max(0, f.life); this._poly(ctx, f.x, f.y, f.poly, f.angle, `255,255,255`, al); }
    for (const p of this.particles) { const al = Math.max(0, p.life / p.maxLife); const [x, y] = r2s(p.x, p.y); ctx.fillStyle = `rgba(255,255,255,${al})`; ctx.fillRect(x - scale / 2, y - scale / 2, Math.max(1, scale), Math.max(1, scale)); }
    if (this.ship) {
      let dim = this.ship.invul > 0 && ((this.ship.invul * 10) | 0) % 2 === 0;
      this._poly(ctx, this.ship.x, this.ship.y, [[20, 0], [-15, 12], [-10, 0], [-15, -12]], this.ship.angle, dim ? "100,100,100" : "255,255,255");
      if (this.ship.thrusting) this._poly(ctx, this.ship.x, this.ship.y, [[-10, 0], [-18, 5], [-25, 0], [-18, -5]], this.ship.angle, "200,200,255");
    }
    this._ui(ctx, W, H, r2s);
    if (this.phase === "PLAY") this._controls(ctx, W, H);
    // scanline CRT
    ctx.fillStyle = "rgba(0,0,0,0.16)"; for (let y = 0; y < H; y += 3) ctx.fillRect(0, y, W, 1);
  }
  _ufoPoly(u) {
    const k = u.size === 2 ? 1 : 0.55;
    return [[-15, 0], [-5, -5], [5, -5], [15, 0], [5, 5], [-5, 5], [-15, 0], [-5, 10], [5, 10], [15, 0]].map(([x, y]) => [x * k, y * k]);
  }
  _poly(ctx, px, py, poly, angleDeg, rgb, alpha) {
    const ar = angleDeg * Math.PI / 180, c = Math.cos(ar), s = Math.sin(ar);
    const pts = poly.map(([x, y]) => { const rx = x * c - y * s, ry = x * s + y * c; return [(px + rx) * this._sc + this._ox, (py + ry) * this._sc + this._oy]; });
    if (pts.length < 2) return;
    const a = alpha != null ? alpha : 1;
    const closed = pts.length > 2;
    // glow
    ctx.strokeStyle = `rgba(${rgb},${a * 0.28})`; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]); if (closed) ctx.closePath(); ctx.stroke();
    ctx.strokeStyle = `rgba(${rgb},${a})`; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]); if (closed) ctx.closePath(); ctx.stroke();
  }
  _ui(ctx, W, H, r2s) {
    ctx.fillStyle = "#fff"; ctx.font = `${Math.round(25 * this._sc)}px "Courier New", monospace`; ctx.textAlign = "right"; ctx.textBaseline = "top";
    const [sx, sy] = r2s(AST.REF_W - 20, 20);
    ctx.fillText((this.t("asteroids_score", "SCORE: {score}")).replace("{score}", this.score), sx, sy);
    for (let i = 0; i < this.lives; i++) this._poly(ctx, AST.REF_W - 30 - i * 30, 60, [[10, 0], [-7, 6], [-7, -6]], -90, "255,255,255");
    ctx.textAlign = "center";
    if (this.phase === "START") {
      ctx.fillStyle = "#fff"; ctx.font = `bold ${Math.round(40 * this._sc)}px "Courier New", monospace`;
      ctx.fillText(this.t("asteroids_title", "ASTEROIDS"), W / 2, H / 2 - 50);
      ctx.font = `${Math.round(22 * this._sc)}px "Courier New", monospace`;
      ctx.fillText(this.t("asteroids_start", "TAP / PREMI UN TASTO"), W / 2, H / 2 + 10);
      ctx.fillText(this.t("asteroids_instructions", "Frecce: ruota/spingi · Spazio: spara"), W / 2, H / 2 + 50);
    } else if (this.phase === "GAMEOVER") {
      ctx.fillStyle = "#fff"; ctx.font = `bold ${Math.round(44 * this._sc)}px "Courier New", monospace`;
      ctx.fillText(this.t("asteroids_gameover", "GAME OVER"), W / 2, H / 2 - 30);
      ctx.font = `${Math.round(22 * this._sc)}px "Courier New", monospace`;
      ctx.fillText(this.t("asteroids_exit", "TAP PER USCIRE"), W / 2, H / 2 + 30);
    }
    ctx.textBaseline = "alphabetic";
  }
  _controls(ctx, W, H) {
    const labels = [["left", "◀"], ["right", "▶"], ["up", "▲"], ["fire", "●"]];
    const n = labels.length, gap = 10, bw = Math.min(90, (W - 24 - gap * (n - 1)) / n), h = 64, y = H - h - 12;
    const x0 = (W - (n * bw + (n - 1) * gap)) / 2;
    this._btns = []; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    labels.forEach(([a, lbl], i) => {
      const x = x0 + i * (bw + gap);
      ctx.fillStyle = this.held[a] ? "rgba(120,200,255,0.5)" : "rgba(40,50,80,0.5)";
      this.host._roundRect(ctx, x, y, bw, h, 10); ctx.fill();
      ctx.strokeStyle = "rgba(160,180,255,0.5)"; ctx.lineWidth = 1.5; this.host._roundRect(ctx, x, y, bw, h, 10); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.font = "bold 24px system-ui, sans-serif"; ctx.fillText(lbl, x + bw / 2, y + h / 2 + 1);
      this._btns.push({ a, x, y, w: bw, h });
    });
    ctx.textBaseline = "alphabetic";
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["asteroids"] = AsteroidsGame;
