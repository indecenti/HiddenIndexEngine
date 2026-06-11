/*
 * skins/base.js — Skin dei menu web (overlay DOM/CSS).
 *
 * Il MENU CORE (game.js) gestisce stato, save/lock, i18n, audio e il rendering
 * di SCENA/minigiochi (canvas, parita' 1:1 con pygame). I MENU sono delegati a
 * uno SKIN pluggabile selezionato da manifest.ui_theme. Lo skin costruisce DOM
 * per le schermate START / LEVEL_SELECT / SETTINGS sopra il canvas; le altre
 * (RESULTS/PAUSE) ricadono sul rendering canvas del core.
 *
 * MenuSkinWeb e' la direzione "Clean" (default) ed e' anche il fallback.
 * horror.js / kids.js estendono questa classe e cambiano solo look & feel.
 * Nessuna emoji: le icone sono SVG inline.
 */

window.MENU_SKINS = window.MENU_SKINS || {};

var _SVG_STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.7 5.9 6.4.6-4.8 4.3 1.4 6.3L12 16.9 6.3 19.6l1.4-6.3L2.9 9l6.4-.6z"/></svg>';
var _SVG_LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm3 8H9V7a3 3 0 016 0z"/></svg>';
var _SVG_GEAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.14 12.94a7.49 7.49 0 000-1.88l2.03-1.58a.5.5 0 00.12-.64l-1.92-3.32a.5.5 0 00-.6-.22l-2.39.96a7.3 7.3 0 00-1.62-.94l-.36-2.54a.5.5 0 00-.5-.42h-3.84a.5.5 0 00-.5.42l-.36 2.54c-.59.24-1.13.56-1.62.94l-2.39-.96a.5.5 0 00-.6.22L2.71 8.84a.5.5 0 00.12.64l2.03 1.58a7.49 7.49 0 000 1.88l-2.03 1.58a.5.5 0 00-.12.64l1.92 3.32a.5.5 0 00.6.22l2.39-.96c.49.38 1.03.7 1.62.94l.36 2.54a.5.5 0 00.5.42h3.84a.5.5 0 00.5-.42l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96a.5.5 0 00.6-.22l1.92-3.32a.5.5 0 00-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1112 8.5a3.5 3.5 0 010 7z"/></svg>';

var _BASE_CSS = "\
#menu-root{position:fixed;inset:0;z-index:5;display:none;overflow-y:auto;overflow-x:hidden;color:var(--text,#eaf0fa);font-family:var(--font-body,system-ui,-apple-system,Segoe UI,sans-serif);-webkit-tap-highlight-color:transparent;animation:menuFade .35s ease}\
@keyframes menuFade{from{opacity:0}to{opacity:1}}\
#menu-root .menu-bg{position:fixed;inset:0;z-index:-1;background:radial-gradient(130% 70% at 50% -12%,rgba(120,160,240,.16),rgba(0,0,0,0) 58%),var(--bg2,#0c111a);background-size:cover;background-position:center}\
#menu-root .menu-title{margin:6px 0;text-align:center;font-family:var(--font-title,Georgia,serif);font-weight:500;letter-spacing:.5px;color:var(--text,#eaf0fa);font-size:34px}\
#menu-root .menu-title.big{font-size:52px}\
#menu-root .gear-btn{position:absolute;top:14px;right:16px;width:42px;height:42px;border-radius:50%;border:1px solid var(--card-border,#33405a);background:rgba(0,0,0,.3);color:var(--accent,#5aa0eb);cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}\
#menu-root .gear-btn svg{width:22px;height:22px;fill:currentColor}\
#menu-root .start-screen{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;cursor:pointer;padding:24px}\
#menu-root .start-prompt{color:var(--accent,#5aa0eb);font-size:20px;animation:promptPulse 1.4s ease-in-out infinite}\
@keyframes promptPulse{0%,100%{opacity:.5}50%{opacity:1}}\
#menu-root .level-select{max-width:1120px;margin:0 auto;padding:26px 22px 64px;position:relative}\
#menu-root .ls-sub{text-align:center;color:var(--accent,#5aa0eb);font-size:14px;margin:2px 0 20px}\
#menu-root .level-group{margin:20px 0}\
#menu-root .level-name{font-family:var(--font-title,Georgia,serif);font-size:20px;color:var(--accent2,#ffd479);margin:0 0 12px;text-align:left}\
#menu-root .scene-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(220px,100%),1fr));gap:18px}\
#menu-root .scene-card{position:relative;aspect-ratio:16/10;border-radius:14px;overflow:hidden;border:2px solid var(--card-border,#33405a);background:var(--bg2,#0c111a);cursor:pointer;padding:0;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}\
#menu-root .scene-card:hover{border-color:var(--card-border-hover,#7cb2f2);transform:translateY(-3px);box-shadow:0 10px 26px rgba(0,0,0,.45)}\
#menu-root .scene-card.locked{cursor:not-allowed}\
#menu-root .scene-thumb{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}\
#menu-root .scene-card.locked .scene-thumb{filter:grayscale(1) brightness(.5)}\
#menu-root .card-veil{position:absolute;inset:0;background:linear-gradient(transparent 52%,rgba(6,10,20,.92))}\
#menu-root .stars{position:absolute;top:8px;right:8px;display:flex;gap:2px}\
#menu-root .star svg{width:16px;height:16px;fill:rgba(255,255,255,.22)}\
#menu-root .star.on svg{fill:#ffce3a}\
#menu-root .card-meta{position:absolute;left:12px;right:12px;bottom:9px;text-align:left}\
#menu-root .scene-name{font-weight:600;font-size:15px;color:#fff}\
#menu-root .scene-count{font-size:12px;color:var(--accent,#5aa0eb)}\
#menu-root .lock-badge{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}\
#menu-root .lock-badge svg{width:36px;height:36px;fill:var(--lock,#ff5a5a)}\
#menu-root .settings-screen{max-width:560px;margin:0 auto;padding:42px 22px;min-height:100%;display:flex;flex-direction:column;gap:18px;justify-content:center}\
#menu-root .set-panel{background:rgba(0,0,0,.25);border:1px solid var(--card-border,#33405a);border-radius:16px;padding:22px;display:flex;flex-direction:column;gap:20px}\
#menu-root .set-row-top{display:flex;justify-content:space-between;font-size:14px;color:var(--text-dim,#9fb3d8);margin-bottom:8px}\
#menu-root .set-range{width:100%;accent-color:var(--slider-fill,#5aa0eb)}\
#menu-root .lang-row{display:flex;flex-direction:column;gap:10px}\
#menu-root .set-label{font-size:14px;color:var(--text-dim,#9fb3d8)}\
#menu-root .lang-btns{display:flex;gap:8px;flex-wrap:wrap}\
#menu-root .lang-btn{padding:9px 15px;border-radius:10px;border:1px solid var(--card-border,#33405a);background:rgba(255,255,255,.06);color:var(--text,#eaf0fa);cursor:pointer;font-weight:600}\
#menu-root .lang-btn.active{background:var(--accent,#5aa0eb);color:#0c0c0c;border-color:#fff}\
#menu-root .back-btn{align-self:center;padding:12px 30px;border-radius:12px;border:none;background:var(--accent,#5aa0eb);color:#0c0c0c;font-weight:700;cursor:pointer;font-size:16px}\
#menu-root .results-screen,#menu-root .pause-screen{min-height:100%;display:flex;align-items:center;justify-content:center;padding:24px}\
#menu-root .results-panel,#menu-root .pause-panel{background:var(--bg2,#0c111a);border:2px solid var(--accent,#5aa0eb);border-radius:18px;padding:28px 26px;max-width:440px;width:100%;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.5);animation:panelPop .35s cubic-bezier(.2,.9,.3,1.3)}\
@keyframes panelPop{from{opacity:0;transform:translateY(20px) scale(.96)}to{opacity:1;transform:none}}\
#menu-root .results-title{font-family:var(--font-title,Georgia,serif);font-size:28px;margin:0 0 12px}\
#menu-root .results-title.win{color:#46d27e}#menu-root .results-title.lose{color:#e0563f}\
#menu-root .res-stars{display:flex;justify-content:center;gap:14px;margin:4px 0 16px}\
#menu-root .res-stars .star svg{width:46px;height:46px;fill:rgba(255,255,255,.14)}\
#menu-root .res-stars .star.on svg{fill:#ffce3a;filter:drop-shadow(0 0 6px rgba(255,210,80,.6))}\
#menu-root .res-score-label{color:var(--accent,#5aa0eb);font-size:14px;font-style:italic}\
#menu-root .res-score{font-family:var(--font-title,Georgia,serif);font-size:46px;font-weight:700;margin:2px 0 4px;color:var(--text,#fff)}\
#menu-root .res-perfect{color:#46d27e;font-size:15px;font-style:italic;margin-bottom:6px}\
#menu-root .res-stats{border-top:1px solid rgba(255,255,255,.14);margin-top:12px;padding-top:12px;display:flex;flex-direction:column;gap:8px}\
#menu-root .res-stat{display:flex;justify-content:space-between;font-size:14px}\
#menu-root .res-stat .k{color:var(--text-dim,#9fb3d8)}#menu-root .res-stat .v{color:#fff}\
#menu-root .res-btns{display:flex;gap:12px;margin-top:18px;justify-content:center}\
#menu-root .pause-title{font-family:var(--font-title,Georgia,serif);font-size:30px;margin:0 0 18px;color:var(--text,#fff)}\
#menu-root .pause-btns{display:flex;flex-direction:column;gap:12px;margin-top:6px}\
#menu-root .menu-btn{flex:1;padding:13px 18px;border-radius:12px;border:1px solid var(--card-border,#33405a);background:rgba(255,255,255,.08);color:var(--text,#fff);font-weight:700;cursor:pointer;font-size:15px}\
#menu-root .menu-btn.primary{background:var(--accent,#5aa0eb);color:#0c0c0c;border:none}\
#menu-root .pause-scrim{position:fixed;inset:0;z-index:-1;background:rgba(8,12,22,.85)}\
#menu-root .firefly{position:absolute;width:4px;height:4px;border-radius:50%;background:rgba(190,212,245,.9);box-shadow:0 0 7px 2px rgba(190,212,245,.5);animation:fly 12s ease-in-out infinite}\
@keyframes fly{0%,100%{transform:translate(0,0);opacity:.35}50%{transform:translate(18px,-15px);opacity:1}}\
@media (max-width:520px){#menu-root .level-select{padding:20px 12px 56px}#menu-root .settings-screen{padding:28px 14px}#menu-root .menu-title{font-size:26px}#menu-root .menu-title.big{font-size:38px}#menu-root .results-panel,#menu-root .pause-panel{padding:22px 18px}#menu-root .res-score{font-size:38px}#menu-root .res-stars .star svg{width:38px;height:38px}}\
@media (prefers-reduced-motion:reduce){#menu-root,#menu-root *{animation:none!important}}\
";

(function () {
  if (!document.getElementById("menu-skin-css-base")) {
    var s = document.createElement("style");
    s.id = "menu-skin-css-base";
    s.textContent = _BASE_CSS;
    (document.head || document.documentElement).appendChild(s);
  }
})();

class MenuSkinWeb {
  constructor(game) {
    this.game = game;
    this._root = null;
    this._shownState = null;
    this._shaderBg = null;
    this._ensureRoot();
    this._injectFonts();
  }

  // Inietta le @font-face dei font bundlati del tema (manifest.fonts), una volta.
  _injectFonts() {
    var fonts = (this.game.manifest && this.game.manifest.fonts) || [];
    if (!fonts.length || document.getElementById("menu-fonts")) return;
    var base = this.game.manifest._base || "./";
    var css = fonts.map(function (f) {
      return "@font-face{font-family:'" + f.family + "';src:url('" + base + f.url +
        "') format('truetype');font-display:swap}";
    }).join("");
    var s = document.createElement("style");
    s.id = "menu-fonts"; s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  }

  handles(state) { return MenuSkinWeb.handledStates.indexOf(state) !== -1; }

  _ensureRoot() {
    var r = document.getElementById("menu-root");
    if (!r) { r = document.createElement("div"); r.id = "menu-root"; document.body.appendChild(r); }
    this._root = r;
  }

  show(state) {
    if (this._shownState !== state) { this._build(state); this._shownState = state; }
    this._root.style.display = "block";
    if (this._shaderBg) this._shaderBg.resize();  // ora che l'overlay e' visibile
  }
  hide() { this._destroyShader(); if (this._root) this._root.style.display = "none"; this._shownState = null; }
  refresh() { this._shownState = null; this.game.invalidate(); }

  // Sfondo a shader WebGL OPZIONALE: solo se il tema lo chiede, c'e' WebGL e
  // non e' attiva la reduced-motion. Altrimenti resta lo sfondo CSS (fallback).
  _maybeShader(bg) {
    var b = (this.game.manifest.theme && this.game.manifest.theme.background) || {};
    if (b.mode !== "shader") return;
    if (typeof ShaderBG === "undefined" || !ShaderBG) return;
    try { if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return; } catch (e) {}
    var inst = ShaderBG.create(bg, b.shader || "synthwave");
    if (inst) this._shaderBg = inst;
  }

  _destroyShader() {
    if (this._shaderBg) { try { this._shaderBg.destroy(); } catch (e) {} this._shaderBg = null; }
  }

  el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  _setVars() {
    var t = this.game.theme, m = this.game.manifest, r = this._root;
    var set = function (k, v) { r.style.setProperty(k, v); };
    set("--accent", t.accent()); set("--accent2", t.accent2());
    set("--text", t.text()); set("--text-dim", t.textDim());
    set("--bg2", t.bgBottom()); set("--card-border", t.cardBorder());
    set("--card-border-hover", t.cardBorderHover());
    set("--slider-fill", t.sliderFill()); set("--lock", t.lock());
    var typ = (m.theme && m.theme.typography) || {};
    var fam = function (role, fb) {
      var c = typ[role];
      if (c && c.family) {
        var a = Array.isArray(c.family) ? c.family : [c.family];
        return a.map(function (f) { return /\s/.test(f) ? ('"' + f + '"') : f; }).join(",");
      }
      return fb;
    };
    set("--font-title", fam("title", "Georgia,serif"));
    set("--font-body", fam("body", "system-ui,sans-serif"));
  }

  _build(state) {
    var r = this._root;
    this._destroyShader();
    this._setVars();
    r.className = "menu-root skin-" + this.constructor.skinId + " state-" + state.toLowerCase();
    r.innerHTML = "";
    r.appendChild(this._bgLayer(state));
    if (state === "START") r.appendChild(this._startScreen());
    else if (state === "LEVEL_SELECT") r.appendChild(this._levelSelect());
    else if (state === "SETTINGS") r.appendChild(this._settings());
    else if (state === "RESULTS") r.appendChild(this._results());
    else if (state === "PAUSE") r.appendChild(this._pause());
  }

  _bgLayer(state) {
    // PAUSE: scrim semi-trasparente, cosi' la scena congelata sul canvas resta
    // visibile dietro (il core non ridisegna ma nemmeno pulisce il canvas).
    if (state === "PAUSE") return this.el("div", "pause-scrim");
    var bg = this.el("div", "menu-bg");
    if (this.constructor.skinId === "default") {
      var m = this.game.manifest;
      if (m.menu_poster) {
        bg.style.backgroundImage = "linear-gradient(rgba(6,10,20,.55),rgba(6,10,20,.55)),url(" + (m._base + m.menu_poster) + ")";
      }
    }
    this._decorate(bg);
    this._maybeShader(bg);
    return bg;
  }

  // Decoro di sfondo: lucciole solo se il tema le richiede (parita' col
  // DefaultSkin Python). Sovrascritto dagli skin ricchi.
  _decorate(bg) {
    var p = (this.game.manifest.theme && this.game.manifest.theme.particles) || {};
    if (p.type !== "fireflies") return;
    var n = p.density || 6;
    for (var i = 0; i < n; i++) {
      var f = this.el("span", "firefly");
      f.style.left = ((i * 37 + 13) % 92 + 4) + "%";
      f.style.top = ((i * 53 + 20) % 70 + 12) + "%";
      f.style.animationDelay = (i * 1.7) + "s";
      bg.appendChild(f);
    }
  }

  _startScreen() {
    var g = this.game, m = g.manifest;
    var wrap = this.el("div", "start-screen");
    wrap.appendChild(this.el("h1", "menu-title big", g.t(m.title_key, m.game_id)));
    wrap.appendChild(this.el("div", "start-prompt", g.t("start_prompt", "Clicca per iniziare")));
    wrap.addEventListener("click", function () { g._startFromMenu(); });
    return wrap;
  }

  _levelSelect() {
    var self = this, g = this.game, m = g.manifest, data = g.save;
    var wrap = this.el("div", "level-select");
    var gear = this.el("button", "gear-btn");
    gear.setAttribute("aria-label", g.t("settings_title", "Impostazioni"));
    gear.innerHTML = _SVG_GEAR;
    gear.addEventListener("click", function () { g.audio.sfx("click"); g._openSettings(); });
    wrap.appendChild(gear);
    wrap.appendChild(this.el("h1", "menu-title", g.t(m.title_key, m.game_id)));
    wrap.appendChild(this.el("div", "ls-sub", g.t("menu_select_scene", "Seleziona una scena")));
    (m.levels || []).forEach(function (lvl) {
      var grp = self.el("div", "level-group");
      grp.appendChild(self.el("h2", "level-name", g.t(lvl.name_key || lvl.id, lvl.id)));
      var grid = self.el("div", "scene-grid");
      (lvl.scenes || []).forEach(function (sc, i) {
        var locked = !Save.isSceneUnlocked(data, m, lvl.id, i);
        var stars = Save.getStars(data, lvl.id, sc.id);
        var card = self.el("button", "scene-card" + (locked ? " locked" : ""));
        if (sc.thumb) {
          var img = self.el("img", "scene-thumb");
          img.src = m._base + sc.thumb; img.alt = ""; img.loading = "lazy";
          card.appendChild(img);
        }
        card.appendChild(self.el("div", "card-veil"));
        if (!locked && stars > 0) {
          var st = self.el("div", "stars");
          for (var s = 0; s < 3; s++) {
            var sv = self.el("span", "star" + (s < stars ? " on" : ""));
            sv.innerHTML = _SVG_STAR; st.appendChild(sv);
          }
          card.appendChild(st);
        }
        var meta = self.el("div", "card-meta");
        meta.appendChild(self.el("div", "scene-name", g.t(sc.id + "_name", sc.id)));
        var n = (sc.objects || []).filter(function (o) { return o.is_goal; }).length;
        meta.appendChild(self.el("div", "scene-count", n + " " + g.t("menu_objects", "oggetti")));
        card.appendChild(meta);
        if (locked) { var lb = self.el("div", "lock-badge"); lb.innerHTML = _SVG_LOCK; card.appendChild(lb); }
        card.addEventListener("click", function () {
          if (locked) { g.audio.sfx("miss"); return; }
          g.audio.sfx("click"); self.hide(); g.startScene(lvl, sc);
        });
        grid.appendChild(card);
      });
      grp.appendChild(grid);
      wrap.appendChild(grp);
    });
    return wrap;
  }

  _settings() {
    var self = this, g = this.game, m = g.manifest;
    var wrap = this.el("div", "settings-screen");
    wrap.appendChild(this.el("h1", "menu-title", g.t("settings_title", "Impostazioni")));
    var panel = this.el("div", "set-panel");
    panel.appendChild(this._slider(g.t("label_music_volume", "Volume Musica"), g.audio.musicVol, function (v) {
      g.audio.musicVol = v;
      if (g.audio.musicEl) g.audio.musicEl.volume = g.audio.muted ? 0 : v;
      g._saveSettings();
    }, false));
    panel.appendChild(this._slider(g.t("label_sfx_volume", "Volume Effetti"), g.audio.sfxVol, function (v) {
      g.audio.sfxVol = v; g._saveSettings();
    }, true));
    var langRow = this.el("div", "lang-row");
    langRow.appendChild(this.el("div", "set-label", g.t("label_language", "Lingua")));
    var btns = this.el("div", "lang-btns");
    var langs = (m.languages && m.languages.length) ? m.languages : ["it", "en", "de", "es", "fr"];
    langs.forEach(function (lg) {
      var b = self.el("button", "lang-btn" + (lg === g.lang ? " active" : ""), lg.toUpperCase());
      b.addEventListener("click", function () { g.lang = lg; g._saveSettings(); g.audio.sfx("click"); self.refresh(); });
      btns.appendChild(b);
    });
    langRow.appendChild(btns); panel.appendChild(langRow);
    wrap.appendChild(panel);
    var back = this.el("button", "back-btn", g.t("btn_back", "Indietro"));
    back.addEventListener("click", function () {
      g.audio.sfx("click");
      g.state = (g._prevState === "PAUSE") ? "PAUSE" : "LEVEL_SELECT";
      g.invalidate();
    });
    wrap.appendChild(back);
    return wrap;
  }

  _slider(label, val, onInput, sfxChange) {
    var self = this, row = this.el("div", "set-row");
    var top = this.el("div", "set-row-top");
    top.appendChild(this.el("span", "set-label", label));
    var out = this.el("span", "set-val", Math.round(val * 100) + "%");
    top.appendChild(out); row.appendChild(top);
    var r = this.el("input", "set-range");
    r.type = "range"; r.min = "0"; r.max = "100"; r.step = "1"; r.value = String(Math.round(val * 100));
    r.addEventListener("input", function () {
      var v = (parseInt(r.value, 10) || 0) / 100;
      out.textContent = Math.round(v * 100) + "%";
      onInput(v);
      if (sfxChange) self.game.audio.sfx("found");
    });
    row.appendChild(r);
    return row;
  }

  _stat(k, v) {
    var row = this.el("div", "res-stat");
    row.appendChild(this.el("span", "k", k));
    row.appendChild(this.el("span", "v", v));
    return row;
  }

  _results() {
    var self = this, g = this.game;
    var r = g.result || { score: 0, stars: 0, allFound: false, found: 0, total: 0, timeElapsed: 0, sceneIdx: 0 };
    var wrap = this.el("div", "results-screen");
    var panel = this.el("div", "results-panel");
    panel.appendChild(this.el("h1", "results-title " + (r.allFound ? "win" : "lose"),
      g.t(r.allFound ? "mission_complete" : "mission_failed", r.allFound ? "Completato!" : "Tempo scaduto")));
    var stars = this.el("div", "res-stars");
    for (var i = 0; i < 3; i++) {
      var sv = this.el("span", "star" + (i < r.stars ? " on" : ""));
      sv.innerHTML = _SVG_STAR; stars.appendChild(sv);
    }
    panel.appendChild(stars);
    panel.appendChild(this.el("div", "res-score-label", g.t("total_score", "Punteggio")));
    panel.appendChild(this.el("div", "res-score", String(r.score)));
    if (r.allFound) panel.appendChild(this.el("div", "res-perfect", g.t("perfect_score", "Perfetto!")));
    var stats = this.el("div", "res-stats");
    var mm = String(Math.floor(r.timeElapsed / 60)).padStart(2, "0");
    var ss = String(Math.floor(r.timeElapsed % 60)).padStart(2, "0");
    stats.appendChild(this._stat(g.t("time_elapsed", "Tempo"), mm + ":" + ss));
    stats.appendChild(this._stat(g.t("objects_found", "Oggetti"), r.found + "/" + r.total));
    panel.appendChild(stats);
    var btns = this.el("div", "res-btns");
    var retry = this.el("button", "menu-btn", g.t("btn_retry", "Riprova"));
    retry.addEventListener("click", function () { g.audio.sfx("click"); self.hide(); g.startScene(g.level, g.sceneDef); });
    btns.appendChild(retry);
    var hasNext = !!(r.allFound && g.level && g.level.scenes[r.sceneIdx + 1]);
    var prim = this.el("button", "menu-btn primary", g.t(hasNext ? "btn_next" : "btn_continue", hasNext ? "Avanti" : "Continua"));
    prim.addEventListener("click", function () {
      g.audio.sfx("click");
      if (hasNext) { self.hide(); g.startScene(g.level, g.level.scenes[r.sceneIdx + 1]); return; }
      g.state = "LEVEL_SELECT"; g.audio.playMusic(g.manifest.menu_music); g.invalidate();
    });
    btns.appendChild(prim);
    panel.appendChild(btns);
    wrap.appendChild(panel);
    return wrap;
  }

  _pause() {
    var self = this, g = this.game;
    var wrap = this.el("div", "pause-screen");
    var panel = this.el("div", "pause-panel");
    panel.appendChild(this.el("h1", "pause-title", g.t("hud_paused", "Pausa")));
    var btns = this.el("div", "pause-btns");
    var mk = function (label, primary, fn) {
      var b = self.el("button", "menu-btn" + (primary ? " primary" : ""), label);
      b.addEventListener("click", function () { g.audio.sfx("click"); fn(); });
      return b;
    };
    btns.appendChild(mk(g.t("btn_resume", "Riprendi"), true, function () { g.state = "SCENE"; g.invalidate(); }));
    btns.appendChild(mk(g.t("settings_title", "Impostazioni"), false, function () { g._openSettings(); }));
    btns.appendChild(mk(g.t("btn_restart", "Ricomincia"), false, function () { self.hide(); g.startScene(g.level, g.sceneDef); }));
    btns.appendChild(mk(g.t("btn_quit_to_main", "Menu"), false, function () { g.state = "LEVEL_SELECT"; g.audio.playMusic(g.manifest.menu_music); g.invalidate(); }));
    panel.appendChild(btns);
    wrap.appendChild(panel);
    return wrap;
  }
}
MenuSkinWeb.skinId = "default";
MenuSkinWeb.handledStates = ["START", "LEVEL_SELECT", "SETTINGS", "RESULTS", "PAUSE"];
window.MENU_SKINS.default = MenuSkinWeb;

function makeMenuSkin(game) {
  var id = (game.manifest && game.manifest.ui_theme) || "default";
  var C = window.MENU_SKINS[id] || window.MENU_SKINS.default;
  if (!C) return null;
  try { return new C(game); }
  catch (e) {
    console.warn("menu skin init fallita:", e);
    return window.MENU_SKINS.default ? new window.MENU_SKINS.default(game) : null;
  }
}
window.makeMenuSkin = makeMenuSkin;
