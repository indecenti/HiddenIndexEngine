// ──────────────────────────────────────────────────────────────────────────
// CentipedeGame — port JS 1:1 di engine/minigames/centipede/centipede_game.py.
// ──────────────────────────────────────────────────────────────────────────
class CentiMushroom {
  constructor(gx, gy) {
    this.gx = gx;
    this.gy = gy;
    this.health = 4;
    this.poisoned = false;
  }
  draw(ctx, sm, ox, oy) {
    const color = this.poisoned ? [50, 200, 50] : [200, 50, 200];
    const fact = 0.4 + (this.health / 4.0) * 0.6;
    const r = Math.round(color[0] * fact);
    const g = Math.round(color[1] * fact);
    const b = Math.round(color[2] * fact);
    const c = `rgb(${r},${g},${b})`;
    
    const rx = ox + this.gx * 20;
    const ry = oy + this.gy * 20;
    
    // Glow sotto
    ctx.fillStyle = `rgb(${Math.round(r / 3)},${Math.round(g / 3)},${Math.round(b / 3)})`;
    ctx.beginPath();
    ctx.roundRect(rx + 1, ry + 1, 18, 18, 6);
    ctx.fill();
    
    // Cappello
    ctx.fillStyle = c;
    ctx.beginPath();
    ctx.roundRect(rx + 2, ry + 2, 16, 12, 8);
    ctx.fill();
    
    // Gambo
    ctx.fillRect(rx + 8, ry + 10, 4, 10);
  }
}

class CentipedeSegment {
  constructor(x, y, isHead = false) {
    this.x = x;
    this.y = y;
    this.isHead = isHead;
    this.dirX = 1;
    this.dirY = 1;
    this.movingDown = false;
    this.targetY = y;
    this.speed = 180.0;
    this.poisoned = false;
  }
  update(dt, mushrooms, playerZoneTop) {
    if (this.movingDown) {
      this.y += this.speed * dt;
      if (this.dirY > 0) {
        if (this.y >= this.targetY) {
          this.y = this.targetY;
          this.movingDown = false;
        }
      } else {
        if (this.y <= this.targetY) {
          this.y = this.targetY;
          this.movingDown = false;
        }
      }
      return;
    }

    const prevGx = Math.floor(this.x / 20);
    this.x += this.dirX * this.speed * dt;
    const currGx = Math.floor(this.x / 20);
    const gy = Math.floor(this.y / 20);

    let hit = false;
    if (this.dirX > 0 && this.x + 20 > 600) {
      hit = true;
      this.x = 600 - 20;
    } else if (this.dirX < 0 && this.x < 0) {
      hit = true;
      this.x = 0;
    }

    if (!hit && currGx !== prevGx) {
      const key = `${currGx},${gy}`;
      if (mushrooms[key]) {
        hit = true;
        const m = mushrooms[key];
        if (m.poisoned) this.poisoned = true;
        this.x = prevGx * 20;
      }
    }

    if (hit) {
      this.dirX *= -1;
      this.movingDown = true;
      if (this.poisoned && gy < 35) {
        this.targetY = this.y + 20;
        this.dirY = 1;
      } else {
        if (this.dirY > 0) {
          if (gy >= 35) {
            this.dirY = -1;
            this.targetY = this.y - 20;
          } else {
            this.targetY = this.y + 20;
          }
        } else {
          if (gy <= playerZoneTop) {
            this.dirY = 1;
            this.targetY = this.y + 20;
          } else {
            this.targetY = this.y - 20;
          }
        }
      }
    }
  }
  draw(ctx, sm, ox, oy) {
    let color = this.isHead ? [255, 255, 255] : [255, 0, 255];
    if (this.poisoned) color = [50, 200, 50];
    const rx = ox + this.x;
    const ry = oy + this.y;

    // Glow
    ctx.fillStyle = `rgb(${Math.round(color[0] / 4)},${Math.round(color[1] / 4)},${Math.round(color[2] / 4)})`;
    ctx.beginPath();
    ctx.roundRect(rx - 1, ry - 1, 22, 22, 10);
    ctx.fill();

    // Segmento principale
    ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
    ctx.beginPath();
    ctx.roundRect(rx + 1, ry + 1, 18, 18, this.isHead ? 8 : 10);
    ctx.fill();

    if (this.isHead) {
      const ex = rx + (this.dirX > 0 ? 12 : 4);
      ctx.fillStyle = "#000";
      ctx.fillRect(ex, ry + 4, 4, 4);
      ctx.fillStyle = "#fff";
      ctx.fillRect(ex + 1, ry + 5, 2, 2);
    }
  }
}

class CentiSpider {
  constructor(side) {
    this.x = side === 1 ? -40 : 620;
    this.y = (26 + Math.floor(Math.random() * 8)) * 20; // tra ROWS-10 e ROWS-2
    this.vx = side * 150.0;
    this.vy = 150.0;
    this.isDead = false;
    this.moveTimer = 0.0;
  }
  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.moveTimer += dt;
    if (this.moveTimer > 0.2 + Math.random() * 0.2) {
      this.moveTimer = 0;
      this.vy *= Math.random() > 0.1 ? -1 : 1;
      if (Math.random() > 0.95) this.vx *= -1;
    }

    // Rimbalzo Orizzontale
    if (this.x < 0) {
      this.x = 0;
      this.vx = Math.abs(this.vx);
    } else if (this.x > 580) {
      this.x = 580;
      this.vx = -Math.abs(this.vx);
    }

    // Rimbalzo Verticale (Area Player)
    if (this.y < 26 * 20) {
      this.y = 26 * 20;
      this.vy = Math.abs(this.vy);
    } else if (this.y > 700) {
      this.y = 700;
      this.vy = -Math.abs(this.vy);
    }
  }
  draw(ctx, sm, ox, oy) {
    const rx = ox + this.x;
    const ry = oy + this.y;
    const color = [255, 128, 0];

    // Glow
    ctx.fillStyle = `rgb(${Math.round(color[0] / 5)},${Math.round(color[1] / 5)},${Math.round(color[2] / 5)})`;
    ctx.beginPath();
    ctx.arc(rx + 10, ry + 10, 15, 0, Math.PI * 2);
    ctx.fill();

    // Corpo
    ctx.fillStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
    ctx.beginPath();
    ctx.roundRect(rx, ry, 20, 20, 4);
    ctx.fill();

    // Zampe animate
    const t = performance.now() * 0.02;
    ctx.strokeStyle = `rgb(${color[0]},${color[1]},${color[2]})`;
    ctx.lineWidth = 2;
    for (let i = 0; i < 4; i++) {
      const offset = Math.sin(t + i) * 8;
      ctx.beginPath();
      ctx.moveTo(rx + 2 + i * 5, ry + 10);
      ctx.lineTo(rx + 2 + i * 5, ry + 10 + offset);
      ctx.stroke();
    }
  }
}

class CentiParticle {
  constructor(x, y, color) {
    this.x = x;
    this.y = y;
    const angle = Math.random() * Math.PI * 2;
    const speed = 50 + Math.random() * 100;
    this.vx = Math.cos(angle) * speed;
    this.vy = Math.sin(angle) * speed;
    this.color = color;
    this.life = 1.0;
    this.size = 2 + Math.floor(Math.random() * 4);
  }
  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.life -= dt * 1.5;
  }
  draw(ctx, ox, oy) {
    if (this.life > 0) {
      const rx = ox + this.x;
      const ry = oy + this.y;
      ctx.fillStyle = `rgba(${this.color[0]},${this.color[1]},${this.color[2]},${this.life})`;
      ctx.fillRect(rx, ry, this.size, this.size);
    }
  }
}

class CentipedeGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    this.mushrooms = {};
    this.segments = [];
    this.spiders = [];
    this.particles = [];
    this.bullets = [];
    this.playerX = 300;
    this.playerY = 680;
    
    this.score = 0;
    this.lives = 3;
    this.level = 0;
    this.phase = "START";
    this.deathTimer = 0.0;
    this.invulTimer = 0.0;
    
    this.playerZoneTop = 26; // 36 - 10
    this.offsetX = (1280 - 600) / 2;
    this.offsetY = 0;
    this.spiderTimer = 2.0;
    this.usingMouse = false;
    this.mouseTargetX = 300;
    this.mouseTargetY = 680;
    
    this.held = { left: false, right: false, up: false, down: false };
    this._btns = [];
    this.sounds = {};
  }
  t(k, fb) { return this.strings[k] || fb || k; }
  
  load() {
    const loads = [];
    loads.push(loadImage(this.base + "marquee_centipede.png").then(im => this.marquee = im));
    const snd = {
      fire: "centi_fire.wav",
      kill_centi: "centi_kill.wav",
      kill_spider: "spider_kill.wav",
      death: "death.wav",
      beat: "beat.wav",
      mush_hit: "mush_hit.wav"
    };
    for (const [k, f] of Object.entries(snd)) {
      this.sounds[k] = new Audio(this.base + "assets/sounds/" + f);
      this.sounds[k].preload = "auto";
    }
    return Promise.all(loads);
  }
  _sfx(k, vol = 0.4) {
    const a = this.sounds[k];
    if (!a) return;
    const n = a.cloneNode();
    n.volume = (this.host.audio.muted ? 0 : this.host.audio.sfxVol) * vol;
    n.play().catch(() => {});
  }
  
  start() {
    this.score = 0;
    this.lives = 3;
    this.level = 0;
    this.phase = "START";
    this._resetLevel();
  }
  _resetLevel() {
    this.mushrooms = {};
    this.spiders = [];
    this.bullets = [];
    for (let i = 0; i < 45; i++) {
      const gx = Math.floor(Math.random() * 30);
      const gy = 2 + Math.floor(Math.random() * 24); // tra 2 e ROWS-10
      this.mushrooms[`${gx},${gy}`] = new CentiMushroom(gx, gy);
    }
    this._spawnCentipede(12 + this.level);
  }
  _spawnCentipede(length) {
    this.segments = [];
    for (let i = 0; i < length; i++) {
      this.segments.push(new CentipedeSegment((15 - i) * 20, 0, i === 0));
    }
  }
  
  pointer(sx, sy, type) {
    if (type === "up") {
      this.held.left = this.held.right = this.held.up = this.held.down = false;
      return;
    }
    if (this.phase === "START") {
      this.phase = "PLAY";
      return;
    }
    if (this.phase === "GAMEOVER") {
      this.host._minigameDone({ success: this.score > 0, score: this.score });
      return;
    }
    if (this.phase !== "PLAY") return;

    for (const b of this._btns) {
      if (sx >= b.x && sx <= b.x + b.w && sy >= b.y && sy <= b.y + b.h) {
        if (b.a === "fire") this._fire();
        else this.held[b.a] = true;
        this.usingMouse = false;
        return;
      }
    }

    this.usingMouse = true;
    this.mouseTargetX = sx - this.offsetX - 10;
    this.mouseTargetY = sy - this.offsetY - 10;
    this._fire(); // sparo al tocco
  }
  
  key(e, down) {
    if (down && (this.phase === "START")) {
      this.phase = "PLAY";
      return;
    }
    if (down && this.phase === "GAMEOVER") {
      this.host._minigameDone({ success: this.score > 0, score: this.score });
      return;
    }
    if (this.phase !== "PLAY") return;

    this.usingMouse = false;
    if (e.key === "ArrowLeft") this.held.left = down;
    else if (e.key === "ArrowRight") this.held.right = down;
    else if (e.key === "ArrowUp") this.held.up = down;
    else if (e.key === "ArrowDown") this.held.down = down;
    else if (e.key === " " && down) this._fire();
  }
  
  _fire() {
    if (this.bullets.length < 1) {
      this.bullets.push({ x: this.playerX + 8, y: this.playerY });
      this._sfx("fire");
    }
  }
  
  update(dt) {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      this.particles[i].update(dt);
      if (this.particles[i].life <= 0) this.particles.splice(i, 1);
    }
    
    if (this.phase === "PLAY") {
      if (this.invulTimer > 0) this.invulTimer -= dt;
      this._updatePlay(dt);
    } else if (this.phase === "DYING") {
      this.deathTimer -= dt;
      if (this.deathTimer <= 0) {
        if (this.lives <= 0) this.phase = "GAMEOVER";
        else {
          this.phase = "PLAY";
          this.invulTimer = 2.5;
          this.playerX = 300;
          this.playerY = 680;
          this.bullets = [];
          this.spiders = [];
          this._spawnCentipede(12 + this.level);
        }
      }
    }
  }
  
  _updatePlay(dt) {
    let newX = this.playerX;
    let newY = this.playerY;
    if (this.usingMouse) {
      newX = this.mouseTargetX;
      newY = this.mouseTargetY;
    } else {
      newX += ((this.held.right ? 1 : 0) - (this.held.left ? 1 : 0)) * 300.0 * dt;
      newY += ((this.held.down ? 1 : 0) - (this.held.up ? 1 : 0)) * 300.0 * dt;
    }

    newX = Math.max(0, Math.min(newX, 600 - 20));
    newY = Math.max(this.playerZoneTop * 20, Math.min(newY, 720 - 20));

    // Collisione con i Funghi (Blocco movimento)
    let collision = false;
    const playerRect = { x: newX + 2, y: newY + 2, w: 16, h: 16 };
    const pgx = Math.floor((newX + 10) / 20);
    const pgy = Math.floor((newY + 10) / 20);

    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const key = `${pgx + dx},${pgy + dy}`;
        if (this.mushrooms[key]) {
          const mr = { x: (pgx + dx) * 20, y: (pgy + dy) * 20, w: 20, h: 20 };
          if (playerRect.x < mr.x + mr.w && playerRect.x + playerRect.w > mr.x &&
              playerRect.y < mr.y + mr.h && playerRect.y + playerRect.h > mr.y) {
            collision = true;
            break;
          }
        }
      }
      if (collision) break;
    }

    if (!collision) {
      this.playerX = newX;
      this.playerY = newY;
    }

    this.spiderTimer -= dt;
    if (this.spiderTimer <= 0) {
      this.spiders.push(new CentiSpider(Math.random() < 0.5 ? 1 : -1));
      this.spiderTimer = 5.0 + Math.random() * 5.0; // SPIDER_SPAWN_TIME (5.0, 10.0)
    }

    if (this.invulTimer <= 0) {
      const pr = { x: this.playerX, y: this.playerY, w: 16, h: 16 };
      for (const s of this.segments) {
        s.update(dt, this.mushrooms, this.playerZoneTop);
        const sr = { x: s.x + 2, y: s.y + 2, w: 16, h: 16 };
        if (pr.x < sr.x + sr.w && pr.x + pr.w > sr.x &&
            pr.y < sr.y + sr.h && pr.y + pr.h > sr.y) {
          this._handleDeath();
          return;
        }
      }
      for (let i = this.spiders.length - 1; i >= 0; i--) {
        const sp = this.spiders[i];
        sp.update(dt);
        const spr = { x: sp.x + 2, y: sp.y + 2, w: 16, h: 16 };
        if (pr.x < spr.x + spr.w && pr.x + pr.w > spr.x &&
            pr.y < spr.y + spr.h && pr.y + pr.h > spr.y) {
          this._handleDeath();
          return;
        }
      }
    } else {
      for (const s of this.segments) s.update(dt, this.mushrooms, this.playerZoneTop);
      for (const sp of this.spiders) sp.update(dt);
    }

    // Bullets
    for (let i = this.bullets.length - 1; i >= 0; i--) {
      const b = this.bullets[i];
      b.y -= 800.0 * dt; // BULLET_SPEED
      if (b.y < 0) {
        this.bullets.splice(i, 1);
        continue;
      }

      const br = { x: b.x, y: b.y, w: 4, h: 12 };
      const bgx = Math.floor((b.x + 2) / 20);
      const bgy = Math.floor((b.y + 6) / 20);

      const mKey = `${bgx},${bgy}`;
      if (this.mushrooms[mKey]) {
        const m = this.mushrooms[mKey];
        m.health -= 1;
        if (m.health <= 0) {
          delete this.mushrooms[mKey];
          this.score += 1; // PT_MUSHROOM
        }
        this.bullets.splice(i, 1);
        this._sfx("mush_hit", 0.2);
        continue;
      }

      // Hit Spider
      let hitSpider = null;
      for (const sp of this.spiders) {
        const spr = { x: sp.x, y: sp.y, w: 20, h: 20 };
        if (br.x < spr.x + spr.w && br.x + br.w > spr.x &&
            br.y < spr.y + spr.h && br.y + br.h > spr.y) {
          hitSpider = sp;
          break;
        }
      }
      if (hitSpider) {
        this.spiders.splice(this.spiders.indexOf(hitSpider), 1);
        this.bullets.splice(i, 1);
        this.score += 600; // PT_SPIDER_MID
        this._sfx("kill_spider");
        continue;
      }

      // Hit Centipede
      let hitSeg = null;
      for (const s of this.segments) {
        const sr = { x: s.x, y: s.y, w: 20, h: 20 };
        if (br.x < sr.x + sr.w && br.x + br.w > sr.x &&
            br.y < sr.y + sr.h && br.y + br.h > sr.y) {
          hitSeg = s;
          break;
        }
      }
      if (hitSeg) {
        this.bullets.splice(i, 1);
        this.score += hitSeg.isHead ? 100 : 10; // PT_CENTI_HEAD : PT_CENTI_BODY
        const mx = Math.floor((hitSeg.x + 10) / 20);
        const my = Math.floor((hitSeg.y + 10) / 20);
        this.mushrooms[`${mx},${my}`] = new CentiMushroom(mx, my);
        
        const idx = this.segments.indexOf(hitSeg);
        this.segments.splice(idx, 1);
        if (idx < this.segments.length) {
          this.segments[idx].isHead = true;
        }
        this._sfx("kill_centi");
        continue;
      }
    }

    if (this.segments.length === 0) {
      this.level += 1;
      this._spawnCentipede(12);
    }
  }
  
  _handleDeath() {
    this.lives -= 1;
    this._sfx("death");
    this.phase = "DYING";
    this.deathTimer = 1.5;
    for (let i = 0; i < 30; i++) {
      this.particles.push(new CentiParticle(this.playerX + 10, this.playerY + 10, [0, 255, 255]));
      this.particles.push(new CentiParticle(this.playerX + 10, this.playerY + 10, [255, 255, 255]));
    }
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

    const sm = this.host.scaling;
    
    // Area di gioco centrata
    ctx.fillStyle = "rgb(10, 5, 20)"; // COLOR_BG
    ctx.fillRect(this.offsetX, this.offsetY, 600, 720);
    
    // Disegna Funghi
    for (const m of Object.values(this.mushrooms)) {
      m.draw(ctx, sm, this.offsetX, this.offsetY);
    }
    
    // Disegna Segmenti Centopiedi
    for (const s of this.segments) {
      s.draw(ctx, sm, this.offsetX, this.offsetY);
    }
    
    // Disegna Ragni
    for (const sp of this.spiders) {
      sp.draw(ctx, sm, this.offsetX, this.offsetY);
    }
    
    // Disegna Proiettili
    ctx.fillStyle = "rgb(255, 255, 100)"; // COLOR_BULLET
    for (const b of this.bullets) {
      ctx.fillRect(this.offsetX + b.x, this.offsetY + b.y, 4, 12);
    }
    
    // Disegna Particelle
    for (const p of this.particles) {
      p.draw(ctx, this.offsetX, this.offsetY);
    }
    
    // Disegna Giocatore
    if (this.phase === "PLAY") {
      const isInvulBlink = this.invulTimer > 0 && Math.floor(this.invulTimer * 10) % 2 === 0;
      if (!isInvulBlink) {
        const px = this.offsetX + this.playerX;
        const py = this.offsetY + this.playerY;
        
        // Player Glow
        ctx.fillStyle = "rgb(0, 80, 80)";
        ctx.beginPath();
        ctx.arc(px + 10, py + 10, 15, 0, Math.PI * 2);
        ctx.fill();
        
        // Player Body
        ctx.fillStyle = "rgb(0, 255, 255)"; // COLOR_PLAYER
        ctx.beginPath();
        ctx.roundRect(px, py, 20, 20, 4);
        ctx.fill();
        // Player turret
        ctx.fillRect(px + 8, py - 5, 4, 5);
      }
    }
    
    this._drawUI(ctx, 1280, 720);
    this._drawScanlines(ctx, 1280, 720);
    ctx.restore();
  }
  
  _drawUI(ctx, W, H) {
    ctx.font = "bold 26px Courier New, monospace";
    ctx.fillStyle = "#fff";
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    
    // Score
    const scoreStr = (this.t("centipede_score", "SCORE: {score}")).replace("{score}", this.score);
    ctx.fillText(scoreStr, 1260, 10);
    
    // Lives
    ctx.fillStyle = "rgb(0, 255, 255)";
    for (let i = 0; i < this.lives; i++) {
      const lx = 1260 - 15 - i * 30;
      ctx.fillRect(lx, 50, 15, 15);
    }
    
    if (this.phase === "START" || this.phase === "GAMEOVER") {
      this._drawOverlayPanel(ctx, W, H);
    }
  }
  
  _drawOverlayPanel(ctx, W, H) {
    const pw = 580, ph = 240;
    const px = (W - pw) / 2;
    const py = (H - ph) / 2;
    
    ctx.save();
    // Glass Panel
    ctx.fillStyle = "rgba(10, 10, 25, 0.9)";
    ctx.beginPath();
    ctx.roundRect(px, py, pw, ph, 15);
    ctx.fill();
    ctx.strokeStyle = "rgba(0, 255, 255, 0.47)";
    ctx.lineWidth = 3;
    ctx.stroke();
    
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    
    if (this.phase === "START") {
      ctx.font = "bold 28px Courier New, monospace";
      ctx.fillStyle = "rgb(0, 255, 255)";
      ctx.fillText(this.t("centipede_title", "CENTIPEDE"), px + pw / 2, py + 40);
      
      ctx.font = "18px Courier New, monospace";
      ctx.fillStyle = "#c8c8c8";
      ctx.fillText(this.t("centipede_instructions", "Frecce: muovi · Spazio: spara"), px + pw / 2, py + 100);
      
      ctx.font = "bold 28px Courier New, monospace";
      ctx.fillStyle = "#fff";
      ctx.fillText(this.t("centipede_start", "TAP / PREMI UN TASTO"), px + pw / 2, py + 160);
    } else if (this.phase === "GAMEOVER") {
      ctx.font = "bold 28px Courier New, monospace";
      ctx.fillStyle = "rgb(255, 50, 50)";
      ctx.fillText(this.t("centipede_gameover", "GAME OVER"), px + pw / 2, py + 60);
      
      ctx.font = "20px Courier New, monospace";
      ctx.fillStyle = "#fff";
      ctx.fillText(this.t("centipede_exit", "TAP PER USCIRE"), px + pw / 2, py + 130);
    }
    ctx.restore();
  }
  
  _drawScanlines(ctx, W, H) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
    for (let y = 0; y < H; y += 3) {
      ctx.fillRect(0, y, W, 1);
    }
  }
}

(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["centipede"] = CentipedeGame;
