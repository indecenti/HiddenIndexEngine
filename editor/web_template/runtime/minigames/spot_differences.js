// ──────────────────────────────────────────────────────────────────────────
// SpotDifferencesGame — port JS 1:1 di engine/minigames/spot_differences/spot_differences_game.py.
// ──────────────────────────────────────────────────────────────────────────
class SpotDifferencesGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    
    this.currentScore = 0;
    this.totalScore = 0;
    this.level = 1;
    this.maxLevels = 5;
    this.wonAll = false;
    this.gameOver = false;
    
    // Difficoltà e parametri
    this.numTotalObjects = 50;
    this.numDifferences = 6;
    this.timeLeft = 120;
    this.timeLimit = 120;
    
    // Feedback ed estetica
    this.wrongClickTimer = 0.0;
    this.wrongClickPos = { x: 0, y: 0 };
    this.pulseTimer = 0.0;
    this.particles = [];
    this.screenShake = 0.0;
    this.victoryTimer = 0.0;
    
    this.combo = 0;
    this.comboTimer = 0.0;
    this.lastHitMsg = "";
    this.lastHitTimer = 0.0;
    this.wrongClicks = 0;
    
    this.panelWidth = 640;
    this.panelHeight = 600;
    this.objectBaseSize = 42;
    
    this.stylePools = { cartoon: [], real: [], "line art": [] };
    this.chosenStyle = "cartoon";
    this.deckSmall = [];
    this.deckOther = [];
    this.loadedImages = {};
    
    this.objectsToDraw = [];
    this.differencesIndices = [];
    this.foundIndices = {};
    
    this.lastTickTime = 0.0;
    
    // Temi estetici Vegas/Casino
    this.themes = [
      {
        name: "Vegas Gold",
        bg: "#0f051e",
        panelBg: "#2d0f4b",
        hudBg: "#ffd700"
      },
      {
        name: "Feltro Verde",
        bg: "#05190a",
        panelBg: "#0f4119",
        hudBg: "#daa520"
      },
      {
        name: "Neon Slot",
        bg: "#0a0a0f",
        panelBg: "#141428",
        hudBg: "#00fa9a"
      }
    ];
    this.uiTheme = this.themes[Math.floor(Math.random() * this.themes.length)];
  }
  
  t(k, fb) { return this.strings[k] || fb || k; }
  
  load() {
    const jsonPath = this.base + "objects.json";
    return fetch(jsonPath)
      .then(r => r.json())
      .then(data => {
        const rawObjects = data.objects || [];
        this.stylePools = { cartoon: [], real: [], "line art": [] };
        
        for (const obj of rawObjects) {
          const style = obj.style || "cartoon";
          this.stylePools[style] = this.stylePools[style] || [];
          this.stylePools[style].push(obj);
        }
        
        // Seleziona stile coerente
        const validStyles = Object.keys(this.stylePools).filter(s => this.stylePools[s].length >= 25);
        this.chosenStyle = validStyles.length > 0 ? validStyles[Math.floor(Math.random() * validStyles.length)] : "cartoon";
        
        const pool = this.stylePools[this.chosenStyle] || [];
        const loads = [];
        this.loadedImages = {};
        
        for (const item of pool) {
          loads.push(loadImage(this.host.manifest._base + item.icon).then(img => {
            if (img) {
              this.loadedImages[item.id] = img;
            }
          }));
        }
        return Promise.all(loads);
      });
  }
  
  _sfx(soundId) {
    const mapping = {
      hit: "found",
      error: "miss",
      win: "complete",
      level: "levelup",
      tick: "click"
    };
    const mapped = mapping[soundId];
    if (mapped) this.host.audio.sfx(mapped);
  }
  
  _shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
  }
  
  start() {
    this.currentScore = 0;
    this.totalScore = 0;
    this.level = 1;
    this.maxLevels = 5;
    this.wonAll = false;
    this.gameOver = false;
    this.panelWidth = 640;
    this.panelHeight = 600;
    this.deckSmall = [];
    this.deckOther = [];
    this._setupLevel();
  }
  
  _setupLevel() {
    this.objectsToDraw = [];
    this.differencesIndices = [];
    this.foundIndices = {};
    this.gameOver = false;
    this.wrongClickTimer = 0.0;
    this.particles = [];
    this.victoryTimer = 0.0;
    this.screenShake = 0.0;
    this.wrongClicks = 0;
    this.combo = 0;
    this.comboTimer = 0.0;
    
    const levelScale = (this.level - 1) / Math.max(1, this.maxLevels - 1);
    this.numTotalObjects = 63 + Math.floor(85 * levelScale);
    this.numDifferences = 6 + Math.floor(9 * levelScale);
    this.timeLeft = Math.max(30, this.timeLimit * (1.0 - levelScale * 0.45));
    
    const pool = this.stylePools[this.chosenStyle] || [];
    if (pool.length === 0) {
      this.finishGame();
      return;
    }
    
    if (this.deckSmall.length === 0 || this.deckOther.length === 0) {
      const allSmall = pool.filter(o => o.tags.includes("piccolo"));
      const allOther = pool.filter(o => !allSmall.includes(o));
      
      this.deckSmall = allSmall.length < 20 ? pool.slice() : allSmall.slice();
      this.deckOther = allOther.length < 20 ? pool.slice() : allOther.slice();
      
      this._shuffle(this.deckSmall);
      this._shuffle(this.deckOther);
    }
    
    const numSmallTarget = Math.min(this.deckSmall.length, this.numDifferences * 4 + 15);
    const numOthersTarget = Math.min(this.deckOther.length, this.numTotalObjects);
    
    const selectedAssets = [];
    for (let i = 0; i < numSmallTarget; i++) {
      if (this.deckSmall.length === 0) break;
      selectedAssets.push(this.deckSmall.pop());
    }
    for (let i = 0; i < numOthersTarget; i++) {
      if (this.deckOther.length === 0) break;
      selectedAssets.push(this.deckOther.pop());
    }
    
    while (selectedAssets.length < this.numTotalObjects + 10) {
      selectedAssets.push(pool[Math.floor(Math.random() * pool.length)]);
    }
    
    this._shuffle(selectedAssets);
    
    const placedRects = [];
    const baseSize = this.objectBaseSize;
    
    const quadrants = [
      { x1: 15, y1: 15, x2: this.panelWidth / 2, y2: this.panelHeight / 2 },
      { x1: this.panelWidth / 2, y1: 15, x2: this.panelWidth - 15, y2: this.panelHeight / 2 },
      { x1: 15, y1: this.panelHeight / 2, x2: this.panelWidth / 2, y2: this.panelHeight - 25 },
      { x1: this.panelWidth / 2, y1: this.panelHeight / 2, x2: this.panelWidth - 15, y2: this.panelHeight - 25 }
    ];
    let quadIdx = 0;
    
    for (const passNum of [1, 2]) {
      for (let i = selectedAssets.length - 1; i >= 0; i--) {
        if (this.objectsToDraw.length >= this.numTotalObjects) break;
        
        const asset = selectedAssets[i];
        const isSmall = asset.tags.includes("piccolo");
        
        if (passNum === 1 && isSmall) continue;
        if (passNum === 2 && !isSmall) continue;
        
        const img = this.loadedImages[asset.id];
        if (!img) {
          selectedAssets.splice(i, 1);
          continue;
        }
        
        const origW = img.width || 65;
        const origH = img.height || 65;
        
        let tagMult = 1.0;
        if (asset.tags.includes("grande")) tagMult *= 1.15;
        if (asset.tags.includes("piccolo")) tagMult *= (0.45 + Math.random() * 0.35);
        if (asset.tags.includes("lungo") || asset.tags.includes("largo")) tagMult *= 0.90;
        
        const sizeMult = (passNum === 1 ? (0.9 + Math.random() * 0.3) : (0.7 + Math.random() * 0.4)) * tagMult;
        const scaleFactor = (baseSize / Math.max(origW, origH)) * sizeMult;
        
        let newW = Math.round(origW * scaleFactor);
        let newH = Math.round(origH * scaleFactor);
        
        newW = Math.max(20, Math.min(Math.round(this.panelWidth * 0.70), newW));
        newH = Math.max(20, Math.min(Math.round(this.panelHeight * 0.70), newH));
        
        let foundPos = false;
        const attempts = 200;
        
        for (let attempt = 0; attempt < attempts; attempt++) {
          const q = quadrants[quadIdx % 4];
          let rx, ry;
          if (attempt < 100) {
            rx = Math.floor(q.x1 + Math.random() * (q.x2 - newW - q.x1));
            ry = Math.floor(q.y1 + Math.random() * (q.y2 - newH - q.y1));
          } else {
            rx = Math.floor(15 + Math.random() * (this.panelWidth - newW - 30));
            ry = Math.floor(15 + Math.random() * (this.panelHeight - newH - 40));
          }
          
          const newRect = { x: rx, y: ry, w: newW, h: newH, cx: rx + newW / 2, cy: ry + newH / 2 };
           const collisionMargin = isSmall ? 15 : 6;
          
          const intersects = (r1, r2, margin) => {
            const shrink1 = { x: r1.x + margin, y: r1.y + margin, w: r1.w - margin * 2, h: r1.h - margin * 2 };
            const shrink2 = { x: r2.x + margin, y: r2.y + margin, w: r2.w - margin * 2, h: r2.h - margin * 2 };
            if (shrink1.w <= 0 || shrink1.h <= 0 || shrink2.w <= 0 || shrink2.h <= 0) return false;
            return shrink1.x < shrink2.x + shrink2.w &&
                   shrink1.x + shrink1.w > shrink2.x &&
                   shrink1.y < shrink2.y + shrink2.h &&
                   shrink1.y + shrink1.h > shrink2.y;
          };
          
          const hasCollision = placedRects.some(r => intersects(newRect, r, collisionMargin));
          if (!hasCollision) {
            placedRects.push(newRect);
            this.objectsToDraw.push({
              id: asset.id,
              img: img,
              x: rx,
              y: ry,
              w: newW,
              h: newH,
              cx: rx + newW / 2,
              cy: ry + newH / 2,
              angle: Math.floor(-25 + Math.random() * 50),
              flipX: Math.random() > 0.5,
              isSmall: isSmall,
              zOrder: passNum
            });
            selectedAssets.splice(i, 1);
            quadIdx++;
            foundPos = true;
            break;
          }
        }
      }
    }
    
    const diffCount = Math.min(this.numDifferences, this.objectsToDraw.length);
    this.differencesIndices = [];
    
    const smallIndices = [];
    const otherIndices = [];
    for (let i = 0; i < this.objectsToDraw.length; i++) {
      if (this.objectsToDraw[i].isSmall) smallIndices.push(i);
      else otherIndices.push(i);
    }
    
    this._shuffle(smallIndices);
    this._shuffle(otherIndices);
    const candidates = smallIndices.concat(otherIndices);
    const minDistance = 180.0;
    
    for (const idx of candidates) {
      if (this.differencesIndices.length >= diffCount) break;
      const o1 = this.objectsToDraw[idx];
      
      let tooClose = false;
      for (const selIdx of this.differencesIndices) {
        const o2 = this.objectsToDraw[selIdx];
        const dist = Math.sqrt(Math.pow(o1.cx - o2.cx, 2) + Math.pow(o1.cy - o2.cy, 2));
        if (dist < minDistance) {
          tooClose = true;
          break;
        }
      }
      
      if (!tooClose) {
        this.differencesIndices.push(idx);
      }
    }
    
    if (this.differencesIndices.length < diffCount) {
      const missing = diffCount - this.differencesIndices.length;
      const remaining = candidates.filter(i => !this.differencesIndices.includes(i));
      for (let i = 0; i < Math.min(missing, remaining.length); i++) {
        this.differencesIndices.push(remaining[i]);
      }
    }
  }
  
  pointer(sx, sy, type) {
    if (this.gameOver) {
      if (type === "down") {
        if (this.wonAll || this.timeLeft <= 0) {
          this.finishGame();
        } else {
          this.level += 1;
          this._sfx("level");
          if (this.level > this.maxLevels) {
            this.level = this.maxLevels;
            this.wonAll = true;
            this._sfx("win");
          } else {
            this._setupLevel();
            this.gameOver = false;
          }
        }
      }
      return;
    }
    
    if (type !== "down") return;
    
    const scale = Math.min(this.host.canvas.clientWidth / 1280, this.host.canvas.clientHeight / 720);
    const offX = (this.host.canvas.clientWidth - 1280 * scale) / 2;
    const offY = (this.host.canvas.clientHeight - 720 * scale) / 2;
    const rx = (sx - offX) / scale;
    const ry = (sy - offY) / scale;
    
    if (ry >= 10 && ry <= this.panelHeight - 10 && rx >= 10 && rx <= 1270) {
      const isRight = rx >= 640;
      const checkX = isRight ? rx - 640 : rx;
      const checkY = ry;
      
      let hit = false;
      for (const idx of this.differencesIndices) {
        if (idx in this.foundIndices) continue;
        const obj = this.objectsToDraw[idx];
        
        if (checkX >= obj.x && checkX <= obj.x + obj.w && checkY >= obj.y && checkY <= obj.y + obj.h) {
          this.foundIndices[idx] = 1.0;
          this._sfx("hit");
          
          let points = 500;
          if (this.comboTimer > 0) {
            this.combo += 1;
            const multiplier = 1.0 + this.combo * 0.5;
            points = Math.floor(points * multiplier);
            this.lastHitMsg = `COMBO X${multiplier}!`;
          } else {
            this.combo = 0;
            this.lastHitMsg = "+500";
          }
          
          this.comboTimer = 4.0;
          this.lastHitTimer = 1.5;
          this.currentScore += points;
          this.totalScore += points;
          hit = true;
          
          this._spawnConfetti(rx, ry);
          
          if (Object.keys(this.foundIndices).length === this.differencesIndices.length) {
            this.totalScore += Math.floor(this.timeLeft * 50);
            this.gameOver = true;
            this.victoryTimer = 2.0;
            this.screenShake = 20.0;
            this._sfx("win");
          }
          break;
        }
      }
      
      if (!hit) {
        this.wrongClicks += 1;
        this.combo = 0;
        this.comboTimer = 0;
        this.wrongClickTimer = 0.6;
        this.wrongClickPos = { x: rx, y: ry };
        this.screenShake = 8.0;
        this._sfx("error");
        this.currentScore = Math.max(0, this.currentScore - 150);
        this.totalScore = Math.max(0, this.totalScore - 150);
      }
    }
  }
  
  key(e, down) {
    if (!down) return;
    if (e.key === "Escape") {
      this.finishGame();
    }
  }
  
  update(dt) {
    if (!this.gameOver) {
      this.timeLeft -= dt;
      
      if (this.timeLeft > 0 && this.timeLeft <= 10.0) {
        const freq = 1.0 + ((10.0 - this.timeLeft) / 10.0) * 4.0;
        this.lastTickTime += dt * freq;
        if (this.lastTickTime >= 1.0) {
          this.lastTickTime -= 1.0;
          this._sfx("tick");
          this.screenShake = 5.0 + (10.0 - this.timeLeft);
        }
      }
      
      if (this.timeLeft <= 0) {
        this.timeLeft = 0;
        this.gameOver = true;
        this.victoryTimer = 0.0;
        this._sfx("error");
        this.screenShake = 10.0;
        this._spawnExplosion(640, 360);
      }
    }
    
    if (this.comboTimer > 0) this.comboTimer -= dt;
    if (this.lastHitTimer > 0) this.lastHitTimer -= dt;
    if (this.wrongClickTimer > 0) this.wrongClickTimer -= dt;
    if (this.screenShake > 0) this.screenShake -= dt * 30;
    
    if (this.gameOver && this.timeLeft <= 0) {
      this.victoryTimer += dt;
    } else if (this.victoryTimer > 0) {
      this.victoryTimer -= dt;
    }
    
    this.pulseTimer += dt * 5;
    
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.vy += 500 * dt;
      p.life -= dt;
      if (p.life <= 0) {
        this.particles.splice(i, 1);
      }
    }
    
    for (const idx in this.foundIndices) {
      if (this.foundIndices[idx] > 0) {
        this.foundIndices[idx] -= dt;
        if (this.foundIndices[idx] < 0) this.foundIndices[idx] = 0;
      }
    }
  }
  
  _spawnConfetti(cx, cy) {
    const colors = ["#ff3232", "#32ff32", "#3232ff", "#ffff32", "#ff64c8"];
    for (let i = 0; i < 100; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 300 + Math.random() * 500;
      this.particles.push({
        x: cx,
        y: cy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        color: colors[Math.floor(Math.random() * colors.length)],
        life: 1.0 + Math.random() * 1.5,
        size: 8 + Math.floor(Math.random() * 10),
        type: Math.random() > 0.5 ? "comic_sq" : "star"
      });
    }
  }
  
  _spawnExplosion(cx, cy) {
    const colors = ["#ff3232", "#ff6400", "#ffff02", "#c8c8c8"];
    for (let i = 0; i < 150; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 500 + Math.random() * 1300;
      this.particles.push({
        x: cx,
        y: cy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        color: colors[Math.floor(Math.random() * colors.length)],
        life: 1.0 + Math.random() * 2.0,
        size: 20 + Math.floor(Math.random() * 40),
        type: Math.random() > 0.6 ? "boom_cloud" : "star"
      });
    }
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
  
  _drawTextComic(ctx, text, fontStyleStr, x, y, colorStr) {
    ctx.save();
    ctx.font = fontStyleStr;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    
    ctx.fillStyle = "#000";
    const radiusOut = 3;
    const stepsOut = 12;
    for (let i = 0; i < stepsOut; i++) {
      const angle = (i * 2 * Math.PI) / stepsOut;
      const dx = Math.round(Math.cos(angle) * radiusOut);
      const dy = Math.round(Math.sin(angle) * radiusOut);
      ctx.fillText(text, x + dx, y + dy);
    }
    
    const radiusIn = 1.5;
    const stepsIn = 8;
    for (let i = 0; i < stepsIn; i++) {
      const angle = (i * 2 * Math.PI) / stepsIn;
      const dx = Math.round(Math.cos(angle) * radiusIn);
      const dy = Math.round(Math.sin(angle) * radiusIn);
      ctx.fillText(text, x + dx, y + dy);
    }
    
    ctx.fillStyle = colorStr;
    ctx.fillText(text, x, y);
    ctx.restore();
  }
  
  _drawVictorySunburst(ctx) {
    const numRays = 12;
    const rayAngle = 360 / numRays;
    const timeOffset = performance.now() * 0.01 * (Math.PI / 180);
    ctx.save();
    ctx.fillStyle = "rgba(255, 215, 0, 0.15)";
    for (let i = 0; i < numRays; i++) {
      const angle = i * rayAngle * (Math.PI / 180) + timeOffset;
      ctx.beginPath();
      ctx.moveTo(640, 360);
      ctx.lineTo(640 + Math.cos(angle - 0.2) * 1500, 360 + Math.sin(angle - 0.2) * 1500);
      ctx.lineTo(640 + Math.cos(angle + 0.2) * 1500, 360 + Math.sin(angle + 0.2) * 1500);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }
  
  _drawAnimatedObj(ctx, obj, idx, isRight) {
    ctx.save();
    
    let drawX = obj.x;
    let drawY = obj.y;
    if (isRight) {
      drawX += this.panelWidth;
    }
    
    let scale = 1.0;
    if (idx in this.foundIndices && this.foundIndices[idx] > 0) {
      const t = 1.0 - this.foundIndices[idx];
      scale = 1.0 + 0.3 * (1.0 - Math.abs(t - 0.5) * 2);
    }
    
    ctx.save();
    ctx.translate(drawX + obj.w / 2, drawY + obj.h / 2);
    ctx.rotate(obj.angle * Math.PI / 180);
    if (obj.flipX) ctx.scale(-1, 1);
    ctx.scale(scale, scale);
    
    // Ombra nativa accelerata hardware 2D in stile adesivo/fumetto
    ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
    ctx.shadowBlur = 2;
    ctx.shadowOffsetX = 5;
    ctx.shadowOffsetY = 5;
    
    ctx.drawImage(obj.img, -obj.w / 2, -obj.h / 2, obj.w, obj.h);
    ctx.restore();
    ctx.restore();
    
    if (idx in this.foundIndices) {
      ctx.save();
      const pulse = Math.sin(this.pulseTimer) * 6;
      const cx = drawX + obj.w / 2;
      const cy = drawY + obj.h / 2;
      const radius = Math.max(obj.w, obj.h) / 2 * scale + 10 + pulse;
      
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 6;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(cx, cy, radius + 2, 0, Math.PI * 2);
      ctx.stroke();
      
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();
      
      ctx.strokeStyle = "#32c832";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, radius - 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      
      if (this.foundIndices[idx] > 0.8) {
        this._drawStarburst(ctx, cx, cy, radius * 1.8);
      }
    }
  }
  
  _drawStarburst(ctx, cx, cy, size) {
    ctx.save();
    const pts = [];
    for (let i = 0; i < 14; i++) {
      const ang = i * (Math.PI * 2 / 14);
      const dist = i % 2 === 0 ? size : size * 0.4;
      pts.push({ x: cx + Math.cos(ang) * dist, y: cy + Math.sin(ang) * dist });
    }
    
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 10;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.fillStyle = "#ffd700";
    
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.fill();
    
    ctx.strokeStyle = "#ff6400";
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();
  }
  
  _drawParticles(ctx) {
    for (const p of this.particles) {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.life * 5);
      ctx.fillStyle = p.color;
      
      if (p.type === "comic_sq") {
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 3;
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.rect(-p.size / 2, -p.size / 2, p.size, p.size);
        ctx.stroke();
        ctx.fill();
      } else if (p.type === "boom_cloud") {
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fill();
      } else {
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 3;
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(0, -p.size / 2);
        ctx.lineTo(p.size / 4, p.size / 4);
        ctx.lineTo(-p.size / 4, p.size / 4);
        ctx.closePath();
        ctx.stroke();
        ctx.fill();
      }
      ctx.restore();
    }
  }
  
  _drawHUD(ctx) {
    const hudH = 85;
    const hudY = 720 - hudH - 20;
    
    ctx.save();
    ctx.fillStyle = this.uiTheme.hudBg;
    this._roundRect(ctx, 20, hudY, 1240, hudH, 15);
    ctx.fill();
    
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 4;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    this._roundRect(ctx, 20, hudY, 1240, hudH, 15);
    ctx.stroke();
    
    if (this.wrongClickTimer > 0) {
      const cx = this.wrongClickPos.x;
      const cy = this.wrongClickPos.y;
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 8;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx - 30, cy - 30);
      ctx.lineTo(cx + 30, cy + 30);
      ctx.moveTo(cx + 30, cy - 30);
      ctx.lineTo(cx - 30, cy + 30);
      ctx.stroke();
      
      ctx.strokeStyle = "#ff3232";
      ctx.lineWidth = 4;
      ctx.stroke();
    }
    
    const textY = hudY + hudH / 2;
    const safeLeft = 220;
    const safeRight = 1060;
    const msgCenterX = 640;
    
    let msg = "";
    let color = "#fff";
    
    if (!this.gameOver) {
      const remaining = this.differencesIndices.length - Object.keys(this.foundIndices).length;
      msg = `LIV ${this.level}/${this.maxLevels} - RIMANENTI: ${remaining}`;
      color = "#fff";
    } else if (this.timeLeft <= 0) {
      msg = "K.O. - TEMPO SCADUTO!";
      color = "#ff3232";
    } else if (this.wonAll) {
      msg = "SUPER CAMPIONE!";
      color = "#ffd700";
    } else {
      msg = "LIVELLO COMPLETATO!";
      color = "#32ff64";
    }
    
    this._drawTextComic(ctx, msg, "bold 28px Impact", msgCenterX, textY, color);
    this._drawTextComic(ctx, `SCORE: ${this.totalScore}`, "bold 28px Impact", safeLeft, textY, "#fff");
    
    const timeColor = this.timeLeft > 10 ? "#fff" : "#ff3232";
    const minutes = Math.floor(this.timeLeft / 60);
    const seconds = Math.floor(this.timeLeft % 60);
    const timeStr = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    
    let zoom = 1.0;
    if (this.timeLeft > 0 && this.timeLeft <= 10.0 && !this.gameOver) {
      const pulse = Math.abs(Math.sin(this.timeLeft * Math.PI * 3));
      zoom = 1.0 + pulse * 0.8 * ((10.0 - this.timeLeft) / 10.0);
    }
    
    ctx.save();
    ctx.translate(safeRight, textY);
    ctx.scale(zoom, zoom);
    this._drawTextComic(ctx, timeStr, "bold 32px Impact", 0, 0, timeColor);
    ctx.restore();
    ctx.restore();
  }
  
  _drawGameOverOverlay(ctx) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.78)";
    ctx.fillRect(0, 0, 1280, 720);
    
    const t = Math.min(1.0, this.victoryTimer * 3);
    const scale = Math.sin(t * Math.PI / 2);
    
    const boxW = Math.round(600 * scale);
    const boxH = Math.round(250 * scale);
    
    if (scale > 0.1) {
      ctx.save();
      ctx.translate(640, 320);
      
      ctx.fillStyle = "#000";
      this._roundRect(ctx, -boxW / 2 + 10, -boxH / 2 + 10, boxW, boxH, 15);
      ctx.fill();
      
      ctx.fillStyle = this.uiTheme.panelBg;
      this._roundRect(ctx, -boxW / 2, -boxH / 2, boxW, boxH, 15);
      ctx.fill();
      
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 8;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      this._roundRect(ctx, -boxW / 2, -boxH / 2, boxW, boxH, 15);
      ctx.stroke();
      
      this._drawTextComic(ctx, "GAME OVER!", "bold 80px Impact", 0, -30, "#ff3232");
      this._drawTextComic(ctx, `SCORE FINALE: ${this.totalScore}`, "bold 36px Impact", 0, 45, "#fff");
      
      if (this.victoryTimer > 1.0 && Math.sin(this.pulseTimer) > 0) {
        this._drawTextComic(ctx, "CLICCA PER USCIRE", "bold 32px Impact", 0, 160, "#fff");
      }
      ctx.restore();
    }
  }
  
  _drawVictoryOverlay(ctx) {
    const msg = this.wrongClicks === 0 ? "PERFECT!!!" : "WINNER!";
    const color = "#fff";
    this._drawTextComic(ctx, msg, "bold 100px Impact", 640, 310, color);
    
    if (this.lastHitTimer > 0) {
      ctx.save();
      const alpha = Math.min(1.0, this.lastHitTimer);
      ctx.globalAlpha = alpha;
      this._drawTextComic(ctx, this.lastHitMsg, "bold 38px Arial", 640, 80, "#ffff00");
      ctx.restore();
    }
    
    if (Math.sin(this.pulseTimer) > 0) {
      const nextMsg = this.level === this.maxLevels ? "CLICCA PER USCIRE" : "CLICCA PER CONTINUARE";
      this._drawTextComic(ctx, nextMsg, "bold 32px Impact", 640, 480, "#fff");
    }
  }
  
  finishGame() {
    const results = {
      success: this.wonAll,
      score: this.totalScore,
      wrong_clicks: this.wrongClicks,
      won_all: this.wonAll
    };
    this.host._minigameDone(results);
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
    
    let shx = 0;
    let shy = 0;
    if (this.screenShake > 0) {
      shx = -this.screenShake + Math.random() * this.screenShake * 2;
      shy = -this.screenShake + Math.random() * this.screenShake * 2;
      ctx.translate(shx, shy);
    }
    
    ctx.fillStyle = this.uiTheme.bg;
    ctx.fillRect(0, 0, 1280, 720);
    
    if (this.gameOver && this.victoryTimer > 0 && Object.keys(this.foundIndices).length === this.differencesIndices.length) {
      this._drawVictorySunburst(ctx);
    }
    
    ctx.fillStyle = this.uiTheme.panelBg;
    this._roundRect(ctx, 10, 10, 1260, this.panelHeight - 20, 15);
    ctx.fill();
    
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 4;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    this._roundRect(ctx, 10, 10, 1260, this.panelHeight - 20, 15);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(640, 10);
    ctx.lineTo(640, this.panelHeight - 10);
    ctx.stroke();
    
    for (let i = 0; i < this.objectsToDraw.length; i++) {
      this._drawAnimatedObj(ctx, this.objectsToDraw[i], i, false);
    }
    
    for (let i = 0; i < this.objectsToDraw.length; i++) {
      if (this.differencesIndices.includes(i)) {
        if (i in this.foundIndices) {
          this._drawAnimatedObj(ctx, this.objectsToDraw[i], i, true);
        }
      } else {
        this._drawAnimatedObj(ctx, this.objectsToDraw[i], i, true);
      }
    }
    
    this._drawParticles(ctx);
    this._drawHUD(ctx);
    
    if (this.gameOver) {
      if (Object.keys(this.foundIndices).length === this.differencesIndices.length) {
        this._drawVictoryOverlay(ctx);
      } else if (this.timeLeft <= 0) {
        this._drawGameOverOverlay(ctx);
      }
    }
    
    ctx.restore();
  }
}


(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["spot_differences"] = SpotDifferencesGame;
