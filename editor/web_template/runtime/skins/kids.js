/*
 * skins/kids.js — direzione "Playground": cielo + sole coi raggi, coriandoli,
 * card "sticker" arrotondate con ombra giocattolo, titolo tondo che rimbalza.
 * Eredita struttura e schermate da MenuSkinWeb; cambia solo look & feel.
 */

var _KIDS_CSS = "\
#menu-root.skin-kids{--text:#ffffff}\
#menu-root.skin-kids .menu-bg{background:linear-gradient(#5bbdf5,#39a3e6 56%,#74cf9a 100%)}\
#menu-root.skin-kids .menu-bg .sun{position:absolute;top:-46px;right:-34px;width:150px;height:150px;border-radius:50%;background:#ffd744;box-shadow:0 0 0 14px rgba(255,221,90,.32)}\
#menu-root.skin-kids .menu-bg .sun::before{content:'';position:absolute;inset:-42px;border-radius:50%;background:repeating-conic-gradient(rgba(255,210,60,.5) 0 5deg,transparent 5deg 45deg);animation:ksun 44s linear infinite}\
#menu-root.skin-kids .confetti{position:absolute;top:-6vh;width:9px;height:14px;border-radius:2px;animation:kfall linear infinite}\
#menu-root.skin-kids .menu-title{font-family:var(--font-title,'Comic Sans MS',Verdana,sans-serif);color:#fff;text-shadow:0 3px 0 #2a7ec0,0 5px 8px rgba(0,0,0,.18);animation:kbounce 1.9s ease-in-out infinite}\
#menu-root.skin-kids .ls-sub{color:#eaffff}\
#menu-root.skin-kids .level-name{font-family:var(--font-title,'Comic Sans MS',Verdana,sans-serif);color:#fff;text-shadow:0 2px 0 #2a7ec0}\
#menu-root.skin-kids .scene-card{border-radius:22px;border:5px solid #fff;background:#bcd0e0;box-shadow:0 7px 0 #2a7ec0}\
#menu-root.skin-kids .scene-card:hover{transform:translateY(-4px);box-shadow:0 11px 0 #2a7ec0}\
#menu-root.skin-kids .scene-name{font-family:var(--font-title,'Comic Sans MS',Verdana,sans-serif);font-weight:700}\
#menu-root.skin-kids .scene-count{color:#ffe6a0}\
#menu-root.skin-kids .gear-btn{background:#fff;color:#39a3e6;border:none;box-shadow:0 3px 0 #2a7ec0}\
#menu-root.skin-kids .set-panel{background:rgba(255,255,255,.82);border:none}\
#menu-root.skin-kids .set-row-top,#menu-root.skin-kids .set-label{color:#2a8f5e}\
#menu-root.skin-kids .lang-btn{color:#2a6;background:rgba(255,255,255,.7);border:none}\
#menu-root.skin-kids .lang-btn.active{background:#ffce3a;color:#7a5a00}\
#menu-root.skin-kids .back-btn{background:#ffce3a;color:#7a5a00;box-shadow:0 5px 0 #c99a1e}\
@keyframes ksun{to{transform:rotate(360deg)}}\
@keyframes kbounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}\
@keyframes kfall{0%{transform:translateY(0) rotate(0);opacity:0}10%{opacity:1}100%{transform:translateY(120vh) rotate(360deg);opacity:.9}}\
@media (prefers-reduced-motion:reduce){#menu-root.skin-kids *{animation:none!important}}\
";

(function () {
  if (!document.getElementById("menu-skin-css-kids")) {
    var s = document.createElement("style");
    s.id = "menu-skin-css-kids";
    s.textContent = _KIDS_CSS;
    (document.head || document.documentElement).appendChild(s);
  }
})();

class KidsMenuSkin extends MenuSkinWeb {
  _decorate(bg) {
    bg.appendChild(this.el("div", "sun"));
    var cols = ["#ff7aa2", "#ffd23a", "#58d68d", "#ffffff", "#7fd0f5"];
    for (var i = 0; i < 14; i++) {
      var c = this.el("div", "confetti");
      c.style.left = ((i * 61 + 7) % 96) + "%";
      c.style.background = cols[i % cols.length];
      c.style.animationDuration = (5 + (i % 5)) + "s";
      c.style.animationDelay = (-(i * 0.7)) + "s";
      bg.appendChild(c);
    }
  }
}
KidsMenuSkin.skinId = "kids";
window.MENU_SKINS.kids = KidsMenuSkin;
