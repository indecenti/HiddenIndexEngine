# HiddenEngine Web Platform — Design

Portale che raccoglie i giochi esportati (vedi `WEB_EXPORT.md`) e li pubblica
online, con un **Back Office (BO)** protetto da login per aggiungerli in
**drag & drop**.

## 1. Obiettivi
- **Vetrina pubblica**: griglia dei giochi (copertina, titolo, lingue) → click → gioca.
- **Back Office** (login): caricare un gioco trascinando un file **.zip** (il build
  esportato), eliminarlo, vedere la lista. Niente conoscenze tecniche richieste.
- **Zero nuove dipendenze**: tutto con la standard library Python (http.server,
  hmac, hashlib, zipfile). Niente Flask/Django/DB esterni.
- **Autosufficiente**: i giochi caricati restano file statici dentro la piattaforma.

## 2. Perche' serve un backend
La sola vetrina potrebbe essere statica (legge un catalogo JSON). Ma **login** e
**upload** richiedono un server: autenticare, ricevere lo .zip, scompattarlo,
aggiornare il catalogo. Lo realizziamo con `http.server` (stdlib) — nessuna dip.

## 3. Architettura

```
web_platform/
├── server.py          # server HTTP (vetrina + BO + API)   [stdlib]
├── config.json        # credenziali admin (hash) + secret di sessione  (NON committare)
├── catalog.json       # catalogo aggregato (rigenerato ad ogni modifica)
├── public/
│   ├── index.html     # vetrina pubblica (griglia giochi)
│   ├── style.css
│   ├── app.js         # legge catalog.json, render griglia, apre il gioco
│   ├── admin.html     # BO: login + drag&drop upload + lista/elimina
│   └── admin.js
└── games/
    └── <id>/...       # build esportato del gioco (index.html, v<X.Y>/, game.json…)
```

### Endpoint
| Metodo | Path | Auth | Descrizione |
|---|---|---|---|
| GET | `/` | no | Vetrina (`public/index.html`) |
| GET | `/catalog.json` | no | Catalogo giochi |
| GET | `/games/<...>` | no | File statici dei giochi |
| GET | `/admin` | no | Pagina BO (login o pannello) |
| GET | `/api/me` | no | Stato sessione (loggato?) |
| POST | `/api/login` | no | `{user,pass}` → cookie di sessione |
| POST | `/api/logout` | si | Termina sessione |
| POST | `/api/upload` | si | Upload .zip del gioco → scompatta in `games/<id>/` |
| POST | `/api/delete` | si | `{id}` → rimuove il gioco |

### Autenticazione (semplice, stdlib)
- `config.json`: `{ "user": "...", "pass_hash": "<sha256(salt+password)>", "salt": "...", "secret": "<random>" }`.
- Login: confronta hash; se ok, imposta cookie `sid = base64(payload).hmac(secret)` con scadenza.
- Le route protette verificano la firma e la scadenza del cookie.
- **Nota onesta**: e' un BO leggero per uso interno/self-hosting, non un sistema
  di sicurezza enterprise (no rate-limiting, no HTTPS gestito qui). Per la
  produzione: mettere dietro un reverse proxy con TLS e password robusta.

### Formato di upload (drag & drop)
- Si trascina un **.zip** del build esportato del gioco (la cartella
  `build_web/<gioco>/` zippata, oppure il suo contenuto).
- Il server: salva lo zip in temp → scompatta → trova la cartella che contiene
  `game.json` (root o un livello sotto) → la sposta in `games/<id>/`
  (id = `game.json.id`) → rigenera `catalog.json`.
- Helper: `python -m editor.web_exporter <gioco> --zip` (da aggiungere) o, per il
  test iniziale, copia diretta della cartella + rigenerazione catalogo.

### Catalogo
- `catalog.json` = aggregato dei `games/<id>/game.json`, con i path riscritti
  relativi alla piattaforma (`games/<id>/...`). La vetrina legge solo questo.

## 4. Flusso utente
- **Giocatore**: apre `/` → vede la griglia → click su un gioco → `/games/<id>/`
  (la landing del gioco reindirizza alla versione latest) → gioca.
- **Admin**: apre `/admin` → login → trascina lo .zip → il gioco appare nella vetrina.

## 5. Avvio
```
python web_platform/server.py            # http://localhost:8800
python web_platform/server.py --port 8812 --host 0.0.0.0   # esposto in rete
```
- Vetrina: `http://localhost:<porta>/`
- Back Office: `http://localhost:<porta>/admin`

### Credenziali
- Primo avvio: se manca `config.json`, ne crea uno con utente `admin` e una
  password **casuale stampata in console** (da cambiare).
- Stato attuale di test (questo repo): **admin / `test1234`** (cambiala in produzione,
  o cancella `config.json` per rigenerarne una nuova al prossimo avvio).
- `config.json`, `catalog.json` e `games/` sono dati locali: NON committarli
  (aggiungili a `.gitignore`).

### Aggiungere un gioco
- Esporta il gioco con lo zip distribuibile:
  `python -m editor.web_exporter <Gioco> --zip`  → produce `build_web/<Gioco>.zip`
  (solo la versione latest, leggero).
- Vai in `/admin`, fai login, **trascina lo .zip** nella dropzone. Fatto: appare in vetrina.
- In alternativa, copia la cartella `build_web/<Gioco>/` dentro `web_platform/games/<id>/`
  e riavvia (il catalogo si rigenera all'avvio).

### Stato verificato
Sono pre-installati **LineVenture** e **Malonno_Survivors**. Pipeline testata
end-to-end: login, upload .zip (95 MB) → install → catalogo aggiornato → gioco
giocabile su `/games/<id>/`; delete autenticato; richieste non autorizzate respinte.

## 6. Roadmap (oltre l'MVP)
- Generazione zip dall'exporter (`--zip`) e upload diretto dall'editor.
- Pagine gioco con meta dedicati (SEO/social) servite dal portale.
- Multi-utente, ruoli, statistiche di gioco.
- Storage su CDN/object-storage invece del filesystem locale.
