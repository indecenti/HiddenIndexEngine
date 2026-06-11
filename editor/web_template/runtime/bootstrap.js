// bootstrap: il registry MINIGAME_CLASSES e' popolato per auto-registrazione
// dai file minigames/*.js inclusi nel bundle (vedi web_exporter._bundle_runtime).

// ──────────────────────────────────────────────────────────────────────────
// Bootstrap
// ──────────────────────────────────────────────────────────────────────────
// Controllo di forma minimo del manifest: meglio un messaggio chiaro che uno
// stack trace oscuro dentro Game se il build e' malformato/incompleto.
function _assertManifestShape(m) {
  if (!m || typeof m !== "object") throw new Error("Manifest assente o non valido.");
  const missing = [];
  if (!m.game_id) missing.push("game_id");
  if (!Array.isArray(m.levels)) missing.push("levels[]");
  if (missing.length) {
    throw new Error(
      "Manifest del gioco malformato: campi mancanti/invalidi: " + missing.join(", ") +
      ". Ri-esegui l'export (editor.web_exporter)."
    );
  }
}

async function main() {
  const base = "./";
  // Preferisci il manifest incorporato (manifest.js -> window.__MANIFEST__):
  // funziona da file:// senza fetch. Fallback a fetch per setup http custom.
  let manifest = window.__MANIFEST__;
  if (!manifest) {
    manifest = await fetch(base + "manifest.json").then(r => r.json());
  }
  _assertManifestShape(manifest);
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
