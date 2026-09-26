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

// Registry dei minigiochi: ogni file minigames/*.js si auto-registra qui.
window.MINIGAME_CLASSES = window.MINIGAME_CLASSES || {};

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
// Tuning: identical values in engine/effect_renderer.py.
const FX = {
  GLINT_HALO_ALPHA: 0.92, GLINT_HALO_FALLOFF: 2.4, GLINT_WHITE_CORE: 0.55, GLINT_CORE_SIZE: 10.0,
  GLINT_SPARKLE_FROM: 0.55, GLINT_SPARKLE_LEN: 1.15, GLINT_SPARKLE_SPIN: 0.08,
  GLINT_SPARKLE_MAX: 80, GLINT_SPARKLE_FULL_RADIUS: 90, GLINT_MIN_RADIUS: 6,
  SMOKE_PUFFS: 16, SMOKE_RISE: 5.0, SMOKE_WIND: 1.8, SMOKE_SWAY: 0.55, SMOKE_FADE_IN: 0.2,
  SMOKE_SCATTER: 0.9, SMOKE_FADE_OUT: 1.4, SMOKE_ALPHA: 1.25, SMOKE_GROW_FROM: 0.7,
  SMOKE_GROW_TO: 2.4, SMOKE_SIZE_BASE: 0.6, SMOKE_SIZE_GAIN: 0.8, SMOKE_SPRITE: 64,
  SMOKE_SPRITE_FALLOFF: 1.6, SMOKE_LIT_CORE: 0.3, SMOKE_LIT_SIZE: 3.0,
  FLIES_PER_INTENSITY: 40, FLIES_SPEED: 6.0, FLIES_BUZZ_HZ: 9.0, FLIES_BUZZ_AMP: 0.025,
  FLIES_BASE_SIZE: 4.2, FLIES_WING_ALPHA: 90,
};

function fxHash01(n) { const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); }
function fxSmooth(e0, e1, x) {
  if (e1 === e0) return x >= e1 ? 1 : 0;
  const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
}
function glintBrightness(tAccum, phase, pulseMin) {
  const floor = Math.max(0, Math.min(1, pulseMin));
  const raw = 0.5 - 0.5 * Math.cos(2 * Math.PI * (tAccum + phase));
  return floor + (1 - floor) * fxSmooth(0, 1, raw);
}

// Radial gradient sampling the same profile as effect_renderer._radial_sprite:
// alpha = peak * exp(-k d^2) * (1 - d), colour whitened towards the centre.
function fxRadialGradient(ctx, x, y, r, color, peak, falloff, whiteCore, coreSize) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  const [r0, g0, b0] = color;
  const STOPS = 14;
  for (let k = 0; k <= STOPS; k++) {
    const d = k / STOPS;
    const a = peak * Math.exp(-falloff * d * d) * (1 - d);
    const w = whiteCore * Math.exp(-coreSize * d * d);
    const cr = Math.round(r0 + (255 - r0) * w), cg = Math.round(g0 + (255 - g0) * w),
      cb = Math.round(b0 + (255 - b0) * w);
    g.addColorStop(d, `rgba(${cr},${cg},${cb},${a.toFixed(4)})`);
  }
  return g;
}

// A glow that breathes: soft halo, warm-white heart, a star at the crest.
function drawGlint(ctx, sx, sy, sr, color, intensity, tAccum, phase, pulseMin) {
  const b = glintBrightness(tAccum, phase, pulseMin);
  const level = Math.max(0, Math.min(1, intensity * b));
  if (level <= 0.01 || sr <= 0) return;
  const r = Math.max(FX.GLINT_MIN_RADIUS, Math.round(sr));
  ctx.save();
  ctx.globalAlpha = level;
  ctx.fillStyle = fxRadialGradient(ctx, sx, sy, r, color, FX.GLINT_HALO_ALPHA,
    FX.GLINT_HALO_FALLOFF, FX.GLINT_WHITE_CORE, FX.GLINT_CORE_SIZE);
  ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fill();
  const spark = fxSmooth(FX.GLINT_SPARKLE_FROM, 1, b) * Math.min(1, intensity)
    * Math.min(1, FX.GLINT_SPARKLE_FULL_RADIUS / r);
  if (spark > 0.02) {
    const len = Math.max(4, Math.min(r * FX.GLINT_SPARKLE_LEN, FX.GLINT_SPARKLE_MAX) * (0.75 + 0.25 * b));
    const tint = color.map(c => Math.min(255, Math.round((c + 510) / 3)));
    const ang = 2 * Math.PI * ((FX.GLINT_SPARKLE_SPIN * (tAccum + phase)) % 0.25);
    ctx.globalAlpha = spark;
    ctx.translate(sx, sy); ctx.rotate(-ang);
    for (let arm = 0; arm < 2; arm++) {
      const grad = arm === 0 ? ctx.createLinearGradient(-len, 0, len, 0)
        : ctx.createLinearGradient(0, -len, 0, len);
      grad.addColorStop(0, `rgba(${tint[0]},${tint[1]},${tint[2]},0)`);
      grad.addColorStop(0.5, `rgba(${tint[0]},${tint[1]},${tint[2]},0.9)`);
      grad.addColorStop(1, `rgba(${tint[0]},${tint[1]},${tint[2]},0)`);
      ctx.fillStyle = grad;
      const w = 2.2;
      if (arm === 0) ctx.fillRect(-len, -w / 2, len * 2, w);
      else ctx.fillRect(-w / 2, -len, w, len * 2);
    }
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.beginPath(); ctx.arc(0, 0, Math.max(1, len / 10), 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

function smokePuff(i, t, sr, size) {
  const seed = fxHash01(i + 1);
  const speed = 0.85 + 0.3 * fxHash01(i + 17);
  const p = (((t * speed + i / FX.SMOKE_PUFFS + seed * 0.05) % 1) + 1) % 1;
  const opacity = fxSmooth(0, FX.SMOKE_FADE_IN, p) * Math.pow(1 - p, FX.SMOKE_FADE_OUT);
  const rise = -p * sr * FX.SMOKE_RISE;
  const wind = FX.SMOKE_WIND * sr * p * p;
  const sway = Math.sin(2 * Math.PI * (p * 1.3 + seed)) * FX.SMOKE_SWAY * sr * (0.3 + p);
  const radius = sr * size * (FX.SMOKE_GROW_FROM + (FX.SMOKE_GROW_TO - FX.SMOKE_GROW_FROM) * p)
    * (0.85 + 0.3 * fxHash01(i + 31));
  const scatter = (fxHash01(i + 53) - 0.5) * FX.SMOKE_SCATTER * sr * (0.4 + p);
  return [wind + sway + scatter, rise, radius, opacity];
}

const _smokeSprites = {};
function smokeSprite(color) {
  const key = color.join(",");
  if (_smokeSprites[key]) return _smokeSprites[key];
  const d = FX.SMOKE_SPRITE, c = document.createElement("canvas");
  c.width = c.height = d;
  const cx = c.getContext("2d");
  cx.fillStyle = fxRadialGradient(cx, d / 2, d / 2, d / 2, color, 1, FX.SMOKE_SPRITE_FALLOFF,
    FX.SMOKE_LIT_CORE, FX.SMOKE_LIT_SIZE);
  cx.fillRect(0, 0, d, d);
  _smokeSprites[key] = c;
  return c;
}

// Soft puffs that appear, rise, drift with the wind, swell and fade.
function drawSmoke(ctx, sx, sy, sr, color, intensity, tAccum, phase, pulseMin) {
  if (sr <= 0 || intensity <= 0) return;
  const sprite = smokeSprite(color);
  const size = Math.max(0.25, FX.SMOKE_SIZE_BASE + FX.SMOKE_SIZE_GAIN * (pulseMin || 0));
  const peak = FX.SMOKE_ALPHA * Math.min(2, intensity);
  const t = tAccum + (phase || 0);
  const age = i => (((t * (0.85 + 0.3 * fxHash01(i + 17)) + i / FX.SMOKE_PUFFS) % 1) + 1) % 1;
  const order = [...Array(FX.SMOKE_PUFFS).keys()].sort((a, b) => age(b) - age(a));
  ctx.save();
  for (const i of order) {
    const [dx, dy, pr, op] = smokePuff(i, t, sr, size);
    const a = Math.min(1, peak * op);
    if (a * 255 <= 2 || pr < 1) continue;
    ctx.globalAlpha = a;
    ctx.drawImage(sprite, sx + dx - pr, sy + dy - pr, pr * 2, pr * 2);
  }
  ctx.restore();
}

function flyPosition(i, tAccum, tGlobal, sx, sy, sr) {
  const h = [];
  for (let k = 0; k < 8; k++) h.push(fxHash01(i * 7 + k));
  const t = tAccum * FX.FLIES_SPEED;
  const fx1 = 0.6 + 0.8 * h[0], fx2 = 1.3 + 1.2 * h[1], fy1 = 0.5 + 0.9 * h[2], fy2 = 1.1 + 1.3 * h[3];
  let x = sr * (0.55 * Math.sin(t * fx1 + 6.283 * h[4]) + 0.3 * Math.sin(t * fx2 + 6.283 * h[5]));
  let y = sr * 0.6 * (0.55 * Math.cos(t * fy1 + 6.283 * h[6]) + 0.3 * Math.sin(t * fy2 + 6.283 * h[7]));
  const buzz = FX.FLIES_BUZZ_AMP * sr;
  x += buzz * Math.sin(2 * Math.PI * FX.FLIES_BUZZ_HZ * tGlobal + 11 * h[0]);
  y += buzz * Math.cos(2 * Math.PI * FX.FLIES_BUZZ_HZ * 1.13 * tGlobal + 7 * h[1]);
  return [sx + x, sy + y, 0.6 + 0.4 * h[5]];
}

// A swarm: small dark bodies with two flickering wings, nearer flies bigger.
function drawFlies(ctx, sx, sy, sr, color, intensity, tAccum, tGlobal, pulseMin) {
  const count = Math.round(Math.max(0, intensity) * FX.FLIES_PER_INTENSITY);
  if (count < 1 || sr <= 0) return;
  const [r, g, b] = color;
  const scale = Math.max(0.8, Math.min(2, sr / 120)) * Math.max(0.3, pulseMin == null ? 1 : pulseMin);
  const wing = `rgba(${Math.min(255, r + 150)},${Math.min(255, g + 150)},${Math.min(255, b + 160)},${FX.FLIES_WING_ALPHA / 255})`;
  ctx.save();
  for (let i = 0; i < count; i++) {
    const [x, y, depth] = flyPosition(i, tAccum, tGlobal, sx, sy, sr);
    const len = Math.max(1.5, FX.FLIES_BASE_SIZE * scale * depth);
    if (len < 2.2) { ctx.fillStyle = `rgb(${r},${g},${b})`; ctx.fillRect(Math.floor(x), Math.floor(y), 1, 1); continue; }
    const w = Math.round(len), h = Math.max(1, Math.round(len * 0.6));
    const beat = Math.floor(tGlobal * 40 + i * 3) % 2;
    const wh = Math.max(1, h - beat);
    ctx.fillStyle = wing;
    ctx.beginPath(); ctx.ellipse(x, y - h + beat, (w + 2) / 2, (wh + 1) / 2, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.beginPath(); ctx.ellipse(x, y, w / 2, h / 2, 0, 0, Math.PI * 2); ctx.fill();
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
  miss_penalty_curve: [25, 50, 100, 150, 300, 500],
  miss_combo_window: 1.5,
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

