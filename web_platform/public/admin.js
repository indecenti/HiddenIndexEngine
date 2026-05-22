"use strict";

const $ = id => document.getElementById(id);

async function api(path, opts) {
  const r = await fetch(path, opts);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  return { ok: r.ok, status: r.status, data };
}

async function refreshAuth() {
  const { data } = await api("/api/me");
  const authed = !!(data && data.authed);
  $("loginBox").style.display = authed ? "none" : "block";
  $("adminBox").style.display = authed ? "block" : "none";
  $("logout").style.display = authed ? "inline" : "none";
  if (authed) loadGames();
}

async function login() {
  $("loginMsg").textContent = "";
  const { ok, data } = await api("/api/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user: $("user").value, pass: $("pass").value }),
  });
  if (ok) refreshAuth();
  else $("loginMsg").textContent = (data && data.error) || "Errore di accesso";
}

async function logout(e) {
  e.preventDefault();
  await api("/api/logout", { method: "POST" });
  refreshAuth();
}

async function loadGames() {
  const list = $("list");
  const cat = await fetch("/catalog.json", { cache: "no-cache" }).then(r => r.json()).catch(() => ({ games: [] }));
  const games = cat.games || [];
  if (!games.length) { list.innerHTML = '<p style="color:var(--dim)">Nessun gioco.</p>'; return; }
  list.innerHTML = "";
  for (const g of games) {
    const el = document.createElement("div");
    el.className = "gameitem";
    const cover = g.icon || g.og_image || "";
    el.innerHTML = `
      <img src="${cover ? "/" + cover : ""}" alt="">
      <div class="info"><div class="t">${esc(g.title || g.id)}</div>
        <div class="s">${g.id} · v${g.version || "?"} · ${(g.languages || []).join(", ")}</div></div>
      <a class="btn ghost" href="/${g.url}" target="_blank" style="padding:8px 12px">Apri</a>
      <button class="del" data-id="${esc(g.id)}">Elimina</button>`;
    list.appendChild(el);
  }
  list.querySelectorAll(".del").forEach(b => b.addEventListener("click", () => delGame(b.dataset.id)));
}

async function delGame(id) {
  if (!confirm(`Eliminare "${id}"?`)) return;
  const { ok, data } = await api("/api/delete", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (ok) loadGames();
  else alert((data && data.error) || "Errore");
}

function uploadZip(file) {
  const msg = $("upMsg"); msg.className = "msg"; msg.textContent = "";
  if (!file || !/\.zip$/i.test(file.name)) { msg.className = "msg err"; msg.textContent = "Serve un file .zip"; return; }
  const bar = $("bar"); bar.classList.add("show"); const fill = bar.firstElementChild; fill.style.width = "0";
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.setRequestHeader("X-Filename", file.name);
  xhr.upload.onprogress = e => { if (e.lengthComputable) fill.style.width = (e.loaded / e.total * 100) + "%"; };
  xhr.onload = () => {
    bar.classList.remove("show");
    let d = {}; try { d = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status === 200 && d.ok) {
      msg.className = "msg ok"; msg.textContent = `Caricato: ${d.game.title} (v${d.game.version})`;
      loadGames();
    } else {
      msg.className = "msg err"; msg.textContent = (d && d.error) || `Errore (${xhr.status})`;
    }
  };
  xhr.onerror = () => { bar.classList.remove("show"); msg.className = "msg err"; msg.textContent = "Errore di rete"; };
  xhr.send(file);
}

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// Eventi
$("loginBtn").addEventListener("click", login);
$("pass").addEventListener("keydown", e => { if (e.key === "Enter") login(); });
$("logout").addEventListener("click", logout);
$("pick").addEventListener("click", e => { e.preventDefault(); $("file").click(); });
$("file").addEventListener("change", e => { if (e.target.files[0]) uploadZip(e.target.files[0]); });

const drop = $("drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) uploadZip(f); });
drop.addEventListener("click", () => $("file").click());

refreshAuth();
