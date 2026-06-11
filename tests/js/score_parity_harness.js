// tests/js/score_parity_harness.js
//
// Harness di parita' Python<->JS per lo scoring di fine scena.
//
// Esegue la VERA funzione game.js::_doFinish (senza modificarla) dentro una
// sandbox VM, stubbando solo i side-effect (Save/performance/audio/transizioni).
// Riceve da stdin {rules, cases:[{score,timeLeft,timeTotal,found,total}]} e
// stampa su stdout [{bonus,stars,score,allFound}] per ogni caso.
//
// Uso:  node score_parity_harness.js <path/to/game.js>  < cases.json
// Vedi tests/test_web_sync.py::test_scene_score_parity_python_vs_js

"use strict";
const fs = require("fs");
const vm = require("vm");

const gameJsPath = process.argv[2];
if (!gameJsPath) {
  process.stderr.write("manca il path di game.js\n");
  process.exit(2);
}

const code = fs.readFileSync(gameJsPath, "utf8");

// Le dichiarazioni 'class' top-level di uno script VM non finiscono sul global
// object: le esponiamo esplicitamente appendendo un'assegnazione (non tocca il
// file reale, solo la copia valutata qui).
const sandbox = {
  // Side-effect richiamati da _doFinish, neutralizzati.
  Save: { record() { return null; }, load() { return {}; }, getStars() { return 0; } },
  performance: { now() { return 0; } },
  window: { location: { search: "" } },
  console,
};
vm.createContext(sandbox);
vm.runInContext(code + "\nglobalThis.Game = Game;", sandbox, { filename: "game.js" });

const Game = sandbox.Game;
if (typeof Game !== "function") {
  process.stderr.write("classe Game non trovata dopo la valutazione di game.js\n");
  process.exit(3);
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const rules = input.rules;
const cases = input.cases || [];
const missConsecutive = input.missConsecutive || [];

// Scoring di fine scena: esegue la vera _doFinish.
const scores = cases.map((c) => {
  // Istanza senza costruttore: evitiamo l'inizializzazione che richiede il browser.
  const g = Object.create(Game.prototype);
  g.R = rules;
  g.score = c.score;
  g.timeLeft = c.timeLeft;
  g.timeTotal = c.timeTotal;
  // 'goals' e' un getter su this.objects filtrato per is_goal: impostiamo objects.
  g.objects = Array.from({ length: c.total }, (_, i) => ({ is_goal: true, found: i < c.found }));
  g.sceneDef = { id: "S" };
  g.level = { id: "L", scenes: [g.sceneDef] };
  g.manifest = { game_id: "G" };
  // Stub dei side-effect d'istanza usati da _doFinish.
  g._makeConfetti = () => [];
  g.audio = { stopMusic() {} };
  g._beginFade = () => {};

  g._doFinish();
  const r = g.result;
  return { bonus: r.bonus, stars: r.stars, score: r.score, allFound: r.allFound };
});

// Penalita' miss progressiva: esegue la vera _missPenalty per ogni lunghezza di sequenza.
const missPenalties = missConsecutive.map((n) => {
  const g = Object.create(Game.prototype);
  g.R = rules;
  return g._missPenalty(n);
});

process.stdout.write(JSON.stringify({ scores, missPenalties }));
