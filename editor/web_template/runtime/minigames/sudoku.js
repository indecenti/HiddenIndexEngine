// ──────────────────────────────────────────────────────────────────────────
// SudokuBoard — replica dell'algoritmo di sudoku_game.py
// ──────────────────────────────────────────────────────────────────────────
class SudokuBoard {
  constructor(difficulty) {
    if (difficulty === 1) {
      this.n = 4;
      this.bw = 2;
      this.bh = 2;
    } else if (difficulty === 2) {
      this.n = 6;
      this.bw = 3;
      this.bh = 2;
    } else {
      this.n = 9;
      this.bw = 3;
      this.bh = 3;
    }
    
    this.grid = Array.from({ length: this.n }, () => Array(this.n).fill(0));
    this.solution = Array.from({ length: this.n }, () => Array(this.n).fill(0));
    this.fixed = Array.from({ length: this.n }, () => Array(this.n).fill(false));
    
    this.generate();
    this.applyDifficulty(difficulty);
  }
  
  generate() {
    for (let r = 0; r < this.n; r++) {
      for (let c = 0; c < this.n; c++) {
        const val = ((r * this.bh + Math.floor(r / this.bw) + c) % this.n) + 1;
        this.solution[r][c] = val;
        this.grid[r][c] = val;
      }
    }
    
    // Shuffle numeri
    const nums = Array.from({ length: this.n }, (_, i) => i + 1);
    this._shuffle(nums);
    const mapping = {};
    for (let i = 0; i < this.n; i++) {
      mapping[i + 1] = nums[i];
    }
    
    for (let r = 0; r < this.n; r++) {
      for (let c = 0; c < this.n; c++) {
        this.solution[r][c] = mapping[this.solution[r][c]];
        this.grid[r][c] = this.solution[r][c];
      }
    }
  }
  
  _shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const temp = arr[i];
      arr[i] = arr[j];
      arr[j] = temp;
    }
  }
  
  applyDifficulty(diff) {
    let removeCnt = 0;
    if (diff === 1) {
      removeCnt = Math.floor(this.n * this.n * 0.4);
    } else if (diff === 2) {
      removeCnt = Math.floor(this.n * this.n * 0.5);
    } else {
      removeCnt = Math.floor(this.n * this.n * 0.6);
    }
    
    const cells = [];
    for (let r = 0; r < this.n; r++) {
      for (let c = 0; c < this.n; c++) {
        cells.push({ r, c });
      }
    }
    this._shuffle(cells);
    
    for (let i = 0; i < removeCnt; i++) {
      const cell = cells[i];
      this.grid[cell.r][cell.c] = 0;
    }
    
    for (let r = 0; r < this.n; r++) {
      for (let c = 0; c < this.n; c++) {
        if (this.grid[r][c] !== 0) {
          this.fixed[r][c] = true;
        }
      }
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────
// SudokuGame — Porting 1:1 di SudokuGame da Python
// ──────────────────────────────────────────────────────────────────────────
class SudokuGame {
  constructor(host, base, strings) {
    this.host = host;
    this.base = base;
    this.strings = strings || {};
    this.level = 1;
    this.score = 0;
    this.maxLevels = 3;
    
    // Sfondi scuri e profondi per contrasto vibrante
    this.darkBgs = [
      "#192337", // Navy
      "#2d1937", // Deep Purple
      "#193223", // Forest
      "#3c1919", // Crimson
      "#28282d"  // Slate
    ];
    this.currentBgColor = this.darkBgs[Math.floor(Math.random() * this.darkBgs.length)];
    
    this.board = new SudokuBoard(this.level);
    this.selectedCell = null;
    
    // Layout
    this.gridSize = 0;
    this.cellSize = 0;
    this.gridX = 0;
    this.gridY = 0;
    this.numpadRects = [];
    this.btnClear = { x: 0, y: 0, w: 0, h: 0 };
    this.btnSubmit = { x: 0, y: 0, w: 0, h: 0 };
    
    this.state = "PLAYING"; // PLAYING, GAME_OVER, TIME_UP
    this.timerMsg = 0.0;
    this.errorCells = [];
    
    // Countdown
    this.gameTimer = 0.0;
    this.maxTime = 0.0;
    this._resetTimer();
    
    // Tutorial
    this.tutorialStep = this.level === 1 ? 0 : -1;
    this.tutorialTimer = 0.0;
    this.tutAnimScale = 0.0;
    this.tutPulse = 0.0;
    
    // Feedback
    this.infoMsg = "";
    this.infoTimer = 0.0;
    this.shakeTimer = 0.0;
    this.panicPulse = 0.0;
    this.heartbeatTimer = 0.0;
    this.lastTickTime = 0.0;
  }
  
  t(k, fb) { return this.strings[k] || fb || k; }
  
  _resetTimer() {
    this.maxTime = Math.max(60.0, 210.0 - (this.level * 30.0));
    this.gameTimer = this.maxTime;
  }
  
  _calculateLayout() {
    const W = 1280;
    const H = 720;
    
    this.gridSize = Math.round(H * 0.75);
    this.cellSize = this.gridSize / this.board.n;
    
    // Griglia spostata a sinistra per far spazio al numpad
    this.gridX = Math.round((W / 2.0) - (this.gridSize / 2.0) - (H * 0.15));
    this.gridY = Math.round((H / 2.0) - (this.gridSize / 2.0));
    
    // Numpad
    const numpadX = Math.round(this.gridX + this.gridSize + (H * 0.05));
    const numpadY = Math.round(this.gridY + (H * 0.05));
    const btnS = Math.round(H * 0.09);
    const gap = Math.round(H * 0.02);
    
    const colsN = this.board.n === 4 ? 2 : 3;
    this.numpadRects = [];
    
    for (let i = 1; i <= this.board.n; i++) {
      const row = Math.floor((i - 1) / colsN);
      const col = (i - 1) % colsN;
      const bx = Math.round(numpadX + col * (btnS + gap));
      const by = Math.round(numpadY + row * (btnS + gap));
      this.numpadRects.push({ x: bx, y: by, w: btnS, h: btnS, val: i });
    }
    
    const btnW = Math.round(btnS * colsN + gap * (colsN - 1));
    const btnH = Math.round(H * 0.07);
    const nRows = Math.floor((this.board.n - 1) / colsN) + 1;
    const clearY = Math.round(numpadY + nRows * (btnS + gap));
    
    this.btnClear = { x: numpadX, y: clearY, w: btnW, h: btnH };
    this.btnSubmit = { x: numpadX, y: Math.round(clearY + btnH + gap), w: btnW, h: btnH };
  }
  
  load() {
    this._calculateLayout();
    return Promise.resolve();
  }
  
  start() {}
  
  _sfx(name) {
    if (this.host.audioManager) {
      this.host.audioManager.playSfx(name);
    }
  }
  
  _checkSolution() {
    const errors = [];
    let isFull = true;
    
    for (let r = 0; r < this.board.n; r++) {
      for (let c = 0; c < this.board.n; c++) {
        const val = this.board.grid[r][c];
        if (val === 0) {
          isFull = false;
        } else if (val !== this.board.solution[r][c]) {
          errors.push({ r, c });
        }
      }
    }
    
    if (errors.length > 0) {
      this.errorCells = errors;
      this.score = Math.max(0, this.score - 50);
      this.infoMsg = "ERRORI TROVATI!";
      this.infoTimer = 1.5;
      this.shakeTimer = 0.4;
      this._sfx("error");
    } else if (!isFull) {
      this.infoMsg = "INCOMPLETO!";
      this.infoTimer = 1.0;
      this._sfx("hit");
    } else {
      this.score += 1000 * this.level;
      if (this.level >= this.maxLevels) {
        this.state = "GAME_OVER";
        this.timerMsg = 3.0;
        this._sfx("win");
      } else {
        this.level += 1;
        this.board = new SudokuBoard(this.level);
        this._calculateLayout();
        this.currentBgColor = this.darkBgs[Math.floor(Math.random() * this.darkBgs.length)];
        this.selectedCell = null;
        this.errorCells = [];
        this.infoMsg = "LIVELLO COMPLETATO!";
        this.infoTimer = 2.0;
        this._resetTimer();
        this._sfx("level");
      }
    }
  }
  
  pointer(sx, sy, type) {
    if (this.state !== "PLAYING" || this.shakeTimer > 0) {
      if (type === "down") {
        if (this.state === "GAME_OVER" || this.state === "TIME_UP") {
          this.finishGame();
        }
      }
      return;
    }
    
    if (type !== "down") return;
    
    const scale = Math.min(this.host.canvas.clientWidth / 1280, this.host.canvas.clientHeight / 720);
    const offX = (this.host.canvas.clientWidth - 1280 * scale) / 2;
    const offY = (this.host.canvas.clientHeight - 720 * scale) / 2;
    const mx = (sx - offX) / scale;
    const my = (sy - offY) / scale;
    
    const gx = this.gridX;
    const gy = this.gridY;
    const gs = this.gridSize;
    
    // Click griglia
    if (mx >= gx && mx <= gx + gs && my >= gy && my <= gy + gs) {
      let c = Math.floor((mx - gx) / (gs / this.board.n));
      let r = Math.floor((my - gy) / (gs / this.board.n));
      c = Math.max(0, Math.min(this.board.n - 1, c));
      r = Math.max(0, Math.min(this.board.n - 1, r));
      
      if (!this.board.fixed[r][c]) {
        this.selectedCell = { r, c };
        if (this.tutorialStep === 0) {
          this.tutorialStep = 1;
          this.tutAnimScale = 0;
        } else if (this.tutorialStep === 1) {
          this.tutorialStep = 2;
          this.tutorialTimer = 0;
          this.tutAnimScale = 0;
        }
        this._sfx("hit");
      }
    }
    
    // Click tastierino o extra
    if (this.selectedCell) {
      const { r, c } = this.selectedCell;
      for (const rect of this.numpadRects) {
        if (mx >= rect.x && mx <= rect.x + rect.w && my >= rect.y && my <= rect.y + rect.h) {
          const val = rect.val;
          this.board.grid[r][c] = val;
          
          if (val !== this.board.solution[r][c]) {
            if (!this.errorCells.some(cell => cell.r === r && cell.c === c)) {
              this.errorCells.push({ r, c });
            }
            this.shakeTimer = 0.3;
            this.score = Math.max(0, this.score - 20);
            this._sfx("error");
          } else {
            this.errorCells = this.errorCells.filter(cell => !(cell.r === r && cell.c === c));
            if (this.tutorialStep === 2) {
              this.tutorialStep = 3;
              this.tutorialTimer = 5.0;
              this.tutAnimScale = 0;
            }
            this._sfx("hit");
            
            // Auto-check se pieno e senza errori
            let isFull = true;
            for (let tr = 0; tr < this.board.n; tr++) {
              for (let tc = 0; tc < this.board.n; tc++) {
                if (this.board.grid[tr][tc] === 0) isFull = false;
              }
            }
            if (isFull && this.errorCells.length === 0) {
              this._checkSolution();
            }
          }
        }
      }
      
      const btn = this.btnClear;
      if (mx >= btn.x && mx <= btn.x + btn.w && my >= btn.y && my <= btn.y + btn.h) {
        this.board.grid[r][c] = 0;
        this.errorCells = this.errorCells.filter(cell => !(cell.r === r && cell.c === c));
        this._sfx("hit");
      }
    }
    
    const submit = this.btnSubmit;
    if (mx >= submit.x && mx <= submit.x + submit.w && my >= submit.y && my <= submit.y + submit.h) {
      this._checkSolution();
    }
  }
  
  key(e, down) {
    if (!down) return;
    if (e.key === "Escape") {
      this.finishGame();
    }
  }
  
  update(dt) {
    if (this.infoTimer > 0) this.infoTimer = Math.max(0.0, this.infoTimer - dt);
    if (this.shakeTimer > 0) this.shakeTimer = Math.max(0.0, this.shakeTimer - dt);
    
    if (this.tutorialTimer > 0) {
      this.tutorialTimer -= dt;
      if (this.tutorialTimer <= 0) {
        const oldStep = this.tutorialStep;
        if (this.tutorialStep === 3 || this.tutorialStep === 4) {
          this.tutorialStep += 1;
          if (this.tutorialStep <= 5) {
            this.tutorialTimer = 5.0;
          } else {
            this.tutorialStep = -1;
          }
        }
        if (oldStep !== this.tutorialStep && this.tutorialStep !== -1) {
          this.tutAnimScale = 0;
          this._sfx("level");
        }
      }
    }
    
    this.tutAnimScale = Math.min(1.0, this.tutAnimScale + dt * 5.0);
    this.tutPulse = Math.abs(Math.sin(performance.now() * 0.006));
    
    if (this.state === "PLAYING") {
      this.gameTimer -= dt;
      
      if (this.gameTimer < 10.0 && this.gameTimer > 0) {
        const freq = 5.0 + (10.0 - this.gameTimer) * 1.5;
        this.panicPulse = Math.abs(Math.sin(performance.now() * 0.001 * freq)) * (1.1 - this.gameTimer / 10.0);
        
        this.heartbeatTimer += dt * freq;
        if (this.heartbeatTimer >= Math.PI) {
          this.heartbeatTimer -= Math.PI;
          this._sfx("tick");
        }
      } else {
        this.panicPulse = 0.0;
      }
      
      if (this.gameTimer <= 0) {
        this.gameTimer = 0;
        this.state = "TIME_UP";
        this.timerMsg = 3.0;
        this._sfx("error");
      }
    }
    
    if (this.state === "GAME_OVER" || this.state === "TIME_UP") {
      this.timerMsg -= dt;
      if (this.timerMsg <= 0) {
        this.finishGame();
      }
    }
  }
  
  finishGame() {
    const results = {
      success: this.state === "GAME_OVER",
      score: this.score
    };
    this.host._minigameDone(results);
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
    
    ctx.fillStyle = colorStr;
    ctx.fillText(text, x, y);
    ctx.restore();
  }
  
  _drawComicTooltip(ctx, text, cx, cy, arrowPos = "down") {
    let scale = this.tutAnimScale;
    if (scale < 1.0) {
      scale = -scale * (scale - 2); // Quad ease out
    }
    
    const padding = 15;
    const lines = text.split("\n");
    
    ctx.save();
    ctx.font = "bold 18px Impact";
    ctx.textBaseline = "top";
    
    let maxW = 0;
    let totalH = 0;
    const lineHeights = [];
    
    for (const line of lines) {
      const w = ctx.measureText(line).width;
      if (w > maxW) maxW = w;
      const h = 24;
      lineHeights.push(h);
      totalH += h;
    }
    
    const tw = Math.round((maxW + padding * 2) * scale);
    const th = Math.round((totalH + padding * 2) * scale);
    
    if (tw < 10 || th < 10) {
      ctx.restore();
      return;
    }
    
    let rx, ry;
    if (arrowPos === "down") {
      rx = cx - tw / 2;
      ry = cy - th - 20;
    } else if (arrowPos === "up") {
      rx = cx - tw / 2;
      ry = cy + 20;
    } else if (arrowPos === "left") {
      rx = cx + 20;
      ry = cy - th / 2;
    } else {
      rx = cx - tw - 20;
      ry = cy - th / 2;
    }
    
    // Keep inside boundaries
    rx = Math.max(10, Math.min(1280 - tw - 10, rx));
    ry = Math.max(10, Math.min(720 - th - 10, ry));
    
    const off = Math.round(12 * scale);
    const hOff = Math.round(24 * scale);
    let pts = [];
    if (arrowPos === "down") {
      pts = [{ x: cx, y: cy - 5 }, { x: cx - off, y: cy - hOff }, { x: cx + off, y: cy - hOff }];
    } else if (arrowPos === "up") {
      pts = [{ x: cx, y: cy + 5 }, { x: cx - off, y: cy + hOff }, { x: cx + off, y: cy + hOff }];
    } else if (arrowPos === "left") {
      pts = [{ x: cx + 5, y: cy }, { x: cx + hOff, y: cy - off }, { x: cx + hOff, y: cy + off }];
    } else {
      pts = [{ x: cx - 5, y: cy }, { x: cx - hOff, y: cy - off }, { x: cx - hOff, y: cy + off }];
    }
    
    // 1. Disegna riempimento corpo bolla
    ctx.fillStyle = "#fff";
    this._roundRect(ctx, rx, ry, tw, th, 12);
    ctx.fill();
    
    // 2. Disegna riempimento coda
    if (scale > 0.5) {
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo(pts[1].x, pts[1].y);
      ctx.lineTo(pts[2].x, pts[2].y);
      ctx.closePath();
      ctx.fill();
    }
    
    // 3. Disegna bordo corpo bolla
    ctx.strokeStyle = "#141414";
    ctx.lineWidth = 4;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    this._roundRect(ctx, rx, ry, tw, th, 12);
    ctx.stroke();
    
    // 4. Copri la linea divisoria (re-fill coda) e disegna i bordi esterni della coda
    if (scale > 0.5) {
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo(pts[1].x, pts[1].y);
      ctx.lineTo(pts[2].x, pts[2].y);
      ctx.closePath();
      ctx.fill();
      
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo(pts[1].x, pts[1].y);
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo(pts[2].x, pts[2].y);
      ctx.stroke();
    }
    
    // Scrittura testi
    if (scale > 0.8) {
      ctx.fillStyle = "#141414";
      ctx.textAlign = "center";
      let currY = ry + padding;
      for (let i = 0; i < lines.length; i++) {
        ctx.fillText(lines[i], rx + tw / 2, currY);
        currY += lineHeights[i];
      }
    }
    
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
    
    let gx = this.gridX;
    let gy = this.gridY;
    let gs = this.gridSize;
    
    // Shake o Zoom di panico
    if (this.panicPulse > 0) {
      const zoom = 1.0 + this.panicPulse * 0.03;
      gs = this.gridSize * zoom;
      gx = this.gridX - (gs - this.gridSize) / 2;
      gy = this.gridY - (gs - this.gridSize) / 2;
      
      const shakeAmp = 12 * this.panicPulse;
      gx += Math.sin(performance.now() * 0.06) * shakeAmp;
      gy += Math.cos(performance.now() * 0.055) * (shakeAmp / 2);
    } else if (this.shakeTimer > 0) {
      const shakeAmp = 8;
      gx += Math.sin(this.shakeTimer * 40) * shakeAmp;
    }
    
    ctx.fillStyle = this.currentBgColor;
    ctx.fillRect(0, 0, 1280, 720);
    
    // Score e livello
    const txtLevel = `${this.t("sudoku_level", "Livello")} ${this.level}/${this.maxLevels}`;
    const txtScore = `${this.t("sudoku_score", "Punteggio:")} ${this.score}`;
    
    this._drawTextComic(ctx, txtLevel, "bold 32px Impact", 160, 50, "#fff");
    this._drawTextComic(ctx, txtScore, "bold 28px Impact", 160, 90, "#fff");
    
    // Timer
    if (this.state === "PLAYING") {
      const mins = Math.floor(this.gameTimer / 60);
      const secs = Math.floor(this.gameTimer % 60);
      const txtTimer = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
      
      let tCol = "#fff";
      let tx = 1120;
      let ty = 50;
      if (this.gameTimer < 10.0) {
        const pulse = Math.abs(Math.sin(performance.now() * 0.01));
        tCol = `rgb(255, ${Math.round(255 * (1 - pulse))}, ${Math.round(255 * (1 - pulse))})`;
        tx += Math.sin(performance.now() * 0.05) * 4;
        ty += Math.cos(performance.now() * 0.045) * 2;
      }
      this._drawTextComic(ctx, txtTimer, "bold 32px Impact", tx, ty, tCol);
    }
    
    // Sfondo griglia
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(Math.round(gx), Math.round(gy), Math.round(gs), Math.round(gs));
    
    // Disegna celle
    for (let r = 0; r < this.board.n; r++) {
      for (let c = 0; c < this.board.n; c++) {
        const cx = Math.round(gx + c * (gs / this.board.n));
        const cy = Math.round(gy + r * (gs / this.board.n));
        const cw = Math.round(gx + (c + 1) * (gs / this.board.n)) - cx;
        const ch = Math.round(gy + (r + 1) * (gs / this.board.n)) - cy;
        
        const isSel = this.selectedCell && this.selectedCell.r === r && this.selectedCell.c === c;
        const isErr = this.errorCells.some(cell => cell.r === r && cell.c === c);
        
        if (isSel) {
          let colorPulse = "#ffff64";
          if (this.tutorialStep !== -1) {
            colorPulse = `rgb(255, 255, ${Math.round(100 + this.tutPulse * 155)})`;
          }
          ctx.fillStyle = colorPulse;
          ctx.fillRect(cx, cy, cw, ch);
        } else if (isErr) {
          ctx.fillStyle = "#ffc8c8";
          ctx.fillRect(cx, cy, cw, ch);
        }
        
        const val = this.board.grid[r][c];
        if (val !== 0) {
          const color = this.board.fixed[r][c] ? "#141414" : (isErr ? "#dc2828" : "#1e64c8");
          ctx.save();
          ctx.font = `bold ${Math.round(cw * 0.7)}px Impact`;
          ctx.fillStyle = color;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(val.toString(), cx + cw / 2, cy + ch / 2);
          ctx.restore();
        }
      }
    }
    
    // Linee griglia
    for (let i = 0; i <= this.board.n; i++) {
      const ly = Math.round(gy + i * (gs / this.board.n));
      const lx = Math.round(gx + i * (gs / this.board.n));
      
      let isThick = i % this.board.bh === 0;
      let thick = isThick ? 4 : 1;
      let color = isThick ? "#141414" : "#3c3c3c";
      if (i === 0 || i === this.board.n) thick = 6;
      
      ctx.strokeStyle = color;
      ctx.lineWidth = thick;
      ctx.beginPath();
      ctx.moveTo(Math.round(gx), ly);
      ctx.lineTo(Math.round(gx + gs), ly);
      ctx.stroke();
      
      isThick = i % this.board.bw === 0;
      thick = isThick ? 4 : 1;
      color = isThick ? "#141414" : "#3c3c3c";
      if (i === 0 || i === this.board.n) thick = 6;
      ctx.strokeStyle = color;
      ctx.lineWidth = thick;
      ctx.beginPath();
      ctx.moveTo(lx, Math.round(gy));
      ctx.lineTo(lx, Math.round(gy + gs));
      ctx.stroke();
    }
    
    // Info Message box
    if (this.infoTimer > 0 && this.infoMsg) {
      ctx.save();
      const alpha = Math.min(1.0, this.infoTimer);
      ctx.globalAlpha = alpha;
      
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = 4;
      
      const boxW = 320;
      const boxH = 100;
      const bx = Math.round(gx + gs / 2 - boxW / 2);
      const by = Math.round(gy + gs / 2 - boxH / 2);
      
      this._roundRect(ctx, bx, by, boxW, boxH, 15);
      ctx.fill();
      ctx.stroke();
      
      const txtColor = this.infoMsg.includes("ERRORI") ? "#dc2828" : "#f07832";
      this._drawTextComic(ctx, this.infoMsg, "bold 32px Impact", bx + boxW / 2, by + boxH / 2, txtColor);
      ctx.restore();
    }
    
    // Numpad
    for (const rect of this.numpadRects) {
      const rx = Math.round(rect.x);
      const ry = Math.round(rect.y);
      const rw = Math.round(rect.w);
      const rh = Math.round(rect.h);
      
      ctx.fillStyle = "#f07832";
      ctx.fillRect(rx, ry, rw, rh);
      
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = 3;
      ctx.strokeRect(rx, ry, rw, rh);
      
      this._drawTextComic(ctx, rect.val.toString(), "bold 36px Impact", rx + rw / 2, ry + rh / 2, "#fff");
    }
    
    // Buttons
    const btnCol = "#f07832";
    for (const btn of [
      { r: this.btnClear, text: this.t("sudoku_clear", "CANC") },
      { r: this.btnSubmit, text: this.t("sudoku_submit", "VERIFICA") }
    ]) {
      const bx = Math.round(btn.r.x);
      const by = Math.round(btn.r.y);
      const bw = Math.round(btn.r.w);
      const bh = Math.round(btn.r.h);
      
      ctx.fillStyle = btnCol;
      ctx.fillRect(bx, by, bw, bh);
      
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = 3;
      ctx.strokeRect(bx, by, bw, bh);
      
      this._drawTextComic(ctx, btn.text, "bold 24px Impact", bx + bw / 2, by + bh / 2, "#fff");
    }
    
    // GameOver / TimeUp Overlays
    if (this.state === "GAME_OVER") {
      const progress = Math.max(0.0, Math.min(1.0, (3.0 - this.timerMsg) / 0.5));
      ctx.fillStyle = `rgba(0, 0, 0, ${0.78 * progress})`;
      ctx.fillRect(0, 0, 1280, 720);
      
      if (progress >= 1.0) {
        const bounce = Math.abs(Math.sin(this.timerMsg * 5)) * 20;
        const color = Math.floor(this.timerMsg * 10) % 2 === 0 ? "#ffff00" : "#ff6400";
        
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "#141414";
        ctx.lineWidth = 6;
        
        const bx = 640 - 250;
        const by = 360 - 75 - bounce;
        this._roundRect(ctx, bx, by, 500, 150, 20);
        ctx.fill();
        ctx.stroke();
        
        this._drawTextComic(ctx, this.t("sudoku_game_over", "COMPLETATO!"), "bold 56px Impact", 640, 360 - bounce, color);
      }
    }
    
    if (this.state === "TIME_UP") {
      ctx.fillStyle = "rgba(100, 0, 0, 0.7)";
      ctx.fillRect(0, 0, 1280, 720);
      
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = 6;
      
      const bx = 640 - 250;
      const by = 360 - 75;
      this._roundRect(ctx, bx, by, 500, 150, 20);
      ctx.fill();
      ctx.stroke();
      
      this._drawTextComic(ctx, this.t("sudoku_time_up", "TEMPO SCADUTO!"), "bold 52px Impact", 640, 360, "#ffff00");
    }
    
    // Tutorial
    if (this.tutorialStep >= 0) {
      if (this.tutorialStep === 0) {
        const msg = this.t("tut_step_0", "Ciao! Riempi la griglia: ogni numero deve essere unico per riga, colonna e quadrato.\nClicca una cella vuota per iniziare!");
        this._drawComicTooltip(ctx, msg, gx + gs / 2, gy + gs / 2, "down");
      } else if (this.tutorialStep === 1) {
        const msg = this.t("tut_step_1", "Per iniziare,\nclicca una cella vuota.");
        this._drawComicTooltip(ctx, msg, gx + gs / 2, gy + gs / 2, "down");
      } else if (this.tutorialStep === 2) {
        let valSug = 1;
        let targetX = 850;
        let targetY = 360;
        
        if (this.selectedCell) {
          const { r, c } = this.selectedCell;
          valSug = this.board.solution[r][c];
          for (const rect of this.numpadRects) {
            if (rect.val === valSug) {
              targetX = rect.x + rect.w / 2;
              targetY = rect.y + rect.h / 2;
              break;
            }
          }
        }
        
        const msgBase = this.t("tut_step_2", "Ottimo!\nOra clicca un numero a destra.");
        this._drawComicTooltip(ctx, msgBase, targetX, targetY, "right");
      } else if (this.tutorialStep === 3) {
        const msg = this.t("tut_step_3", "Attento al tempo!\nSe scade, la sfida arcade finisce.");
        this._drawComicTooltip(ctx, msg, 1120, 90, "up");
      } else if (this.tutorialStep === 4) {
        const msg = this.t("tut_step_4", "Fallo il più velocemente possibile.\nBuona fortuna!");
        this._drawComicTooltip(ctx, msg, gx + gs / 2, gy + gs / 2, "down");
      }
    }
    
    // Red panic vignette
    if (this.state === "PLAYING" && this.gameTimer < 10.0 && this.gameTimer > 0) {
      const alpha = this.panicPulse * 0.45;
      ctx.fillStyle = `rgba(200, 0, 0, ${alpha})`;
      const border = 108;
      
      // Top
      ctx.fillRect(0, 0, 1280, border);
      // Bottom
      ctx.fillRect(0, 720 - border, 1280, border);
      // Left
      ctx.fillRect(0, border, border, 720 - border * 2);
      // Right
      ctx.fillRect(1280 - border, border, border, 720 - border * 2);
    }
    
    ctx.restore();
  }
}


(window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {})["sudoku"] = SudokuGame;
