# Security policy

## Versioni supportate

HiddenIndexEngine e' in sviluppo attivo pre-1.0. Riceve fix di sicurezza solo
l'ultima versione pubblicata sul branch `main`.

| Versione | Supportata |
|----------|------------|
| `main` (0.1.x) | si |
| tag precedenti | no |

## Segnalare una vulnerabilita'

**Non aprire una issue pubblica per una vulnerabilita'.**

Usa il canale privato di GitHub:
[Security Advisories](https://github.com/indecenti/HiddenIndexEngine/security/advisories/new).

Nella segnalazione includi:

- descrizione del problema e impatto;
- passi per riprodurlo (proof of concept se disponibile);
- versione, sistema operativo e versione di Python;
- eventuale proposta di fix.

Tempi indicativi: presa in carico entro 7 giorni, aggiornamento sullo stato entro
30 giorni. Il progetto e' portato avanti da una persona sola nel tempo libero: non
ci sono SLA formali ne' bug bounty.

## Superficie d'attacco rilevante

Aree in cui una segnalazione e' particolarmente utile:

- **`web_platform/server.py`** — server HTTP con autenticazione a cookie firmati
  (HMAC-SHA256), hashing password PBKDF2. Component sperimentale: sessioni,
  path traversal sull'upload dei giochi, autorizzazione degli endpoint admin.
- **Caricamento di scene e cataloghi** (`engine/scene_loader.py`,
  `engine/catalog_manager.py`) — un `scene.json` o un `objects_catalog.json`
  ostile potrebbe tentare path traversal tramite i campi `icon` e `background`,
  o esaurire memoria con dimensioni fuori scala.
- **Import di asset nell'editor** — decodifica di immagini non fidate, scrittura
  fuori dalla directory del gioco.
- **Export web** (`editor/web_exporter.py`) — iniezione di contenuto nel bundle
  HTML/JS generato a partire da dati di scena.
- **Deserializzazione dei salvataggi** (`engine/save_manager.py`).

## Fuori ambito

- Crash o `Traceback` senza conseguenze di sicurezza: apri una issue normale.
- Vulnerabilita' nelle dipendenze upstream (pygame, SDL, numpy, opencv):
  segnalale ai rispettivi progetti. Se serve un pin di versione qui, apri una issue.
- La chiave di firma generata da `web_platform/server.py` al primo avvio finisce
  in `web_platform/config.json`, escluso dal versionamento. Se hai committato per
  errore quel file, ruota il segreto: questo non e' un bug del progetto.
- Attacchi che richiedono accesso fisico alla macchina o privilegi di
  amministratore gia' ottenuti.
