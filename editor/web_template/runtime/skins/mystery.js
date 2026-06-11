/*
 * skins/mystery.js — direzione "The Detective": noir investigativo, toni caldi
 * desaturati, vignettatura forte, pulviscolo nella luce, titolo serif, card in
 * seppia che si rivela a colori in hover. Eredita struttura da MenuSkinWeb.
 */

var _MYSTERY_CSS = "\
#menu-root.skin-mystery .menu-bg{background:#140d06;overflow:hidden}\
#menu-root.skin-mystery .vignette{position:absolute;inset:0;pointer-events:none;background:radial-gradient(78% 74% at 50% 44%,rgba(0,0,0,0) 34%,rgba(8,5,2,.92) 100%)}\
#menu-root.skin-mystery .dust{position:absolute;top:-6vh;width:3px;height:3px;border-radius:50%;background:rgba(190,160,100,.55);animation:mdust linear infinite}\
#menu-root.skin-mystery .menu-title{font-family:var(--font-title,Georgia,serif);color:#e9c98a;letter-spacing:2px;text-shadow:0 2px 6px rgba(0,0,0,.7)}\
#menu-root.skin-mystery .ls-sub{color:#b89760}\
#menu-root.skin-mystery .level-name{font-family:var(--font-title,Georgia,serif);color:#c8a262;font-style:italic}\
#menu-root.skin-mystery .scene-card{border-radius:8px;border-color:#6e5524;background:#1a1108;filter:sepia(.28)}\
#menu-root.skin-mystery .scene-card:hover{border-color:#b8954a;filter:sepia(0);box-shadow:0 0 22px rgba(150,110,40,.45)}\
#menu-root.skin-mystery .scene-name{font-family:var(--font-title,Georgia,serif)}\
#menu-root.skin-mystery .scene-count{color:#b89760}\
#menu-root.skin-mystery .gear-btn{color:#c8a262;border-color:#4a3a1c;background:rgba(20,13,6,.6)}\
#menu-root.skin-mystery .set-panel,#menu-root.skin-mystery .results-panel,#menu-root.skin-mystery .pause-panel{background:#1a1108;border-color:#8a6a30}\
#menu-root.skin-mystery .menu-btn.primary,#menu-root.skin-mystery .back-btn,#menu-root.skin-mystery .lang-btn.active{background:#9a7430;color:#1a1108}\
@keyframes mdust{0%{transform:translateY(0);opacity:0}15%{opacity:.8}100%{transform:translateY(112vh);opacity:.2}}\
@media (prefers-reduced-motion:reduce){#menu-root.skin-mystery .dust{animation:none!important}}\
";

(function () {
  if (!document.getElementById("menu-skin-css-mystery")) {
    var s = document.createElement("style");
    s.id = "menu-skin-css-mystery";
    s.textContent = _MYSTERY_CSS;
    (document.head || document.documentElement).appendChild(s);
  }
})();

class MysteryMenuSkin extends MenuSkinWeb {
  _decorate(bg) {
    for (var i = 0; i < 14; i++) {
      var d = this.el("div", "dust");
      d.style.left = ((i * 53 + 9) % 97) + "%";
      d.style.animationDuration = (7 + (i % 5)) + "s";
      d.style.animationDelay = (-(i * 0.9)) + "s";
      bg.appendChild(d);
    }
    bg.appendChild(this.el("div", "vignette"));
  }
}
MysteryMenuSkin.skinId = "mystery";
window.MENU_SKINS.mystery = MysteryMenuSkin;
