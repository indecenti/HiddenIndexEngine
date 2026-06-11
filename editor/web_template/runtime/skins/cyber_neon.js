/*
 * skins/cyber_neon.js — direzione "Cyber Neon": griglia retrofuturista in
 * prospettiva, alone neon, scanline, titolo monospace con glitch/aberrazione,
 * card spigolose con bordo neon. Eredita struttura da MenuSkinWeb.
 */

var _CYBER_CSS = "\
#menu-root.skin-cyber_neon .menu-bg{background:#0a0c19;overflow:hidden}\
#menu-root.skin-cyber_neon .neon-glow{position:absolute;left:0;right:0;top:26%;height:34%;pointer-events:none;background:radial-gradient(60% 100% at 50% 100%,rgba(255,0,255,.28),rgba(255,0,255,0) 70%)}\
#menu-root.skin-cyber_neon .grid{position:absolute;left:-60%;right:-60%;bottom:0;height:60%;pointer-events:none;background-image:linear-gradient(rgba(0,210,225,.4) 1px,transparent 1px),linear-gradient(90deg,rgba(0,210,225,.3) 1px,transparent 1px);background-size:46px 46px;transform:perspective(300px) rotateX(62deg);transform-origin:bottom center;animation:cybergrid 4.5s linear infinite}\
#menu-root.skin-cyber_neon .scan{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(rgba(0,0,0,.16) 0 1px,transparent 1px 3px)}\
#menu-root.skin-cyber_neon .menu-title{font-family:var(--font-title,Consolas,monospace);color:#0ff;letter-spacing:4px;text-transform:uppercase;text-shadow:0 0 8px #0ff,2px 0 0 rgba(255,0,255,.8),-2px 0 0 rgba(255,0,255,.8);animation:cyberglitch 3.5s steps(1,end) infinite}\
#menu-root.skin-cyber_neon .ls-sub{color:#0ff}\
#menu-root.skin-cyber_neon .level-name{font-family:var(--font-title,Consolas,monospace);color:#f5f;text-transform:uppercase;letter-spacing:2px}\
#menu-root.skin-cyber_neon .scene-card{border-radius:0;border-color:#0aa;background:#0a0c19;box-shadow:inset 0 0 0 1px rgba(0,255,255,.18)}\
#menu-root.skin-cyber_neon .scene-card:hover{border-color:#f0f;box-shadow:0 0 22px rgba(255,0,255,.5),inset 0 0 0 1px rgba(0,255,255,.3);transform:none}\
#menu-root.skin-cyber_neon .scene-name{font-family:var(--font-title,Consolas,monospace);letter-spacing:1px}\
#menu-root.skin-cyber_neon .gear-btn{color:#0ff;border-color:#066;background:rgba(0,20,30,.5)}\
#menu-root.skin-cyber_neon .set-panel,#menu-root.skin-cyber_neon .results-panel,#menu-root.skin-cyber_neon .pause-panel{background:#0c1020;border-color:#0aa}\
#menu-root.skin-cyber_neon .menu-btn.primary,#menu-root.skin-cyber_neon .back-btn,#menu-root.skin-cyber_neon .lang-btn.active{background:#f0f;color:#0a0c19}\
@keyframes cybergrid{from{background-position:0 0}to{background-position:0 46px}}\
@keyframes cyberglitch{0%,100%{transform:translate(0,0)}48%{transform:translate(0,0)}49%{transform:translate(-2px,0)}50%{transform:translate(2px,0)}51%{transform:translate(0,0)}}\
@media (prefers-reduced-motion:reduce){#menu-root.skin-cyber_neon .grid,#menu-root.skin-cyber_neon .menu-title{animation:none!important}}\
";

(function () {
  if (!document.getElementById("menu-skin-css-cyber_neon")) {
    var s = document.createElement("style");
    s.id = "menu-skin-css-cyber_neon";
    s.textContent = _CYBER_CSS;
    (document.head || document.documentElement).appendChild(s);
  }
})();

class CyberNeonMenuSkin extends MenuSkinWeb {
  _decorate(bg) {
    bg.appendChild(this.el("div", "neon-glow"));
    bg.appendChild(this.el("div", "grid"));
    bg.appendChild(this.el("div", "scan"));
  }
}
CyberNeonMenuSkin.skinId = "cyber_neon";
window.MENU_SKINS.cyber_neon = CyberNeonMenuSkin;
