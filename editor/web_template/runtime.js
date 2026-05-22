/*
 * runtime.js — Web runtime per HiddenEngine.
 *
 * Obiettivo focale: le coordinate degli oggetti a schermo devono rispecchiare
 * PERFETTAMENTE l'editor/engine Python. Tutte le trasformazioni qui replicano
 * 1:1 engine/scaling_manager.py, engine/core.py (rendering) e
 * engine/click_detector.py (hit test).
 *
 * Convenzioni replicate:
 *  - Le coord x/y degli oggetti sono in spazio-pixel del background originale.
 *  - rect: x/y = top-left; circle: x/y = centro.
 *  - L'icona viene STIRATA alla dimensione hitbox (width x height in bg-space),
 *    non al suo aspect ratio nativo.
 *  - Rotazione Pygame = CCW per angoli positivi -> in canvas si ruota di -angle.
 *  - Ordine trasformazioni surface: scale -> (warp) -> flip -> rotate -> alpha.
 */

"use strict";

// ──────────────────────────────────────────────────────────────────────────
// ScalingManager — replica di engine/scaling_manager.py
// ──────────────────────────────────────────────────────────────────────────
class ScalingManager {
  constructor() {
    this.screenW = 1280;
    this.screenH = 720;
    this.bgDisplayScale = 1.0;
    this.bgScreenX = 0.0;
    this.bgScreenY = 0.0;
    this.bgScreenW = 1280;
    this.bgScreenH = 720;
  }

  updateScreenSize(w, h) {
    this.screenW = w;
    this.screenH = h;
  }

  // engine/scaling_manager.py:set_background
  setBackground(bgW, bgH, bgScale) {
    bgScale = bgScale || 1.0;
    const logicalW = bgW * bgScale;
    const logicalH = bgH * bgScale;
    const fitScale = Math.min(this.screenW / logicalW, this.screenH / logicalH);
    this.bgDisplayScale = fitScale * bgScale;
    const displayW = logicalW * fitScale;
    const displayH = logicalH * fitScale;
    this.bgScreenX = (this.screenW - displayW) / 2;
    this.bgScreenY = (this.screenH - displayH) / 2;
    this.bgScreenW = displayW;
    this.bgScreenH = displayH;
  }

  bgToScreen(bx, by) {
    return [bx * this.bgDisplayScale + this.bgScreenX,
            by * this.bgDisplayScale + this.bgScreenY];
  }

  screenToBg(sx, sy) {
    return [(sx - this.bgScreenX) / this.bgDisplayScale,
            (sy - this.bgScreenY) / this.bgDisplayScale];
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Geometria hit-test — replica di engine/click_detector.py
// ──────────────────────────────────────────────────────────────────────────
function rotatePoint(px, py, cx, cy, angleDeg) {
  // Replica _rotate_point: CCW Pygame con nx=tx*cos - ty*sin, ny=tx*sin + ty*cos
  const rad = angleDeg * Math.PI / 180;
  const cosA = Math.cos(rad), sinA = Math.sin(rad);
  const tx = px - cx, ty = py - cy;
  const nx = tx * cosA - ty * sinA;
  const ny = tx * sinA + ty * cosA;
  return [nx + cx, ny + cy];
}

function hasWarp(obj) {
  const c = obj.corners;
  if (!c) return false;
  return c.some(p => p[0] !== 0 || p[1] !== 0);
}

function pointInPoly(px, py, poly) {
  // Ray casting — replica _is_point_in_poly
  let inside = false;
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect = ((yi > py) !== (yj > py)) &&
      (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function warpPoly(obj, cx, cy) {
  // Costruisce il poligono deformato in bg-space (replica _hit_rect/_hit_circle warp)
  const w = obj.width, h = obj.height;
  const x = (obj.detection_type === "circle")
    ? obj.x - (obj.width > 0 ? obj.width : obj.radius * 2) / 2
    : obj.x;
  const y = (obj.detection_type === "circle")
    ? obj.y - (obj.height > 0 ? obj.height : obj.radius * 2) / 2
    : obj.y;
  const ww = (obj.detection_type === "circle") ? (obj.width > 0 ? obj.width : obj.radius * 2) : w;
  const hh = (obj.detection_type === "circle") ? (obj.height > 0 ? obj.height : obj.radius * 2) : h;
  const c = obj.corners;
  let pts = [
    [x + c[0][0], y + c[0][1]],
    [x + ww + c[1][0], y + c[1][1]],
    [x + ww + c[2][0], y + hh + c[2][1]],
    [x + c[3][0], y + hh + c[3][1]],
  ];
  if (obj.flip_x || obj.flip_y) {
    pts = pts.map(([px, py]) => {
      if (obj.flip_x) px = 2 * cx - px;
      if (obj.flip_y) py = 2 * cy - py;
      return [px, py];
    });
  }
  if (obj.rotation) {
    pts = pts.map(p => rotatePoint(p[0], p[1], cx, cy, obj.rotation));
  }
  return pts;
}

function hitTest(obj, bx, by) {
  if (obj.detection_type === "rect") return hitRect(obj, bx, by);
  if (obj.detection_type === "circle") return hitCircle(obj, bx, by);
  // mask -> fallback cerchio stimato (mask pixel-perfect non supportato nel web v1)
  const r = (obj.width || obj.height) ? Math.max(obj.width, obj.height) / 2 : 30;
  const dx = bx - obj.x, dy = by - obj.y;
  return dx * dx + dy * dy <= r * r;
}

function hitCircle(obj, bx, by) {
  if (hasWarp(obj)) {
    const cx = obj.x, cy = obj.y;
    return pointInPoly(bx, by, warpPoly(obj, cx, cy));
  }
  let rx = obj.width > 0 ? obj.width / 2 : obj.radius;
  let ry = obj.height > 0 ? obj.height / 2 : obj.radius;
  if (rx <= 0) rx = 1.0;
  if (ry <= 0) ry = 1.0;
  let dx = bx - obj.x, dy = by - obj.y;
  if (obj.rotation) {
    const rad = -obj.rotation * Math.PI / 180;
    const c = Math.cos(rad), s = Math.sin(rad);
    const rdx = dx * c - dy * s;
    const rdy = dx * s + dy * c;
    dx = rdx; dy = rdy;
  }
  return (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.0001;
}

function hitRect(obj, bx, by) {
  const cx = obj.x + obj.width / 2;
  const cy = obj.y + obj.height / 2;
  if (hasWarp(obj)) {
    return pointInPoly(bx, by, warpPoly(obj, cx, cy));
  }
  let rx = bx, ry = by;
  if (obj.rotation) {
    [rx, ry] = rotatePoint(bx, by, cx, cy, -obj.rotation);
  }
  const halfW = obj.width / 2, halfH = obj.height / 2;
  return (cx - halfW <= rx && rx <= cx + halfW &&
          cy - halfH <= ry && ry <= cy + halfH);
}

// ──────────────────────────────────────────────────────────────────────────
// Object geometry per il rendering — replica engine/core.py
// ──────────────────────────────────────────────────────────────────────────
function objCenterAndSize(obj) {
  if (obj.detection_type === "rect") {
    return {
      cx: obj.x + obj.width / 2,
      cy: obj.y + obj.height / 2,
      w: obj.width,
      h: obj.height,
    };
  }
  const w = obj.width > 0 ? obj.width : obj.radius * 2;
  const h = obj.height > 0 ? obj.height : obj.radius * 2;
  return { cx: obj.x, cy: obj.y, w, h };
}

// Filtro per-pixel ESATTO come engine: grayscale (engine/utils.py:apply_grayscale,
// luma Rec.601) + color_filter (BLEND_RGBA_MULT, moltiplicazione per canale).
// Un unico feColorMatrix SVG in spazio sRGB: M = Tint . Gray.
//   gray:  out = c*(1-f) + luma*f,  luma = 0.299R+0.587G+0.114B
//   tint:  out = c * (tint/255)  per canale,  alpha invariato
// Via ctx.filter -> nessun getImageData, quindi sicuro anche da file:// (no taint).
let _fxSvgMat = null;
function _fxFilterUrl(grayFactor, gsOn, colorFilter) {
  const f = gsOn ? Math.max(0, Math.min(1, grayFactor != null ? grayFactor : 1)) : 0;
  const tr = (colorFilter ? colorFilter[0] : 255) / 255;
  const tg = (colorFilter ? colorFilter[1] : 255) / 255;
  const tb = (colorFilter ? colorFilter[2] : 255) / 255;
  if (!_fxSvgMat) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("aria-hidden", "true");
    svg.style.position = "absolute"; svg.style.width = "0"; svg.style.height = "0";
    const filter = document.createElementNS(NS, "filter");
    filter.setAttribute("id", "hie-fx");
    filter.setAttribute("color-interpolation-filters", "sRGB"); // come l'engine: math su sRGB
    const m = document.createElementNS(NS, "feColorMatrix");
    m.setAttribute("type", "matrix");
    filter.appendChild(m); svg.appendChild(filter); document.body.appendChild(svg);
    _fxSvgMat = m;
  }
  const a = 1 - f, R = 0.299, G = 0.587, B = 0.114;
  // riga del grayscale, poi scalata per la tinta del canale corrispondente
  const gR = [a + f * R, f * G, f * B];
  const gG = [f * R, a + f * G, f * B];
  const gB = [f * R, f * G, a + f * B];
  _fxSvgMat.setAttribute("values", [
    tr * gR[0], tr * gR[1], tr * gR[2], 0, 0,
    tg * gG[0], tg * gG[1], tg * gG[2], 0, 0,
    tb * gB[0], tb * gB[1], tb * gB[2], 0, 0,
    0, 0, 0, 1, 0,
  ].join(" "));
  return "url(#hie-fx)";
}

// Pre-processa un'icona applicando grayscale + tint su canvas offscreen.
// Restituisce un canvas (cached) o l'immagine originale se nessun filtro.
const _fxCache = new WeakMap();
function processedIcon(img, obj) {
  const gs = !!obj.grayscale;
  const tint = obj.color_filter && (obj.color_filter[0] !== 255 || obj.color_filter[1] !== 255 || obj.color_filter[2] !== 255);
  if (!gs && !tint) return img;

  let perImg = _fxCache.get(img);
  if (!perImg) { perImg = new Map(); _fxCache.set(img, perImg); }
  const key = `${gs}|${obj.grayscale_factor}|${obj.color_filter}`;
  if (perImg.has(key)) return perImg.get(key);

  const c = document.createElement("canvas");
  c.width = img.naturalWidth || img.width;
  c.height = img.naturalHeight || img.height;
  const cx = c.getContext("2d");
  cx.imageSmoothingEnabled = true; cx.imageSmoothingQuality = "high";
  cx.filter = _fxFilterUrl(obj.grayscale_factor, gs, tint ? obj.color_filter : null);
  cx.drawImage(img, 0, 0);
  cx.filter = "none";
  perImg.set(key, c);
  return c;
}

// Disegna un triangolo di texture con mapping affine (clip + transform relativo).
function _texTriangle(ctx, img, s0, s1, s2, d0, d1, d2) {
  const [sx0, sy0] = s0, [sx1, sy1] = s1, [sx2, sy2] = s2;
  const [dx0, dy0] = d0, [dx1, dy1] = d1, [dx2, dy2] = d2;
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(dx0, dy0); ctx.lineTo(dx1, dy1); ctx.lineTo(dx2, dy2); ctx.closePath();
  ctx.clip();
  const denom = sx0 * (sy2 - sy1) - sx1 * sy2 + sx2 * sy1 + (sx1 - sx2) * sy0;
  if (denom !== 0) {
    const m11 = -(sy0 * (dx2 - dx1) - sy1 * dx2 + sy2 * dx1 + (sy1 - sy2) * dx0) / denom;
    const m12 = (sy1 * dy2 + sy0 * (dy1 - dy2) - sy2 * dy1 + (sy2 - sy1) * dy0) / denom;
    const m21 = (sx0 * (dx2 - dx1) - sx1 * dx2 + sx2 * dx1 + (sx1 - sx2) * dx0) / denom;
    const m22 = -(sx1 * dy2 + sx0 * (dy1 - dy2) - sx2 * dy1 + (sx2 - sx1) * dy0) / denom;
    const dx = (sx0 * (sy2 * dx1 - sy1 * dx2) + sy0 * (sx1 * dx2 - sx2 * dx1) + (sx2 * sy1 - sx1 * sy2) * dx0) / denom;
    const dy = (sx0 * (sy2 * dy1 - sy1 * dy2) + sy0 * (sx1 * dy2 - sx2 * dy1) + (sx2 * sy1 - sx1 * sy2) * dy0) / denom;
    ctx.transform(m11, m12, m21, m22, dx, dy);
    ctx.drawImage(img, 0, 0);
  }
  ctx.restore();
}

// Mappa l'immagine sul quadrilatero schermo P=[NW,NE,SE,SW] (due triangoli).
function drawImageQuad(ctx, img, P) {
  const W = img.naturalWidth || img.width;
  const H = img.naturalHeight || img.height;
  _texTriangle(ctx, img, [0, 0], [W, 0], [W, H], P[0], P[1], P[2]);
  _texTriangle(ctx, img, [0, 0], [W, H], [0, H], P[0], P[2], P[3]);
}

function drawObject(ctx, sm, obj, img) {
  const drawable = processedIcon(img, obj);

  // Caso warp: mappa l'icona sul quadrilatero deformato (corners+flip+rotazione),
  // identico al poligono usato dalla hit-detection -> visual e hitbox coerenti.
  if (hasWarp(obj)) {
    const g = objCenterAndSize(obj);
    const quadBg = warpPoly(obj, g.cx, g.cy); // [NW,NE,SE,SW] in bg-space
    const P = quadBg.map(p => sm.bgToScreen(p[0], p[1]));
    ctx.save();
    if (obj.alpha < 255) ctx.globalAlpha = obj.alpha / 255;
    drawImageQuad(ctx, drawable, P);
    ctx.restore();
    return;
  }

  const g = objCenterAndSize(obj);
  const [sx, sy] = sm.bgToScreen(g.cx, g.cy);
  const scale = obj.scale || 1.0;
  const iconW = Math.max(1, g.w * sm.bgDisplayScale * scale);
  const iconH = Math.max(1, g.h * sm.bgDisplayScale * scale);

  ctx.save();
  ctx.translate(sx, sy);
  // Pygame ruota CCW per angolo positivo; canvas (y-down) -> usa -angle
  if (obj.rotation) ctx.rotate(-obj.rotation * Math.PI / 180);
  if (obj.flip_x || obj.flip_y) ctx.scale(obj.flip_x ? -1 : 1, obj.flip_y ? -1 : 1);
  if (obj.alpha < 255) ctx.globalAlpha = obj.alpha / 255;
  ctx.drawImage(drawable, -iconW / 2, -iconH / 2, iconW, iconH);
  ctx.restore();
}

// ──────────────────────────────────────────────────────────────────────────
// Asset loader
// ──────────────────────────────────────────────────────────────────────────
function loadImage(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => { console.warn("Asset mancante:", src); resolve(null); };
    img.src = src;
  });
}

// ──────────────────────────────────────────────────────────────────────────
// Effetti ambientali — replica di engine/effect_renderer.py
// Posizionati in bg-space: sx,sy = bgToScreen(fx.x,fx.y), sr = radius*bgScale.
// ──────────────────────────────────────────────────────────────────────────
function drawGlint(ctx, sx, sy, sr, color, intensity, tAccum, phase, pulseMin) {
  const t = tAccum + phase;
  const pulse = pulseMin + ((Math.sin(2 * Math.PI * t) + 1) * 0.5) * (1 - pulseMin);
  const eff = intensity * pulse;
  if (eff <= 0 || sr <= 0) return;
  const [r, g, b] = color;
  const a = Math.min(1, eff);
  ctx.save();
  ctx.globalCompositeOperation = "lighter"; // blending additivo (BLEND_RGB_ADD)
  const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, sr);
  // Approssima il falloff (1-ratio)^2.4 dell'engine con piu' stop.
  grad.addColorStop(0.0, `rgba(${r},${g},${b},${a})`);
  grad.addColorStop(0.15, `rgba(${r},${g},${b},${a * 0.6})`);
  grad.addColorStop(0.4, `rgba(${r},${g},${b},${a * 0.22})`);
  grad.addColorStop(0.7, `rgba(${r},${g},${b},${a * 0.05})`);
  grad.addColorStop(1.0, `rgba(${r},${g},${b},0)`);
  ctx.fillStyle = grad;
  ctx.beginPath(); ctx.arc(sx, sy, sr, 0, Math.PI * 2); ctx.fill();
  if (eff > 0.3) {
    const cv = Math.min(255, Math.round(230 * eff * 0.9));
    ctx.fillStyle = `rgb(${cv},${cv},${cv})`;
    ctx.beginPath(); ctx.arc(sx, sy, Math.max(1, sr / 8), 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

function drawSmoke(ctx, sx, sy, sr, color, intensity, tAccum, phase, pulseMin) {
  const t = tAccum + phase;
  const [rc, gc, bc] = color;
  const numPuffs = 12;
  ctx.save();
  for (let i = 0; i < numPuffs; i++) {
    const seed = i * 2.618;
    const vSpeed = 0.7 + 0.3 * Math.sin(seed * 0.5);
    const pT = (((t * vSpeed + i / numPuffs) % 1) + 1) % 1;
    const sway = Math.sin(pT * 4.5 + seed) * 0.7 + Math.cos(pT * 8.5 + seed * 1.5) * 0.3;
    const driftX = sway * (sr * 0.8 * (1.1 + pT * 1.5));
    const driftY = -pT * sr * 9.0;
    const puffR = sr * (0.55 + pT * 0.7) * pulseMin;
    const alphaBase = 180 * intensity * Math.max(0, Math.pow(1 - pT, 1.6));
    if (alphaBase <= 1) continue;
    const numBlobs = 5;
    for (let bb = 0; bb < numBlobs; bb++) {
      const bAng = bb * (Math.PI * 2 / numBlobs) + pT * 0.4;
      const bDist = puffR * 0.2 * (0.7 + 0.3 * Math.sin(seed + bb));
      const bx = sx + driftX + Math.cos(bAng) * bDist;
      const by = sy + driftY + Math.sin(bAng) * bDist;
      for (let layer = 0; layer < 3; layer++) {
        const lRatio = (3 - layer) / 3;
        const subR = puffR * (0.6 + 0.12 * bb) * lRatio;
        const subA = (alphaBase * (0.1 + 0.07 * layer)) / 255;
        if (subR > 0 && subA > 0) {
          ctx.fillStyle = `rgba(${rc},${gc},${bc},${subA})`;
          ctx.beginPath(); ctx.arc(bx, by, subR, 0, Math.PI * 2); ctx.fill();
        }
      }
    }
  }
  ctx.restore();
}

function drawFlies(ctx, sx, sy, sr, color, intensity, tAccum, tGlobal, pulseMin) {
  const numFlies = Math.floor(intensity * 40);
  if (numFlies < 1) return;
  const baseSz = Math.max(1, Math.round(pulseMin * 3.0));
  const [r, g, b] = color;
  ctx.save();
  ctx.fillStyle = `rgb(${r},${g},${b})`;
  for (let i = 0; i < numFlies; i++) {
    const phi = i * 1.234;
    const posX = sx + Math.cos(tAccum * (1 + Math.sin(phi * 0.5)) + phi) * sr * (0.4 + 0.4 * Math.sin(tAccum * 0.8 + phi)) + Math.sin(tGlobal * 12 + phi) * (sr * 0.1);
    const posY = sy + Math.sin(tAccum * (0.8 + Math.cos(phi * 0.3)) + phi * 1.1) * sr * (0.4 + 0.4 * Math.cos(tAccum * 0.7 + phi * 1.2)) + Math.cos(tGlobal * 14 + phi * 1.5) * (sr * 0.1);
    const sz = Math.round((i % 4 !== 0) ? baseSz : baseSz * 0.8);
    if (sz <= 1) ctx.fillRect(Math.round(posX), Math.round(posY), 1, 1);
    else ctx.fillRect(Math.round(posX - sz / 2), Math.round(posY - sz / 2), sz, sz);
  }
  ctx.restore();
}

// ──────────────────────────────────────────────────────────────────────────
// AudioEngine — SFX e musica via HTMLAudioElement (nessun fetch).
// Scelta deliberata: cosi' funziona anche aprendo index.html da file://
// (il protocollo file:// blocca fetch/XHR per policy CORS dei browser).
// ──────────────────────────────────────────────────────────────────────────
class AudioEngine {
  constructor(manifest) {
    this.base = manifest._base || "./";
    this.sfxMap = manifest.sfx || {};
    this.musicVol = 0.6;
    this.sfxVol = 0.8;
    this.muted = false;
    this.unlocked = false;

    this.sfxEls = {};         // key -> HTMLAudioElement (template precaricato)
    this.musicEl = null;      // HTMLAudioElement attivo
    this.pendingMusic = null; // src da avviare dopo l'unlock
  }

  // Va chiamato dal primo gesto utente (autoplay policy dei browser).
  unlock() {
    if (this.unlocked) return;
    this.unlocked = true;
    this._preloadSfx();
    if (this.pendingMusic) { this.playMusic(this.pendingMusic, true); this.pendingMusic = null; }
  }

  _preloadSfx() {
    for (const [key, path] of Object.entries(this.sfxMap)) {
      const el = new Audio(this.base + path);
      el.preload = "auto";
      this.sfxEls[key] = el;
    }
  }

  sfx(key) {
    if (this.muted) return;
    const tmpl = this.sfxEls[key];
    if (!tmpl) return;
    // Clona per consentire riproduzioni sovrapposte (es. find rapidi).
    const node = tmpl.cloneNode();
    node.volume = this.sfxVol;
    node.play().catch(() => {});
  }

  // path: web path relativo, oppure null per fermare la musica.
  playMusic(path, immediate = false) {
    if (!this.unlocked) { this.pendingMusic = path; return; }
    if (!path) return this.stopMusic();
    const fullSrc = this.base + path;
    if (this.musicEl && this.musicEl._src === fullSrc) return; // gia' in riproduzione
    this.stopMusic();
    const el = new Audio(fullSrc);
    el._src = fullSrc;
    el.loop = true;
    el.volume = this.muted ? 0 : this.musicVol;
    el.play().catch(() => {});
    this.musicEl = el;
  }

  stopMusic() {
    if (!this.musicEl) return;
    const el = this.musicEl;
    this.musicEl = null;
    // fade-out rapido
    let v = el.volume;
    const t = setInterval(() => {
      v -= 0.1;
      if (v <= 0) { clearInterval(t); el.pause(); el.src = ""; }
      else el.volume = v;
    }, 40);
  }

  setMuted(m) {
    this.muted = m;
    if (this.musicEl) this.musicEl.volume = m ? 0 : this.musicVol;
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Game — state machine: LEVEL_SELECT -> SCENE -> RESULTS
// ──────────────────────────────────────────────────────────────────────────
// RULES_DEFAULTS = fallback delle costanti condivise con l'engine. A runtime
// vengono SOVRASCRITTE da manifest.rules (fonte unica = engine, vedi
// editor/web_rules.py e WEB_EXPORT_SYNC.md). I default qui sotto devono restare
// allineati all'engine: il test tests/test_web_sync.py lo verifica.
const RULES_DEFAULTS = {
  points_per_object: 100,
  bonus_time_max: 500,
  miss_time_penalty: 5,
  miss_point_penalty: 25,
  star_multiplier: { 1: 1, 2: 1, 3: 2 },
  bonus_ratio_3star: 0.66,
  hint_free: 2,
  hint_cooldown: 20,
  hint_penalties: [50, 75, 100],
  hint_max_uses: 3,
  ref_w: 1280,
  ref_h: 720,
};

const HINT_GLOW_MS = 3000;           // durata glow hint manuale (solo estetica)
const HINT_AUTO_DEFAULT_DELAY = 30;  // delay auto-glow se non specificato
const FADE_MS = 380;                 // transizione fade-from-black tra stati

// HUD nomi oggetti — palette pastello (replica engine/hud_manager.py)
const HUD_NAME_COLORS = ["#9ee6a0", "#ffd479", "#8fe3e8", "#ff9e8a", "#d99ae0", "#9ae0d0"];
const HUD_MAX_VISIBLE = 7;

// ──────────────────────────────────────────────────────────────────────────
// Stringhe UI integrate (chrome) nelle 5 lingue supportate.
// Hanno priorita' dopo le stringhe del gioco: garantiscono UI tradotta sempre.
// ──────────────────────────────────────────────────────────────────────────
const UI_STRINGS = {
  it: { start_prompt: "Clicca per iniziare", menu_select_scene: "Seleziona una scena", menu_objects: "oggetti",
    hud_paused: "Pausa", btn_resume: "Riprendi", btn_restart: "Ricomincia", btn_quit_to_main: "Menu", btn_close: "CHIUDI",
    settings_title: "Impostazioni", label_music_volume: "Volume Musica", label_sfx_volume: "Volume Effetti", label_language: "Lingua",
    btn_back: "Indietro", mission_complete: "Livello Completato!", mission_failed: "Tempo Scaduto",
    total_score: "Punteggio", time_elapsed: "Tempo", objects_found: "Oggetti", perfect_score: "Perfetto! Tutti trovati",
    btn_continue: "Continua", btn_next: "Avanti", btn_retry: "Riprova", locked: "Bloccato", best: "Record" },
  en: { start_prompt: "Click to start", menu_select_scene: "Select a scene", menu_objects: "objects",
    hud_paused: "Paused", btn_resume: "Resume", btn_restart: "Restart", btn_quit_to_main: "Menu", btn_close: "CLOSE",
    settings_title: "Settings", label_music_volume: "Music Volume", label_sfx_volume: "SFX Volume", label_language: "Language",
    btn_back: "Back", mission_complete: "Level Complete!", mission_failed: "Time's Up",
    total_score: "Score", time_elapsed: "Time", objects_found: "Objects", perfect_score: "Perfect! All found",
    btn_continue: "Continue", btn_next: "Next", btn_retry: "Retry", locked: "Locked", best: "Best" },
  de: { start_prompt: "Zum Starten klicken", menu_select_scene: "Szene wählen", menu_objects: "Objekte",
    hud_paused: "Pause", btn_resume: "Fortsetzen", btn_restart: "Neustart", btn_quit_to_main: "Menü", btn_close: "SCHLIESSEN",
    settings_title: "Einstellungen", label_music_volume: "Musik", label_sfx_volume: "Effekte", label_language: "Sprache",
    btn_back: "Zurück", mission_complete: "Level geschafft!", mission_failed: "Zeit abgelaufen",
    total_score: "Punkte", time_elapsed: "Zeit", objects_found: "Objekte", perfect_score: "Perfekt! Alle gefunden",
    btn_continue: "Weiter", btn_next: "Weiter", btn_retry: "Erneut", locked: "Gesperrt", best: "Rekord" },
  es: { start_prompt: "Haz clic para empezar", menu_select_scene: "Selecciona una escena", menu_objects: "objetos",
    hud_paused: "Pausa", btn_resume: "Reanudar", btn_restart: "Reiniciar", btn_quit_to_main: "Menú", btn_close: "CERRAR",
    settings_title: "Ajustes", label_music_volume: "Música", label_sfx_volume: "Efectos", label_language: "Idioma",
    btn_back: "Atrás", mission_complete: "¡Nivel completado!", mission_failed: "Tiempo agotado",
    total_score: "Puntuación", time_elapsed: "Tiempo", objects_found: "Objetos", perfect_score: "¡Perfecto! Todo encontrado",
    btn_continue: "Continuar", btn_next: "Siguiente", btn_retry: "Reintentar", locked: "Bloqueado", best: "Récord" },
  fr: { start_prompt: "Cliquez pour commencer", menu_select_scene: "Choisissez une scène", menu_objects: "objets",
    hud_paused: "Pause", btn_resume: "Reprendre", btn_restart: "Recommencer", btn_quit_to_main: "Menu", btn_close: "FERMER",
    settings_title: "Réglages", label_music_volume: "Musique", label_sfx_volume: "Effets", label_language: "Langue",
    btn_back: "Retour", mission_complete: "Niveau terminé !", mission_failed: "Temps écoulé",
    total_score: "Score", time_elapsed: "Temps", objects_found: "Objets", perfect_score: "Parfait ! Tout trouvé",
    btn_continue: "Continuer", btn_next: "Suivant", btn_retry: "Réessayer", locked: "Verrouillé", best: "Record" },
};

// ──────────────────────────────────────────────────────────────────────────
// Theme — legge i colori dal manifest.theme (engine/assets/themes/*) con
// fallback sensati, e li espone come stringhe CSS rgba.
// ──────────────────────────────────────────────────────────────────────────
class Theme {
  constructor(manifest) {
    this.c = (manifest.theme && manifest.theme.colors) || {};
    this.fx = (manifest.theme && manifest.theme.effects) || {};
    this.id = (manifest.theme && manifest.theme.id) || "default";
  }
  _rgba(arr, fb) {
    const v = arr || fb;
    if (!v) return "rgba(128,128,128,1)";
    const a = v.length > 3 ? v[3] / 255 : 1;
    return `rgba(${v[0]},${v[1]},${v[2]},${a})`;
  }
  // opaco (ignora alpha del tema) — utile per accenti/testi
  _rgb(arr, fb) { const v = arr || fb; return v ? `rgb(${v[0]},${v[1]},${v[2]})` : "rgb(128,128,128)"; }
  accent() { return this._rgb(this.c.btn_glow_color || this.c.slider_fill || this.c.scene_border_hover, [120, 160, 240]); }
  accent2() { return this._rgb(this.c.btn_border_hover || this.c.scene_border_hover, [255, 200, 80]); }
  text() { return this._rgb(this.c.text_normal, [235, 238, 245]); }
  textDim() { return this._rgb(this.c.text_locked, [120, 130, 150]); }
  lock() { return this._rgb(this.c.lock_text, [255, 90, 90]); }
  sliderFill() { return this._rgb(this.c.slider_fill, [90, 150, 235]); }
  sliderBg() { return this._rgb(this.c.slider_bg, [30, 33, 40]); }
  cardBorder() { return this._rgb(this.c.scene_border_normal, [80, 100, 150]); }
  cardBorderHover() { return this._rgb(this.c.scene_border_hover, [120, 160, 240]); }
  // gradiente di sfondo derivato dall'overlay del tema
  bgTop() { const v = this.c.background_overlay || [12, 16, 28]; return `rgb(${Math.min(255, v[0] + 6)},${Math.min(255, v[1] + 8)},${Math.min(255, v[2] + 14)})`; }
  bgBottom() { const v = this.c.background_overlay || [12, 16, 28]; return `rgb(${Math.max(0, v[0])},${Math.max(0, v[1])},${Math.max(0, v[2])})`; }
}

// ──────────────────────────────────────────────────────────────────────────
// Save — persistenza progressi in localStorage (per gioco).
// Replica engine/save_manager.py: scores/stars/unlocked_scenes/unlocked_levels.
// ──────────────────────────────────────────────────────────────────────────
const Save = {
  _key(gameId) { return "hie_save_" + gameId; },
  load(gameId) {
    try {
      const raw = localStorage.getItem(this._key(gameId));
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return { scores: {}, stars: {}, unlocked_scenes: {}, unlocked_levels: [] };
  },
  save(gameId, data) {
    try { localStorage.setItem(this._key(gameId), JSON.stringify(data)); } catch (e) {}
  },
  isLevelUnlocked(data, manifest, levelId) {
    const idx = manifest.levels.findIndex(l => l.id === levelId);
    return idx === 0 || data.unlocked_levels.includes(levelId);
  },
  isSceneUnlocked(data, manifest, levelId, sceneIdx) {
    if (!this.isLevelUnlocked(data, manifest, levelId)) return false;
    return sceneIdx <= (data.unlocked_scenes[levelId] || 0);
  },
  getStars(data, levelId, sceneId) { return (data.stars[levelId] && data.stars[levelId][sceneId]) || 0; },
  getScore(data, levelId, sceneId) { return (data.scores[levelId] && data.scores[levelId][sceneId]) || 0; },
  // Registra il risultato tenendo il migliore e sblocca scena/livello successivi.
  record(gameId, manifest, levelId, sceneIdx, sceneId, score, stars) {
    const data = this.load(gameId);
    data.scores[levelId] = data.scores[levelId] || {};
    data.stars[levelId] = data.stars[levelId] || {};
    if (score > (data.scores[levelId][sceneId] || 0)) data.scores[levelId][sceneId] = score;
    if (stars > (data.stars[levelId][sceneId] || 0)) data.stars[levelId][sceneId] = stars;
    const lvl = manifest.levels.find(l => l.id === levelId);
    const nScenes = lvl ? lvl.scenes.length : 0;
    const cur = data.unlocked_scenes[levelId] || 0;
    if (sceneIdx + 1 < nScenes) {
      data.unlocked_scenes[levelId] = Math.max(cur, sceneIdx + 1);
    } else {
      // ultima scena del livello -> sblocca il livello successivo
      const li = manifest.levels.findIndex(l => l.id === levelId);
      const next = manifest.levels[li + 1];
      if (next && !data.unlocked_levels.includes(next.id)) data.unlocked_levels.push(next.id);
    }
    this.save(gameId, data);
    return data;
  },
};

class Game {
  constructor(manifest, canvas) {
    this.manifest = manifest;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.sm = new ScalingManager();
    this.audio = new AudioEngine(manifest);
    this.theme = new Theme(manifest);
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
      this.score = Math.max(0, this.score - this.R.miss_point_penalty);
      this.timeLeft = Math.max(0, this.timeLeft - this.R.miss_time_penalty);
      this.feedback = { x: sx, y: sy, t: performance.now(), ok: false };
      this._spawnPopup(sx, sy, "-" + this.R.miss_point_penalty, "#ff6b6b");
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
    const bonus = allFound ? Math.round(ratio * this.R.bonus_time_max) : 0;
    let stars = 1;
    if (allFound && bonus / this.R.bonus_time_max >= this.R.bonus_ratio_3star) stars = 3;
    else if (allFound) stars = 2;
    const finalScore = Math.round((this.score + bonus) * (this.R.star_multiplier[stars] || 1));
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
    this.state = "SCENE";
    const success = !!(result && result.success);
    const addedScore = (result && result.score) || 0;
    if (addedScore > 0) this.score += addedScore;
    if (obj) {
      obj.found = true;            // consumato comunque (replica engine)
      this.lastFindAt = performance.now();
      this.feedback = { x: this.canvas.clientWidth / 2, y: this.canvas.clientHeight / 2, t: performance.now(), ok: success };
    }
    this.audio.sfx(success ? "complete" : "found");
    this.audio.playMusic(this.sceneDef.music);
    this._mgLastTs = 0;
    if (this.goals.every(o => o.found)) this._completeScene();
    else this.invalidate();
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

  // ── Render-on-demand ─────────────────────────────────────────────────────
  _frame() {
    this._renderScheduled = false;
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

const MINIGAME_CLASSES = { tetran: TetranGame, arcade_eleven: ArcadeEleven, asteroids: AsteroidsGame };

// ──────────────────────────────────────────────────────────────────────────
// Bootstrap
// ──────────────────────────────────────────────────────────────────────────
async function main() {
  const base = "./";
  // Preferisci il manifest incorporato (manifest.js -> window.__MANIFEST__):
  // funziona da file:// senza fetch. Fallback a fetch per setup http custom.
  let manifest = window.__MANIFEST__;
  if (!manifest) {
    manifest = await fetch(base + "manifest.json").then(r => r.json());
  }
  manifest._base = base;
  const canvas = document.getElementById("game");
  const game = new Game(manifest, canvas);
  window.__game = game;
  game.invalidate();
  // Nasconde il loading screen iniziale una volta pronta la prima schermata.
  requestAnimationFrame(() => game._hideLoader());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
