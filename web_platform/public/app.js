"use strict";

async function loadCatalog() {
  const grid = document.getElementById("grid");
  let data;
  try {
    data = await fetch("/catalog.json", { cache: "no-cache" }).then(r => r.json());
  } catch (e) {
    grid.innerHTML = '<div class="empty">Catalogo non disponibile.</div>';
    return;
  }
  const games = (data && data.games) || [];
  if (!games.length) {
    grid.innerHTML = '<div class="empty">Nessun gioco ancora. Vai nel <a href="/admin" style="color:var(--accent)">Back Office</a> per aggiungerne uno.</div>';
    return;
  }
  grid.innerHTML = "";
  for (const g of games) {
    const card = document.createElement("a");
    card.className = "card";
    card.href = "/" + g.url;
    const cover = g.og_image || g.icon || "";
    const langs = (g.languages || []).map(l => `<span class="tag">${l}</span>`).join("");
    card.innerHTML = `
      <div class="cover" style="${cover ? `background-image:url('/${cover}')` : `background:linear-gradient(135deg,${g.theme_color || "#1b2b4d"},#0c1120)`}">
        <div class="play"><span>▶ Gioca</span></div>
      </div>
      <div class="body">
        <div class="title">${escapeHtml(g.title || g.id)}</div>
        <div class="meta">${g.version ? `<span class="tag">v${g.version}</span>` : ""}${langs}</div>
      </div>`;
    grid.appendChild(card);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

loadCatalog();
