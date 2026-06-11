/*
 * skins/horror.js — direzione "Nightmare": near-black con rossi, nebbia che
 * scorre, grana, vignetta e torcia, titolo serif spezzato con flicker.
 * Eredita struttura e schermate da MenuSkinWeb; cambia solo look & feel.
 */

var _HORROR_CSS = "\
#menu-root.skin-horror .menu-bg{background:#090304}\
#menu-root.skin-horror .menu-bg .fog{position:absolute;width:70vw;height:70vw;border-radius:50%;background:radial-gradient(closest-side,rgba(125,40,40,.22),rgba(0,0,0,0));filter:blur(10px);animation:hfog 26s ease-in-out infinite alternate}\
#menu-root.skin-horror .menu-bg .vignette{position:absolute;inset:0;pointer-events:none;background:radial-gradient(82% 72% at 42% 48%,rgba(0,0,0,0) 26%,rgba(0,0,0,.92) 100%)}\
#menu-root.skin-horror .menu-bg .grain{position:absolute;inset:0;pointer-events:none;opacity:.08;background-image:radial-gradient(rgba(255,255,255,.7) .5px,transparent .6px);background-size:3px 3px;animation:hgrain .6s steps(3) infinite}\
#menu-root.skin-horror .menu-title{font-family:var(--font-title,'Times New Roman',Georgia,serif);color:#b51a1a;letter-spacing:5px;text-transform:uppercase;text-shadow:0 0 12px rgba(150,0,0,.5),2px 0 0 rgba(40,0,0,.6);animation:hflick 4.2s steps(1,end) infinite}\
#menu-root.skin-horror .ls-sub{color:#7c2020}\
#menu-root.skin-horror .level-name{font-family:var(--font-title,'Times New Roman',serif);color:#9b1c1c;letter-spacing:2px;text-transform:uppercase}\
#menu-root.skin-horror .scene-card{border-radius:2px;border-color:#5a1414;background:#0a0405}\
#menu-root.skin-horror .scene-card:hover{border-color:#c81e1e;box-shadow:0 0 26px rgba(180,0,0,.45);transform:none}\
#menu-root.skin-horror .scene-name{font-family:var(--font-title,'Times New Roman',serif);letter-spacing:1px}\
#menu-root.skin-horror .scene-count{color:#8f2626}\
#menu-root.skin-horror .gear-btn{color:#a31616;border-color:#3a0e0e;background:rgba(20,4,4,.5)}\
#menu-root.skin-horror .set-panel{background:rgba(10,2,2,.5);border-color:#3a0e0e}\
#menu-root.skin-horror .back-btn{background:#7a1414;color:#f0d6d6}\
#menu-root.skin-horror .lang-btn.active{background:#7a1414;color:#f0d6d6;border-color:#c81e1e}\
@keyframes hflick{0%,100%{opacity:1}6%{opacity:.5}7%{opacity:.95}40%{opacity:.8}41%{opacity:.45}43%{opacity:.92}72%{opacity:.7}}\
@keyframes hfog{from{transform:translate(-6vw,0)}to{transform:translate(8vw,3vh)}}\
@keyframes hgrain{0%{transform:translate(0,0)}50%{transform:translate(-2px,1px)}100%{transform:translate(1px,-2px)}}\
@media (prefers-reduced-motion:reduce){#menu-root.skin-horror .menu-title,#menu-root.skin-horror .fog,#menu-root.skin-horror .grain{animation:none!important}}\
";

(function () {
  if (!document.getElementById("menu-skin-css-horror")) {
    var s = document.createElement("style");
    s.id = "menu-skin-css-horror";
    s.textContent = _HORROR_CSS;
    (document.head || document.documentElement).appendChild(s);
  }
})();

class HorrorMenuSkin extends MenuSkinWeb {
  _decorate(bg) {
    for (var i = 0; i < 3; i++) {
      var f = this.el("div", "fog");
      f.style.left = (6 + i * 30) + "%";
      f.style.top = (18 + i * 18) + "%";
      f.style.animationDelay = (i * 4) + "s";
      bg.appendChild(f);
    }
    bg.appendChild(this.el("div", "grain"));
    bg.appendChild(this.el("div", "vignette"));
  }
}
HorrorMenuSkin.skinId = "horror";
window.MENU_SKINS.horror = HorrorMenuSkin;
