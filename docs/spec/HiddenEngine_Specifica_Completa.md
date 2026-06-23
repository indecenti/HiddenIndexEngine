# HiddenEngine — Specifica Completa del Progetto
### Motore Pygame per Giochi "Cerca e Trova" — Versione 1.0

---

## Indice

1. Visione Generale e Filosofia del Progetto
2. Il Principio Fondamentale — Separazione Motore / Gioco (+ meccanismo di selezione gioco)
3. Struttura delle Cartelle
4. Il Sistema di Scaling Dinamico (+ caching, pan/zoom, resize policy)
5. Il Flusso di Gioco — Schermate, Stati e Transizioni (sequenza precisa, timer, preloading, risultati)
6. Il Sistema Livelli e Scene (+ specifica completa `objects_catalog.json` e `game_config.json`)
7. I Moduli del Motore — Descrizione Dettagliata (+ json_validator, profili qualità)
8. Il Sistema Audio — Thread Separato (architettura audio command dispatcher)
9. La HUD Evoluta (+ troncamento etichette multilingua)
10. Il Menu e le Impostazioni
11. Il Sistema Multilingua
12. Il Sistema di Salvataggio e Punteggio (+ limitazione nota)
13. Sistema Leaderboard, Dashboard e Achievements
14. Il Gioco di Esempio — "La Villa Segreta"
15. L'Editor di Livelli — Specifica Dettagliata (catalogo, posizionamento, workflow)
16. Roadmap di Sviluppo
17. Pacchettizzazione e Distribuzione in EXE
18. Glossario

---

## 1. Visione Generale e Filosofia del Progetto

HiddenEngine è un motore riutilizzabile scritto in Python con Pygame, progettato specificamente per creare giochi del genere **"hidden object"** (cerca e trova). L'obiettivo principale non è costruire un singolo gioco, ma una **piattaforma** che permetta di produrre giochi diversi con il minimo sforzo, semplicemente fornendo nuovi contenuti (immagini, testi, configurazioni) senza mai toccare il codice del motore.

Il motore nasce con una risoluzione di riferimento di **1280×720 pixel** e scala dinamicamente verso qualsiasi altra risoluzione — da piccoli schermi laptop a monitor 4K — mantenendo proporzioni, leggibilità e qualità visiva perfette in ogni condizione.

### Obiettivi del Progetto

- **Riutilizzabilità totale** — lo stesso motore fa girare giochi completamente diversi
- **Semplicità per il creatore di contenuti** — aggiungere un nuovo gioco non richiede programmazione
- **Robustezza tecnica** — scaling impeccabile, audio senza interruzioni, salvataggio affidabile
- **Esperienza di gioco fluida** — animazioni, feedback visivi e sonori curati e reattivi
- **Internazionalizzazione** — supporto multilingua integrato fin dall'inizio

---

## 2. Il Principio Fondamentale — Separazione Motore / Gioco

Tutto il progetto ruota attorno a una regola inviolabile:

> **Il motore non sa nulla del gioco specifico. Il gioco non contiene logica di programmazione.**

Questa separazione si traduce in una distinzione netta tra due layer:

### Layer Motore (ENGINE LAYER)
Contiene tutta la logica, il rendering, la gestione dell'input, l'audio, le animazioni e l'interfaccia. È il codice Python che non viene mai modificato quando si crea un nuovo gioco. Risiede nella cartella `engine/`.

### Layer Gioco (GAME LAYER)
Contiene esclusivamente **dati**: immagini di sfondo, icone degli oggetti, file di configurazione JSON, file di traduzione, musiche e suoni. Non contiene una sola riga di Python. Risiede nella cartella `games/nome_del_gioco/`.

### Il Risultato Pratico

Per creare un gioco completamente nuovo basta:
1. Creare una nuova cartella in `games/`
2. Preparare le immagini e i file JSON
3. Lanciare il motore puntando al nuovo gioco

Nessuna modifica al codice. Nessuna programmazione richiesta.

### Come si Seleziona il Gioco da Lanciare

Il motore accetta il gioco da caricare secondo questa gerarchia di priorità:

1. **Argomento da riga di comando** (priorità massima):
   ```
   python main.py --game villa_segreta
   ```
2. **File `config.ini`** (persistente tra sessioni):
   ```ini
   [engine]
   default_game = villa_segreta
   ```
3. **Menu di selezione gioco all'avvio** — se `config.ini` non specifica alcun gioco, il motore mostra automaticamente la lista di tutti i giochi presenti in `games/`

Questo approccio garantisce flessibilità in fase di sviluppo (CLI) e semplicità per l'utente finale (menu automatico).

---

## 3. Struttura delle Cartelle

```
hiddenengine/
│
├── engine/                        ← Il motore (mai modificare)
│   ├── core.py                    ← Loop principale e gestione stati
│   ├── scaling_manager.py         ← Sistema scaling dinamico
│   ├── scene_loader.py            ← Carica scene da JSON
│   ├── click_detector.py          ← Rilevamento click su oggetti
│   ├── hud_manager.py             ← HUD evoluta
│   ├── hint_system.py             ← Sistema suggerimenti
│   ├── effects_engine.py          ← Animazioni e particelle
│   ├── audio_manager.py           ← Audio su thread separato
│   ├── menu_system.py             ← Menu principale e impostazioni
│   ├── language_manager.py        ← Sistema multilingua
│   ├── save_manager.py            ← Salvataggio e punteggi
│   ├── level_manager.py           ← Gestione livelli e progressione
│   ├── transition_manager.py      ← Transizioni tra schermate
│   └── json_validator.py          ← Validazione JSON con schema al caricamento
│
├── games/                         ← I giochi (solo dati, mai codice)
│   ├── villa_segreta/             ← Gioco di esempio
│   │   ├── game_config.json       ← Configurazione generale del gioco
│   │   ├── objects_catalog.json   ← Catalogo centralizzato oggetti cercabili
│   │   ├── objects/               ← Icone (64×64 PNG) e mask (PNG bianco/nero)
│   │   │   ├── chiave_icon.png
│   │   │   ├── gatto_icon.png
│   │   │   └── libro_mask.png
│   │   ├── strings/               ← Traduzioni
│   │   │   ├── it.json
│   │   │   ├── en.json
│   │   │   └── fr.json
│   │   ├── audio/                 ← Musiche e suoni del gioco
│   │   │   ├── menu_theme.mp3
│   │   │   ├── level1_ambient.mp3
│   │   │   └── sfx/
│   │   ├── ui/                    ← Grafica dell'interfaccia del gioco
│   │   │   ├── menu_background.png
│   │   │   ├── level_select_bg.png
│   │   │   └── hud_frame.png
│   │   └── levels/
│   │       ├── level1_giardino/
│   │       │   ├── level_config.json
│   │       │   ├── scene1_fontana/
│   │       │   │   ├── scene.json
│   │       │   │   └── background.jpg
│   │       │   ├── scene2_pergolato/
│   │       │   │   ├── scene.json
│   │       │   │   └── background.jpg
│   │       │   └── scene3_rimessa/
│   │       │       ├── scene.json
│   │       │       └── background.jpg
│   │       ├── level2_castello/
│   │       │   ├── level_config.json
│   │       │   ├── scene1_cucina/
│   │       │   ├── scene2_torre/
│   │       │   └── scene3_dungeon/
│   │       └── level3_citta/
│   │           └── ...
│
├── editor/                        ← Tool di sviluppo livelli (non incluso nell'EXE)
│   ├── editor_base.py             ← Editor base Pygame (Fase 2)
│   ├── editor_main.py             ← Editor completo Tkinter+Pillow (Fase 5)
│   └── schemas/                   ← Schemi usati dall'editor per la validazione live
│
├── main.py                        ← Punto di avvio del motore
└── config.ini                     ← Configurazione globale (risoluzione, lingua, ecc.)
```

---

## 4. Il Sistema di Scaling Dinamico

Lo scaling è uno dei componenti più critici del motore. Gestito interamente dal modulo `scaling_manager.py`, garantisce che il gioco appaia correttamente su qualsiasi schermo senza che il creatore di contenuti debba preoccuparsene.

### Risoluzione di Riferimento

Tutti i contenuti del gioco (immagini, posizioni degli oggetti, dimensioni della HUD) vengono definiti e misurati sulla risoluzione base di **1280×720 pixel**. Questa è la "verità" del progetto.

### Come Funziona lo Scaling

Al momento dell'avvio, il motore rileva la risoluzione effettiva dello schermo e calcola due fattori di scala:

- **Fattore X** — rapporto tra larghezza reale e 1280
- **Fattore Y** — rapporto tra altezza reale e 720

Per mantenere le proporzioni corrette, viene usato il **fattore minore** dei due (scaling uniforme). Il contenuto viene centrato sullo schermo con bande nere (letterbox) se necessario.

### Cosa Viene Scalato Automaticamente

| Elemento | Scaling |
|---|---|
| Immagini di sfondo | Ridimensionate alla risoluzione corrente |
| Posizione oggetti nascosti | Coordinate moltiplicate per il fattore di scala |
| Aree di click (hit area) | Dimensioni e posizioni scalate |
| Testi della HUD | Font con dimensione scalata |
| Elementi UI (pulsanti, icone) | Scalati proporzionalmente |
| Effetti particellari | Dimensioni e velocità scalate |
| Cursore personalizzato | Scalato |

### Modalità Schermo Supportate

- **Finestra** — a qualsiasi dimensione, con aggiornamento dinamico al ridimensionamento
- **Fullscreen** — usa la risoluzione nativa del monitor
- **Fullscreen Borderless** — finestra massimizzata senza bordi (consigliata)

Il cambio di modalità avviene in tempo reale dalle Impostazioni senza riavviare il gioco.

### Zoom nella Scena

Le scene di gioco possono essere più grandi dello schermo (immagini ad alta risoluzione con molti dettagli). Lo Scaling Manager gestisce anche:

- **Pan** — navigazione nella scena trascinando con il mouse o con le frecce
- **Zoom in/out** — avvicinamento con la rotella del mouse o gesti touch
- **Zoom minimo** — garantisce che l'intera scena sia sempre visibile
- **Zoom massimo** — limite configurabile per non perdere la leggibilità

**Coordinate con Pan/Zoom Attivo**

Quando è attivo lo zoom o il pan, esiste una distinzione critica tra coordinate schermo e coordinate scena. Ogni click del mouse viene trasformato attraverso la pipeline:

```
click_screen → click_viewport → click_scene (coordinate di riferimento 1280×720)
```

Il `click_detector` riceve sempre coordinate di riferimento già trasformate dallo Scaling Manager — non conosce mai lo stato di zoom o pan direttamente. Questo garantisce che le hit area definite nel JSON (in coordinate di riferimento) funzionino correttamente a qualsiasi livello di zoom.

### Caching delle Surface Scalate

Scalare immagini grandi (specialmente mask pixel-perfect) ad ogni frame è proibitivo. Lo Scaling Manager mantiene un **cache LRU** delle Surface già scalate:

- Al caricamento della scena, le mask vengono pre-scalate e messe in cache
- Le Surface in cache vengono invalidate solo se la risoluzione cambia (es. resize finestra)
- Su macchine con poca RAM, il cache ha un limite configurabile (default: 64 MB)

### Resize della Finestra a Runtime

Il resize della finestra è supportato **esclusivamente tra schermate** (menu, selezione livello, schermata risultati) — mai durante una scena attiva con effetti in corso. Quando il giocatore ridimensiona la finestra:

1. Il motore aspetta il frame successivo fuori da uno stato di scena attiva
2. Invalida l'intero cache delle Surface scalate
3. Ricalcola fattori di scala, HUD layout e coordinate hit area
4. Riprende il rendering alla nuova risoluzione

Se il resize avviene durante una scena attiva, viene ignorato e applicato alla schermata successiva. Questo previene artefatti e ricalcoli parziali.

---

## 5. Il Flusso di Gioco — Schermate, Stati e Transizioni

Il motore gestisce il gioco come una **macchina a stati**. In ogni momento il gioco si trova in uno stato preciso, e le transizioni tra stati sono animate e controllate.

### Stati Principali

```
AVVIO
  ↓  (splash screen con logo, 1.5s)
MENU PRINCIPALE
  ↓  [Gioca]           [Impostazioni]        [Esci]
  ↓                          ↓
SELEZIONE LIVELLO        SCHERMATA IMPOSTAZIONI
  ↓  [Livello scelto]
INTRO LIVELLO  (facoltativa — immagine + testo narrativo, skippabile)
  ↓
CARICAMENTO SCENA  (brevissimo se preloading già completato)
  ↓
SCENA ATTIVA  (scena 1 di N)
  ↓  [tutti gli oggetti trovati  —oppure—  timer scaduto]
RISULTATO SCENA
  ↓  [auto-avanzamento dopo 4s, oppure click su "Continua"]
CARICAMENTO SCENA  (brevissimo — preloading già partito durante la scena)
  ↓
SCENA ATTIVA  (scena 2 di N)
  ↓
  ...
SCENA ATTIVA  (scena N di N)
  ↓
FINE LIVELLO  (riepilogo completo, stelle totali, sblocco prossimo livello)
  ↓  [Prossimo Livello / Rivedi / Menu]
SELEZIONE LIVELLO
```

---

### Il Ciclo Completo di una Scena — Sequenza Precisa

Questa è la sequenza esatta di eventi dal momento in cui il giocatore clicca l'ultimo oggetto fino a quando la scena successiva è attiva. I tempi sono valori di default, tutti configurabili.

```
[frame T+0]   Click sul giocatore → click_detector conferma l'ultimo oggetto
[frame T+0]   level_manager aggiorna stato: tutti gli oggetti trovati
[frame T+0]   effects_engine avvia animazione "Trovato!" sull'ultimo oggetto (1.2s)
[frame T+0]   scene_loader inizia preloading della scena successiva (thread separato)
                  — se già in corso (avviato per ≥70% oggetti trovati), non fa nulla
[T+1.2s]      Animazione "Trovato!" completata
[T+1.2s]      effects_engine avvia effetto "Scena Completata" (particelle, flash — 1.5s)
[T+1.2s]      audio_manager riceve comando CROSSFADE verso musica risultato (0.5s)
[T+2.7s]      Effetto completato
[T+2.7s]      transition_manager avvia fade-out (0.4s)
[T+3.1s]      Schermo nero — mostra schermata RISULTATO SCENA
[T+3.1s]      save_manager salva automaticamente il progresso
[T+3.1s+Xs]   Giocatore clicca "Continua" oppure auto-avanzamento dopo 4s
[T+7.1s max]  transition_manager avvia fade-out (0.3s)
[T+7.4s]      Schermo nero
              ├─ se preloading completo → fade-in immediato sulla nuova scena (0.4s)
              └─ se preloading non completo → mostra indicatore caricamento fino a completamento
[T+7.8s]      Nuova SCENA ATTIVA — timer parte, HUD visibile
```

Tutte le animazioni rispettano l'impostazione "Riduci animazioni": le durate vengono dimezzate.

---

### Preloading Asincrono della Scena Successiva

Il preloading non parte quando la scena termina — sarebbe troppo tardi. Part quando uno di questi eventi si verifica per primo durante la scena attiva:

| Condizione | Motivazione |
|---|---|
| Giocatore ha trovato **≥ 70% degli oggetti** | La scena finirà presto |
| Timer al **≤ 40%** del tempo rimasto | Stessa ragione, lato tempo |
| Rimane **1 solo oggetto** da trovare | Certezza: la scena finisce al prossimo click corretto |

Il thread di preloading esegue in background:
1. Legge e valida `scene.json` della scena successiva
2. Carica e scala `background.jpg` alla risoluzione corrente
3. Pre-scala le mask degli oggetti (se presenti) e le mette in cache LRU
4. Costruisce la struttura `PreloadedScene` completa in memoria
5. Imposta un flag `preload_ready = True`

Il main loop non è mai bloccato dal preloading. Se il preloading non è ancora completo quando serve la scena (situazione rara su hardware lento), il motore mostra una schermata di attesa minima con un'animazione semplice — mai uno schermo nero fisso.

---

### Gestione del Timer Scaduto

Il comportamento alla scadenza del timer è **configurabile per livello** tramite il campo `timer_behavior` in `level_config.json`.

**`"timer_behavior": "complete"` (default, consigliato per Easy e Normal)**

La scena si chiude automaticamente con i punti degli oggetti trovati. Gli oggetti non trovati:
1. Vengono evidenziati brevemente sull'immagine per 2 secondi (alone luminoso + label)
2. Compaiono come "non trovati" nella schermata Risultato Scena con icona grigia
3. Non generano punti

Il giocatore avanza sempre. Non si blocca mai. Il punteggio basso produce meno stelle.

**`"timer_behavior": "fail"` (per livelli Hard)**

La scena fallisce. Il motore mostra:
1. Overlay "Tempo scaduto!" con animazione (1.5s)
2. Evidenziazione rapida degli oggetti non trovati (2s)
3. Breve dissolvenza alla schermata "Riprova?" con pulsanti Riprova / Abbandona livello
4. Riprova → ricomincia la stessa scena (timer reset, punteggio scena reset, punteggio scene precedenti mantenuto)

---

### La Schermata Risultato Scena

È la "pausa respiratoria" tra una scena e l'altra. Design principle: **leggibile in 3 secondi senza leggere testo**.

**Layout:**

```
┌─────────────────────────────────────────────┐
│  [Titolo scena]          Scena 1 di 3  ───  │
│                                             │
│   ★ ★ ☆   "Ottimo!"                        │
│                                             │
│   Oggetti trovati:  8 / 8   ✓              │
│   Tempo usato:      1:43 / 2:00            │
│   Punteggio scena:  + 820                   │
│   Punteggio totale: 820                     │
│                                             │
│   [icona] chiave ✓   [icona] gatto ✓  ...  │
│   [icona] libro  ✗   ← non trovato, grigio │
│                                             │
│  [  Rifai  ]           [  Continua  →  ]   │
│             ████████░░░ 4s               │
└─────────────────────────────────────────────┘
```

**Comportamento:**
- La barra di progresso in basso conta 4 secondi, poi avanza automaticamente — il giocatore vede che può aspettare senza fare nulla
- Il punteggio "conta" da 0 al totale in 0.8 secondi (animazione numerica)
- Le stelle appaiono una per una con effetto "pop" in sequenza
- Il messaggio motivazionale dipende dalle stelle: 0→"Meglio la prossima volta!", 1→"Buon lavoro!", 2→"Ottimo!", 3→"Perfetto!" (localizzato)
- Il pulsante "Rifai" è piccolo e secondario — non si vuole incoraggiare il grinding compulsivo
- Il pulsante "Continua" è grande, colorato, posizionato in basso a destra (naturale per il pollice su touch, per il click su mouse)
- Se è l'ultima scena del livello, "Continua" diventa "Vedi risultati livello"

---

### La Schermata Fine Livello

È la ricompensa principale. Più elaborata del risultato scena singola.

**Layout:**

```
┌─────────────────────────────────────────────┐
│         IL GIARDINO ABBANDONATO             │
│              Livello Completato!            │
│                                             │
│   Scena 1 — La Fontana      ★★★   820 pt   │
│   Scena 2 — Il Pergolato    ★★☆   790 pt   │
│   Scena 3 — La Rimessa      ★★★   840 pt   │
│                              ─────────────  │
│              TOTALE          ★★★  2450 pt   │
│                                             │
│   🏆 Nuovo Record!  (precedente: 2100)      │
│                                             │
│   [  Rivedi Livello  ]   [ Prossimo →  ]   │
│             oppure                          │
│   [ 🔒 Livello 2 sbloccato! — animazione ] │
└─────────────────────────────────────────────┘
```

**Comportamento:**
- I punteggi per scena appaiono in sequenza (uno ogni 0.5s) con effetto slide-in
- Il totale appare dopo le scene singole, con animazione numerica
- Se è un nuovo record → banner "Nuovo Record!" con effetto confetti
- Se viene sbloccato il livello successivo → animazione del lucchetto che si apre (1.5s), poi il pulsante "Prossimo" si illumina e diventa cliccabile
- Se il livello successivo era già sbloccato → "Prossimo" è disponibile subito
- Se è l'ultimo livello del gioco → al posto di "Prossimo" appare "Complimenti, hai completato il gioco!"
- Non c'è auto-avanzamento su questa schermata — il giocatore sceglie consapevolmente cosa fare

**Salvataggio:** avviene subito all'inizio di questa schermata, prima che il giocatore veda qualsiasi animazione. Se il gioco viene chiuso durante la schermata Fine Livello, il progresso è già salvato.

---

### Riprendere da una Partita Salvata (mid-level)

Il salvataggio traccia `current_level` e `current_scene`. Alla riapertura del gioco con "Continua":

- Il motore riprende dall'**inizio della scena corrente** (non dal punto esatto in cui si trovava)
- Il punteggio delle scene già completate nel livello corrente viene ripristinato dal salvataggio
- La scena in corso viene ricominciata da zero (timer reset, nessun oggetto pre-trovato)

Questo è deliberato: salvare lo stato esatto di una scena (oggetti trovati, timer, posizione pan/zoom) aggiunge complessità senza un reale beneficio per un casual game. Il giocatore ha perso al massimo 2 minuti di una scena — è accettabile.

---

### Tipi di Transizione — Dettaglio

Il `transition_manager.py` gestisce 4 tipi di transizione, ognuno usato in contesti specifici:

| Tipo | Durata default | Usato per |
|---|---|---|
| **Fade to black** | 0.4s uscita + 0.4s entrata | Passaggio tra schermate diverse (menu → scena, scena → risultato) |
| **Slide orizzontale** | 0.5s | Passaggio tra scene consecutive dello stesso livello (sensazione di "avanzare") |
| **Ripple** | 0.6s | Conferme (es. click su "Abbandona livello") |
| **Flash bianco** | 0.15s | Completamento singolo oggetto (rapido, non interrompe il gioco) |

La transizione tra scene è configurabile nel `level_config.json` per ogni passaggio specifico (vedi §6). Se non specificata, il motore usa Slide orizzontale come default tra scene dello stesso livello.

Tutte le transizioni rispettano "Riduci animazioni": le durate vengono dimezzate e il Ripple viene sostituito con un semplice Fade.

---

### Schermata di Pausa

Accessibile con `ESC` o dal pulsante nella HUD. È un **overlay** sulla scena corrente — la scena rimane visibile ma sfocata (o oscurata al 50%) dietro. Il timer si ferma immediatamente all'apertura della pausa.

Contenuto:
- **Riprendi** — chiude la pausa, riattiva il timer
- **Impostazioni rapide** — volume musica, volume effetti, lingua
- **Abbandona livello** — con dialog di conferma ("Perderai il progresso della scena corrente. Il punteggio delle scene già completate verrà salvato.")

La pausa non è accessibile durante le animazioni di completamento scena o durante le transizioni — evita stati inconsistenti.

---

## 6. Il Sistema Livelli e Scene

### Gerarchia dei Contenuti

La struttura del contenuto è gerarchica su tre livelli:

**Gioco** → contiene più Livelli  
**Livello** → contiene più Scene in sequenza  
**Scena** → una singola immagine con oggetti nascosti da trovare

### Il File `level_config.json`

Ogni livello è descritto da un file di configurazione che il motore legge per organizzare il flusso:

```json
{
  "id": "level1_giardino",
  "name_key": "level1_name",
  "description_key": "level1_desc",
  "thumbnail": "thumbnail.jpg",
  "unlock_after": null,
  "music": "audio/garden_ambient.mp3",
  "intro_image": "assets/intro_card.png",
  "intro_text_key": "level1_intro",
  "difficulty": "easy",
  "timer_behavior": "complete",
  "star_thresholds": [500, 1200, 2000],
  "scenes": [
    {
      "id": "scene1_fontana",
      "order": 1,
      "time_limit": 120,
      "transition_out": "slide_left"
    },
    {
      "id": "scene2_pergolato",
      "order": 2,
      "time_limit": 90,
      "transition_out": "slide_left"
    },
    {
      "id": "scene3_rimessa",
      "order": 3,
      "time_limit": 60,
      "transition_out": "fade"
    }
  ],
  "completion_reward": "unlock_level2"
}
```

**Campi configurabili:**

| Campo | Valori | Descrizione |
|---|---|---|
| `timer_behavior` | `"complete"` / `"fail"` | Cosa succede quando il timer scade (vedi §5) |
| `transition_out` | `"fade"` / `"slide_left"` / `"slide_right"` | Transizione in uscita dalla scena. Default: `"slide_left"` |

### Il File `scene.json`

Ogni scena ha il proprio file JSON che descrive il pool di oggetti nascosti e quanti ne servono per completarla.

#### Pool vs Oggetti Richiesti

Questa distinzione è fondamentale per la rigiocabilità:

- **Pool** (`objects`) — tutti gli oggetti posizionati nella scena dal creatore. Possono essere decine.
- **Oggetti da trovare** (`objects_to_show`) — quanti oggetti vengono estratti dal pool e mostrati al giocatore per questa run. Deve essere ≤ dimensione del pool.

Ad ogni run della scena, il motore seleziona `objects_to_show` oggetti dal pool. Gli oggetti mostrati cambiano tra una run e l'altra, rendendo la scena rigiocabile anche per chi la conosce già.

Se `objects_to_show` è omesso o uguale alla dimensione del pool, vengono mostrati tutti gli oggetti — comportamento classico, nessuna randomizzazione.

#### Oggetti Fissi e Oggetti Casuali

Ogni oggetto del pool può essere marcato come `"always_show": true`: viene sempre incluso nella selezione, indipendentemente dall'estrazione casuale. Gli oggetti rimanenti fino al conteggio `objects_to_show` vengono scelti casualmente dagli altri.

**Esempio:** pool di 25 oggetti, `objects_to_show: 10`, 3 oggetti `always_show: true`.
Ogni run → i 3 fissi + 7 estratti casualmente tra i 22 rimanenti.

```json
{
  "id": "scene1_fontana",
  "name_key": "scene1_fontana_name",
  "background": "background.jpg",
  "background_scale": 1.5,
  "objects_to_show": 8,
  "objects": [
    {
      "catalog_id": "chiave",
      "x": 342, "y": 187,
      "detection_type": "circle",
      "radius": 25,
      "hint_delay": 30,
      "layer": "objects_high",
      "always_show": true
    },
    {
      "catalog_id": "gatto",
      "x": 120, "y": 400,
      "detection_type": "rect",
      "width": 80, "height": 60,
      "hint_delay": 45,
      "layer": "objects_mid",
      "always_show": false
    }
  ]
}
```

#### Validazioni al Caricamento

Il `json_validator` verifica:
- `objects_to_show` ≤ numero totale di oggetti nel pool
- Numero oggetti `always_show: true` ≤ `objects_to_show`
- Se una delle due condizioni è violata, errore chiaro con valori attuali: `"objects_to_show (8) è maggiore del pool (5). Aggiungi oggetti o abbassa objects_to_show."`

---

### Il File `objects_catalog.json` — Specifica Completa

È il file che il creatore compila **prima** di creare qualsiasi scena. Definisce ogni oggetto cercabile del gioco una sola volta. Risiede in `games/nome_gioco/objects_catalog.json`.

#### Tabella dei Campi

| Campo | Tipo | Obbligo | Descrizione |
|---|---|---|---|
| `id` | stringa | **obbligatorio** | Identificatore univoco nel gioco. Usato come `catalog_id` nelle scene. Solo lettere minuscole, numeri, underscore. |
| `label_key` | stringa | **obbligatorio** | Chiave nel file `strings/lingua.json`. Il testo localizzato risolto da questa chiave appare nella HUD e nei tooltip. |
| `icon` | stringa (path) | **obbligatorio** | Path relativo all'icona PNG, da `games/nome_gioco/`. Dimensione consigliata: 64×64 px con trasparenza. Scalata automaticamente dalla HUD. |
| `default_detection` | enum | **obbligatorio** | Tipo di hit area predefinito: `"circle"`, `"rect"`, o `"mask"`. Può essere sovrascritto in ogni `scene.json`. |
| `default_radius` | intero (px) | se `circle` | Raggio dell'hit area in coordinate di riferimento 1280×720. |
| `default_width` | intero (px) | se `rect` | Larghezza dell'hit area. |
| `default_height` | intero (px) | se `rect` | Altezza dell'hit area. |
| `default_mask` | stringa (path) | se `mask` | Path relativo all'immagine maschera PNG (bianco=attivo, nero=trasparente). |
| `default_hint_delay` | intero (sec) | facoltativo | Secondi di inattività prima che scatti il suggerimento automatico. Default: `30`. Sovrascrivibile per ogni istanza in `scene.json`. |
| `tags` | array di stringhe | facoltativo | Etichette libere per filtrare nel pannello catalogo dell'editor. Non usate dal motore. |

#### Esempio Completo

```json
{
  "objects": [
    {
      "id": "chiave",
      "label_key": "obj_chiave",
      "icon": "objects/chiave_icon.png",
      "default_detection": "circle",
      "default_radius": 25,
      "default_hint_delay": 30,
      "tags": ["piccolo", "metallo"]
    },
    {
      "id": "gatto",
      "label_key": "obj_gatto",
      "icon": "objects/gatto_icon.png",
      "default_detection": "rect",
      "default_width": 80,
      "default_height": 60,
      "default_hint_delay": 45,
      "tags": ["animale", "grande"]
    },
    {
      "id": "libro",
      "label_key": "obj_libro",
      "icon": "objects/libro_icon.png",
      "default_detection": "mask",
      "default_mask": "objects/libro_mask.png",
      "default_hint_delay": 35,
      "tags": ["oggetto"]
    },
    {
      "id": "candela",
      "label_key": "obj_candela",
      "icon": "objects/candela_icon.png",
      "default_detection": "circle",
      "default_radius": 18,
      "default_hint_delay": 40,
      "tags": ["piccolo", "luce"]
    }
  ]
}
```

#### Come Viene Usato dai Moduli

- **`scene_loader`** — quando carica un `scene.json`, risolve ogni `catalog_id` nel catalogo per ottenere `icon`, `label_key` e i default da usare se la scena non li sovrascrive
- **`hud_manager`** — usa `icon` e `label_key` per costruire la lista oggetti da trovare
- **`hint_system`** — usa `default_hint_delay` come fallback se la scena non specifica `hint_delay` per quell'istanza
- **`json_validator`** — verifica che ogni `catalog_id` usato nelle scene esista nel catalogo

Se un `catalog_id` in una scena non corrisponde a nessun oggetto del catalogo, il validator blocca il caricamento con errore esplicito: `"catalog_id 'candlestick' non trovato in objects_catalog.json. Hai inteso 'candela'?"`.

---

### Il File `game_config.json` — Specifica Completa

È il file di configurazione globale del gioco. Risiede in `games/nome_gioco/game_config.json`. Viene letto una sola volta all'avvio del gioco e non cambia durante la sessione.

Raccoglie in un unico posto tutte le personalizzazioni del gioco: identità visiva, UI, achievements, layer personalizzati. È il file che distingue un gioco da un altro a livello di motore.

#### Esempio Completo — "La Villa Segreta"

```json
{
  "game_id": "villa_segreta",
  "version": "1.0",
  "title_key": "game_title",

  "identity": {
    "logo": "ui/logo.png",
    "icon": "ui/icon.ico",
    "splash_background": "ui/splash.png"
  },

  "menu": {
    "background": "ui/menu_background.png",
    "music": "audio/menu_theme.mp3",
    "level_select_background": "ui/level_select_bg.png"
  },

  "hud": {
    "frame": "ui/hud_frame.png",
    "font": "ui/hud_font.ttf",
    "text_color": [255, 255, 220],
    "accent_color": [255, 200, 50],
    "position": "bottom"
  },

  "default_language": "it",
  "fallback_language": "en",

  "layer_hint_intensity": {
    "objects_low":  1.5,
    "objects_mid":  1.0,
    "objects_high": 0.7,
    "overlay":      0.0
  },

  "custom_layers": [
    {
      "id": "dietro_albero",
      "z_value": 15,
      "label": "Dietro all'albero",
      "hint_intensity": 1.8
    }
  ],

  "achievements": [
    {
      "id": "no_hints_giardino",
      "name_key": "ach_no_hints_giardino",
      "description_key": "ach_no_hints_giardino_desc",
      "icon": "achievements/no_hints.png",
      "condition": "level_no_hints",
      "params": { "level_id": "level1_giardino" }
    },
    {
      "id": "speed_giardino",
      "name_key": "ach_speed_giardino",
      "description_key": "ach_speed_giardino_desc",
      "icon": "achievements/speed.png",
      "condition": "level_under_time",
      "params": { "level_id": "level1_giardino", "max_seconds": 180 }
    },
    {
      "id": "sharp_eye_giardino",
      "name_key": "ach_sharp_eye_giardino",
      "description_key": "ach_sharp_eye_giardino_desc",
      "icon": "achievements/eye.png",
      "condition": "level_max_wrong_clicks",
      "params": { "level_id": "level1_giardino", "max_wrong": 3 }
    },
    {
      "id": "game_complete",
      "name_key": "ach_game_complete",
      "description_key": "ach_game_complete_desc",
      "icon": "achievements/trophy.png",
      "condition": "all_levels_complete",
      "params": {}
    },
    {
      "id": "all_stars",
      "name_key": "ach_all_stars",
      "description_key": "ach_all_stars_desc",
      "icon": "achievements/stars.png",
      "condition": "all_levels_three_stars",
      "params": {}
    }
  ]
}
```

#### Tabella dei Campi

| Sezione / Campo | Obbligo | Descrizione |
|---|---|---|
| `game_id` | **obbligatorio** | Identificatore univoco del gioco. Usato come nome del file di salvataggio (`save_villa_segreta.json`) e come cartella in `%APPDATA%`. |
| `version` | **obbligatorio** | Versione del gioco — usata per gestire migrazioni del file di salvataggio. |
| `title_key` | **obbligatorio** | Chiave del titolo del gioco. Risolto nella lingua corrente per la finestra e la splash screen. |
| `identity.logo` | facoltativo | Logo PNG mostrato nel menu principale. Se assente, il motore usa il `title_key` come testo. |
| `identity.icon` | facoltativo | Icona `.ico` per la finestra e per l'EXE compilato. |
| `identity.splash_background` | facoltativo | Sfondo della splash screen iniziale. Se assente, schermo nero. |
| `menu.background` | **obbligatorio** | Sfondo del menu principale. |
| `menu.music` | facoltativo | Musica del menu principale. Se assente, nessuna musica nel menu. |
| `menu.level_select_background` | facoltativo | Sfondo della schermata selezione livello. Se assente, usa `menu.background`. |
| `hud.frame` | facoltativo | PNG sovrapposto alla HUD per personalizzarne l'aspetto grafico. |
| `hud.font` | facoltativo | Font `.ttf` per i testi della HUD. Se assente, usa il font di sistema. |
| `hud.text_color` | facoltativo | Colore testo HUD in RGB. Default: `[255, 255, 255]`. |
| `hud.accent_color` | facoltativo | Colore accento (stelle, timer critico) in RGB. Default: `[255, 200, 50]`. |
| `hud.position` | facoltativo | `"bottom"` o `"top"`. Default: `"bottom"`. |
| `default_language` | **obbligatorio** | Lingua usata al primo avvio. Deve corrispondere a un file in `strings/`. |
| `fallback_language` | facoltativo | Lingua di fallback per chiavi mancanti. Default: `"en"`. |
| `layer_hint_intensity` | facoltativo | Mappa layer → moltiplicatore intensità hint. Se assente, tutti i layer usano `1.0`. |
| `custom_layers` | facoltativo | Array di layer aggiuntivi oltre ai cinque predefiniti. Ogni layer ha `id`, `z_value`, `label`, `hint_intensity`. |
| `achievements` | facoltativo | Array degli achievement del gioco. Se assente, nessun achievement. |

#### Campi Obbligatori Minimi

Un `game_config.json` funzionante al minimo assoluto:

```json
{
  "game_id": "mio_gioco",
  "version": "1.0",
  "title_key": "game_title",
  "menu": {
    "background": "ui/menu_background.png"
  },
  "default_language": "it"
}
```

Il motore usa valori di default per tutto il resto. Questo è sufficiente per far girare il gioco con il tema visivo di default del motore.

---

### Tipi di Rilevamento Click

Il motore supporta tre modalità di rilevamento per adattarsi a forme di oggetti diverse:

| Tipo | Descrizione | Quando usarlo |
|---|---|---|
| `circle` | Cerchio con raggio definito | Oggetti piccoli e rotondi |
| `rect` | Rettangolo con larghezza e altezza | Oggetti rettangolari |
| `mask` | Maschera pixel-perfect da immagine | Oggetti di forma irregolare |

### Progressione e Sblocco Livelli

Il motore calcola automaticamente quali livelli sono disponibili basandosi sul campo `unlock_after` nel `level_config.json`. I livelli bloccati sono visibili nella selezione ma non selezionabili, con indicazione visiva del requisito per sbloccarli.

### Punteggio Cumulativo tra Scene

Il punteggio si accumula lungo tutte le scene di un livello. Il punteggio base per oggetto trovato è sempre lo stesso indipendentemente da quanti oggetti erano nel pool — trovare 8 oggetti su un pool da 8 vale quanto trovare 8 su un pool da 25.

| Azione | Punti |
|---|---|
| Oggetto trovato | +100 |
| Click errato | −15 |
| Bonus tempo rimasto | +1 per secondo |
| Livello completato senza hint | +500 |
| Completamento rapido (<50% del tempo) | ×1.5 moltiplicatore |

A fine livello il motore calcola le stelle (1–3) in base al punteggio totale confrontandolo con le soglie in `level_config.json`. Le soglie vanno calibrate tenendo conto di `objects_to_show` — un livello con 5 oggetti per scena produce meno punti base di uno con 15.

---

## 7. I Moduli del Motore — Descrizione Dettagliata

### `core.py` — Il Cuore del Motore

È il punto di ingresso e il coordinatore di tutti gli altri moduli. Gestisce:
- Il game loop principale (target: 60 FPS)
- L'istanziazione e il collegamento di tutti i moduli
- La ricezione e distribuzione degli eventi (input, window resize, ecc.)
- Il delta time per animazioni indipendenti dal frame rate

### `scaling_manager.py` — Scaling Dinamico

Descritto in dettaglio nella sezione 4. Fornisce agli altri moduli le funzioni di conversione tra coordinate di riferimento (1280×720) e coordinate reali dello schermo corrente.

### `scene_loader.py` — Caricamento Scene

Legge i file JSON di gioco e costruisce in memoria la struttura della scena corrente: sfondo, lista oggetti, metadati. Gestisce il preloading asincrono della scena successiva per eliminare i tempi di attesa durante le transizioni.

**Selezione degli oggetti da mostrare:**

Prima di restituire la struttura scena al `level_manager`, applica la logica di selezione pool:

```
1. Separa gli oggetti in: always_show=true (fissi) e always_show=false (casuali)
2. Se len(fissi) > objects_to_show → errore di configurazione (segnalato da json_validator)
3. Mescola la lista casuali con random.shuffle()
4. Pesca (objects_to_show - len(fissi)) oggetti dalla lista casuale
5. Unisce fissi + pescati → lista finale degli oggetti attivi per questa run
6. Solo questa lista viene passata al level_manager e mostrata nella HUD
```

Gli oggetti del pool non selezionati esistono ancora nel `scene.json` ma non sono mai caricati in memoria per la run corrente — non sono rilevabili dal click detector, non appaiono nella HUD.

Il seed della selezione casuale **non viene salvato**: ogni volta che il giocatore rifà una scena ottiene una combinazione diversa.

### `click_detector.py` — Rilevamento Click

Riceve le coordinate del click dal core, le converte tramite lo Scaling Manager, e verifica se il click cade su un oggetto **attivo** (selezionato per questa run, non ancora trovato). Restituisce l'oggetto colpito oppure `null` per click errato. Gestisce tutti e tre i tipi di rilevamento (circle, rect, mask) con priorità z-index.

### `level_manager.py` — Gestione Livelli

È il coordinatore centrale del flusso di gioco. Conosce l'intera struttura del gioco e prende tutte le decisioni di avanzamento.

**Stato interno mantenuto:**
- Livello corrente e lista scene ordinate per `order`
- Indice della scena attiva
- Punteggio accumulato per ogni scena già completata nel livello corrente
- Lista oggetti trovati nella scena attiva
- Stato del timer (tempo rimasto, attivo/pausa/scaduto)

**Decisioni di avanzamento:**

Quando riceve l'evento `SCENE_COMPLETE` (da un oggetto trovato o da timer scaduto):
1. Calcola il punteggio finale della scena (oggetti trovati × 100, bonus tempo, penalty errori)
2. Aggiorna il punteggio accumulato del livello
3. Controlla se esistono altre scene con `order > corrente`
   - Sì → emette `ADVANCE_TO_NEXT_SCENE` con l'indice della prossima
   - No → emette `LEVEL_COMPLETE` con il punteggio totale
4. Calcola le stelle per la scena (confronto con soglie — non usa le soglie del livello, che sono per il totale)

**Decisione sul preloading:**
Ogni frame, il `level_manager` monitora due condizioni e, quando una scatta per la prima volta, notifica lo `scene_loader` di iniziare il preloading della scena successiva:
- `oggetti_trovati / totale_oggetti >= 0.70`
- `timer_rimasto / time_limit <= 0.40`

Se la scena corrente è l'ultima del livello, non viene avviato nessun preloading.

### `hint_system.py` — Sistema Suggerimenti

Traccia il tempo dall'ultimo click corretto. Se supera il `hint_delay` configurato nella scena, attiva un suggerimento visivo sull'oggetto ancora da trovare. Il giocatore può anche richiedere hint manualmente premendo un pulsante nella HUD, con penalità di punteggio.

Il suggerimento può essere di tre intensità crescenti:
1. **Debole** — alone luminoso pulsante di piccole dimensioni
2. **Medio** — cerchio animato più visibile con freccia direzionale
3. **Forte** — evidenziazione diretta dell'area con nome dell'oggetto

### `effects_engine.py` — Animazioni e Particelle

Gestisce tutti gli effetti visivi del gioco:

- **Trovato!** — cerchio verde che si espande dal punto di click + particelle dorate + icona dell'oggetto che vola verso la lista nella HUD
- **Sbagliato!** — flash rosso nel punto di click + leggero shake dello schermo
- **Suggerimento** — alone pulsante sull'oggetto
- **Completamento livello** — esplosione di particelle colorate + testo animato
- **Stella guadagnata** — animazione stella che appare nella HUD
- **Transizioni** — gestione coordinata con `transition_manager.py`

Tutti gli effetti rispettano l'impostazione "Riduci animazioni" nelle opzioni.

**Limitazioni Tecniche e Impostazioni Qualità**

Pygame esegue il rendering in software (CPU), senza accelerazione GPU. Gli effetti di tipo bloom e glow richiedono alpha-blending su Surface multiple — costosi su hardware datato. Per questo il motore definisce tre profili di qualità selezionabili nelle Impostazioni:

| Qualità | Effetti Attivi | Hardware Target |
|---|---|---|
| **Alta** | Particelle, bloom leggero, shake, flash | PC moderni (2018+) |
| **Media** | Particelle ridotte, niente bloom, shake | Laptop datati |
| **Bassa** | Solo flash colore, niente particelle | Hardware molto vecchio |

L'obiettivo è mantenere 60 FPS stabili su tutti i profili. Se il motore rileva un frame rate medio sotto i 45 FPS per più di 5 secondi, suggerisce all'utente di abbassare la qualità. Non si eseguono mai downgrade automatici silenziosi.

### `scene_loader.py` — Caricamento Scene (aggiornamento)

Oltre al caricamento normale, gestisce il **preloading asincrono** tramite `threading.Thread`:

```
scene_loader.preload(scene_id)   ← chiamato da level_manager
    → thread secondario:
        1. legge e valida scene.json
        2. carica background.jpg in una Surface temporanea
        3. scala la Surface alla risoluzione corrente
        4. pre-scala le mask e le mette in cache LRU
        5. costruisce PreloadedScene completa
        6. imposta preload_ready = True
    → thread principale:
        - controlla preload_ready ad ogni transizione
        - se True: usa la PreloadedScene già pronta (veloce)
        - se False: mostra indicatore di attesa, aspetta il completamento
```

Il thread di preloading non usa `pygame` — lavora solo con `PIL/Pillow` per il resize delle immagini, poi passa il risultato al main thread che crea la Surface Pygame. Questo evita problemi di thread-safety con SDL.

### `transition_manager.py` — Transizioni

Gestisce le animazioni di passaggio tra stati del gioco. Ogni transizione ha una durata configurabile e può essere interrotta anticipatamente.

**Interfaccia usata da `core.py`:**

```python
transition_manager.start(type, duration, on_midpoint_callback)
# on_midpoint_callback viene chiamato quando lo schermo è completamente nero/bianco
# — è il momento in cui core.py scambia la scena attiva senza che il giocatore veda nulla
```

Il `transition_manager` è l'unico responsabile del "momento del cambio": il `core.py` non scambia mai lo stato del gioco fuori da un midpoint di transizione, garantendo che il giocatore non veda mai frame con contenuti misti tra due scene.

### `json_validator.py` — Validazione JSON con Schema

Ogni volta che il motore legge un file JSON (scene, livello, configurazione), lo valida contro lo schema corrispondente prima di usarlo. Se la validazione fallisce, il motore mostra un messaggio di errore chiaro indicando file, campo e tipo di errore atteso — mai un crash criptico.

Gli schemi si trovano in `engine/schemas/`:
- `scene_schema.json` — valida ogni `scene.json`
- `level_config_schema.json` — valida ogni `level_config.json`
- `game_config_schema.json` — valida `game_config.json`

**Esempio di errore prodotto:**
```
[ERRORE] games/villa_segreta/levels/level1/scene1/scene.json
  Oggetto "chiave": campo "radious" non riconosciuto. Intendevi "radius"?
  Oggetto "gatto": campo "detection_type" deve essere "circle", "rect" o "mask".
Il motore non può procedere. Correggi i file indicati.
```

---

## 8. Il Sistema Audio — Thread Separato

L'audio è uno dei componenti più delicati di un gioco. Un lag nel render non deve mai interrompere la musica di sottofondo, né ritardare un effetto sonoro. Per questo motivo l'intero sistema audio gira su un **thread Python dedicato**, completamente indipendente dal game loop principale.

### Architettura del Thread Audio

Il thread audio gira in parallelo al game loop. I due thread comunicano attraverso una **coda di messaggi thread-safe** (`queue.Queue`): il game loop inserisce comandi nella coda (es. "riproduci effetto click", "cambia musica di sottofondo"), e il thread audio li consuma aggiornando il proprio stato interno.

**Importante — Separazione delle Responsabilità**

`pygame.mixer` non è thread-safe. Chiamarlo da un thread secondario causa comportamenti imprevedibili su Windows. Per questo motivo:

- Il **thread audio** gestisce solo la logica: legge la coda, decide cosa riprodurre, calcola i volumi del crossfade, aggiorna lo stato interno
- Le **chiamate effettive a `pygame.mixer`** vengono eseguite esclusivamente nel game loop principale, una volta per frame, consumando i risultati preparati dal thread audio

Questo pattern è spesso chiamato *audio command dispatcher*: il thread è un pianificatore, non un esecutore. Il vantaggio di latenza è leggermente ridotto rispetto a un thread completamente autonomo, ma la stabilità su tutte le piattaforme è garantita.

### Responsabilità del Thread Audio

**Musica di sottofondo (MP3)**
- Riproduzione continua in loop di file MP3
- Crossfade fluido tra tracce diverse (durata configurabile, default 1.5 secondi)
- La musica cambia automaticamente quando si entra in un nuovo livello
- Abbassamento automatico del volume durante dialoghi o cutscene
- Dissolvenza in uscita quando il gioco viene messo in pausa

**Effetti Sonori (WAV/OGG)**
- Riproduzione immediata con latenza minima
- Più effetti possono sovrapporsi contemporaneamente (canali multipli)
- Priorità configurabile per effetti critici (es. "trovato!" ha priorità alta)
- Volume degli effetti indipendente dal volume della musica

**Coda di Messaggi**
Tutti i messaggi supportati dal sistema audio:

| Messaggio | Parametri | Descrizione |
|---|---|---|
| `PLAY_MUSIC` | file, loop, fade_in | Avvia musica di sottofondo |
| `STOP_MUSIC` | fade_out | Ferma la musica con dissolvenza |
| `CROSSFADE` | file, duration | Transizione fluida tra due tracce |
| `PLAY_SFX` | file, volume, priority | Riproduce un effetto sonoro |
| `SET_MUSIC_VOLUME` | volume (0.0–1.0) | Cambia volume musica |
| `SET_SFX_VOLUME` | volume (0.0–1.0) | Cambia volume effetti |
| `PAUSE_MUSIC` | — | Pausa la musica |
| `RESUME_MUSIC` | — | Riprende la musica |
| `DUCK_MUSIC` | level, duration | Abbassa temporaneamente il volume |

### Gestione degli Errori Audio

Il thread audio non causa crash al gioco in caso di problemi. Se un file audio non viene trovato o non può essere decodificato, il thread registra l'errore in un log interno e continua senza interrompere il gioco. Il giocatore non vede mai messaggi di errore legati all'audio.

### Formati Supportati

- **MP3** — per musiche di sottofondo (streaming, non caricamento completo in memoria)
- **OGG Vorbis** — alternativa consigliata a MP3 per migliore compatibilità con Pygame
- **WAV** — per effetti sonori (caricamento completo in memoria per latenza minima)

### Impostazioni Audio

Le impostazioni sono persistenti (salvate su file) e accessibili in qualsiasi momento:
- Volume musica (slider 0–100%)
- Volume effetti sonori (slider 0–100%)
- Abilita/Disabilita musica
- Abilita/Disabilita effetti sonori

---

## 9. La HUD Evoluta

La HUD (Heads-Up Display) è l'interfaccia che il giocatore vede durante il gioco. È progettata per essere **informativa ma non invasiva** — occupa spazio minimo e non distrae dall'immagine di scena.

### Layout della HUD

La HUD è posizionata in una barra orizzontale nella parte inferiore dello schermo (o superiore, configurabile). È composta da quattro zone:

**Zona Sinistra — Lista Oggetti**  
Mostra le icone degli oggetti da trovare nella scena corrente. Gli oggetti trovati vengono barrati o mostrano un checkmark animato. Il nome dell'oggetto appare in tooltip al passaggio del mouse sull'icona.

Le etichette degli oggetti sono soggette a troncamento automatico per gestire lingue con nomi lunghi (tedesco, finlandese, ecc.). Se il testo supera la larghezza dell'icona, viene troncato con ellipsis (`…`) e il testo completo appare in tooltip al hover. Questo comportamento è attivo per tutte le lingue — non solo quelle note per i nomi lunghi.

**Zona Centrale — Timer**  
Countdown del tempo rimanente per la scena. Diventa arancione quando rimane il 30% del tempo, rosso quando rimane il 15%. Animazione di pulsazione quando il tempo è critico. Se il gioco è configurato senza limite di tempo, mostra uno stopwatch in modalità conteggio.

**Zona Destra — Punteggio e Stelle**  
Mostra il punteggio corrente con animazione di incremento quando si trova un oggetto. Mostra le stelle accumulate nel livello corrente. Include il pulsante Pausa e il pulsante Hint.

**Zona Superiore Discreta — Progresso Livello**  
Una barra di progresso sottile che indica quante scene del livello sono state completate (es. scena 2 di 3).

### Comportamento Adattivo della HUD

La HUD si adatta al contesto:

- **Durante il gioco normale** — visibile e completa
- **Quando il giocatore non interagisce per 5 secondi** — si riduce in trasparenza (alpha 60%) per non coprire la scena
- **Al movimento del mouse** — torna immediatamente opaca
- **Modalità "Solo Scena"** (attivabile) — la HUD si nasconde quasi completamente, rimane solo un piccolo indicatore di oggetti trovati

### Animazioni della HUD

Ogni interazione con la HUD ha un'animazione appropriata:

- **Oggetto trovato** — l'icona nella lista lampeggia di verde, poi mostra un checkmark, e il punteggio aumenta con animazione numerica
- **Click errato** — il contatore errori nella HUD trema brevemente
- **Hint usato** — il pulsante hint mostra una penalità di punteggio animata
- **Nuova stella** — la stella appare nella HUD con effetto "pop" e particelle dorate
- **Tempo quasi scaduto** — il timer pulsa e la barra progresso diventa rossa

### Personalizzazione della HUD da parte del Gioco

Il gioco può personalizzare l'aspetto della HUD fornendo nella cartella `ui/`:
- `hud_frame.png` — cornice grafica della HUD (sovrapposta ai controlli standard)
- `hud_font.ttf` — font personalizzato per i testi della HUD
- Colori personalizzati nel `game_config.json` (colore testo, colore accento)

Se questi file non sono presenti, il motore usa il tema di default.

---

## 10. Il Menu e le Impostazioni

### Menu Principale

Il menu principale è la prima schermata che il giocatore vede dopo la splash screen. È composto da:

- **Sfondo** — l'immagine `menu_background.png` del gioco, con parallax leggero al movimento del mouse
- **Logo del gioco** — centrato in alto
- **Pulsanti principali** — Gioca, Continua (se esiste un salvataggio), Impostazioni, Esci
- **Credits** — piccolo link in basso

Il layout del menu è generato automaticamente dal motore. Il gioco fornisce solo lo sfondo e il logo.

### Schermata Selezione Livello

Generata automaticamente leggendo tutti i `level_config.json` presenti nella cartella `levels/`. Per ogni livello mostra:

- Immagine thumbnail
- Nome del livello (localizzato)
- Stelle ottenute (0–3), grigie se non ancora giocato
- Lucchetto se non sbloccato, con testo del requisito
- Badge "NUOVO" se mai giocato prima
- Punteggio massimo ottenuto

### Schermata Impostazioni

Accessibile dal menu principale e dal menu di pausa. Organizzata in tre sezioni:

**Sezione Video**
- Risoluzione schermo (lista delle risoluzioni disponibili rilevate automaticamente)
- Modalità schermo (Finestra / Fullscreen / Fullscreen Borderless)
- Qualità rendering (Alta / Media / Bassa) — influenza effetti particelle e animazioni
- Riduci animazioni (toggle) — per accessibilità

**Sezione Audio**
- Volume musica (slider)
- Volume effetti (slider)
- Abilita musica (toggle)
- Abilita effetti (toggle)

**Sezione Gioco**
- Lingua (lista delle lingue disponibili nel gioco corrente)
- Difficoltà hint (Automatico / Solo manuale / Disabilitato)
- Mostra timer (toggle)
- Mostra punteggio (toggle)

Tutte le impostazioni vengono salvate immediatamente e applicate in tempo reale, senza richiedere riavvio.

---

## 11. Il Sistema Multilingua

Il sistema multilingua è integrato nel motore fin dall'inizio e si basa su chiavi di testo — mai stringhe hardcoded nel codice.

### Principio di Funzionamento

Ogni testo visibile nel gioco è identificato da una **chiave** (es. `"level1_name"`, `"obj_chiave"`, `"btn_play"`). Il modulo `language_manager.py` mantiene in memoria il dizionario della lingua corrente e risolve le chiavi in testi localizzati.

Il motore ha le proprie chiavi per i testi dell'interfaccia generica (pulsanti del menu, messaggi di pausa, ecc.). Il gioco aggiunge le proprie chiavi per contenuti specifici (nomi livelli, nomi oggetti, testi narrativi).

### Struttura dei File di Traduzione

Ogni lingua è un file JSON nella cartella `strings/` del gioco:

```json
{
  "game_title": "La Villa Segreta",
  "level1_name": "Il Giardino Abbandonato",
  "level1_desc": "Un giardino antico pieno di segreti nascosti tra le piante.",
  "level1_intro": "La villa era abbandonata da decenni...",
  "obj_chiave": "La Chiave Arrugginita",
  "obj_gatto": "Il Gatto Nero",
  "obj_libro": "Il Libro Antico"
}
```

Il file del motore contiene invece chiavi generiche come:
```json
{
  "btn_play": "Gioca",
  "btn_settings": "Impostazioni",
  "btn_exit": "Esci",
  "hud_found": "Trovato!",
  "hud_wrong": "Riprova!",
  "pause_title": "Pausa"
}
```

### Rilevamento Automatico Lingue Disponibili

Il `language_manager` scansiona la cartella `strings/` del gioco e costruisce automaticamente la lista delle lingue disponibili. Il menu Impostazioni mostra solo le lingue per cui esiste il file di traduzione.

### Cambio Lingua in Tempo Reale

Il cambio di lingua avviene istantaneamente senza ricaricare la scena. Tutti i testi vengono aggiornati al volo. Le immagini che contengono testo (es. pannelli narrativi) possono avere versioni per lingua diverse nella cartella `assets/localized/`.

### Gestione Chiavi Mancanti

Se una chiave non esiste nel file della lingua corrente, il motore cerca nella lingua di fallback (default: inglese). Se non esiste nemmeno lì, mostra la chiave stessa come testo, in modo da non causare crash e rendere immediatamente evidente cosa manca.

---

## 12. Il Sistema di Salvataggio e Punteggio

### Cosa Viene Salvato

Il modulo `save_manager.py` gestisce un file di salvataggio per gioco (non per livello). Il file è in formato JSON e contiene:

- Progresso per ogni livello (completato / stelle ottenute / punteggio massimo)
- Progresso per ogni scena di ogni livello
- Livello corrente (per il tasto "Continua")
- Scena corrente all'interno del livello
- Impostazioni utente (volume, lingua, modalità schermo, ecc.)
- Statistiche generali (tempo totale di gioco, click totali, click corretti, ecc.)

### Struttura del File di Salvataggio

```
save_villa_segreta.json
{
  "version": "1.0",
  "last_played": "2025-04-15T11:30:00",
  "current_level": "level2_castello",
  "current_scene": "scene1_cucina",
  "levels": {
    "level1_giardino": {
      "completed": true,
      "stars": 3,
      "best_score": 2450,
      "scenes": {
        "scene1_fontana":   { "completed": true, "best_score": 820 },
        "scene2_pergolato": { "completed": true, "best_score": 790 },
        "scene3_rimessa":   { "completed": true, "best_score": 840 }
      }
    },
    "level2_castello": {
      "completed": false,
      "stars": 0,
      "best_score": 0,
      "scenes": {}
    }
  },
  "settings": {
    "language": "it",
    "music_volume": 0.7,
    "sfx_volume": 0.9,
    "screen_mode": "fullscreen_borderless"
  },
  "stats": {
    "total_play_time_seconds": 3640,
    "total_clicks": 287,
    "correct_clicks": 241,
    "hints_used": 5
  }
}
```

### Protezione dei Dati

Il salvataggio avviene automaticamente:
- Al completamento di ogni scena
- Alla chiusura del gioco (anche forzata tramite gestione del segnale di chiusura finestra)
- Ogni 60 secondi di gioco come backup preventivo

Il file viene scritto prima in un file temporaneo, poi rinominato — questo previene la corruzione del salvataggio in caso di interruzione improvvisa.

### Limitazione Nota — Salvataggio in Chiaro

Il file di salvataggio è un JSON leggibile. Un utente può modificarlo a mano per alterare stelle, punteggi e livelli sbloccati. Questa è una **limitazione deliberata e accettata** per la versione 1.0:

- HiddenEngine è pensato per giochi casual single-player senza classifiche online
- La protezione crittografica del salvataggio aggiunge complessità senza un reale beneficio per questo tipo di gioco
- Il file è documentato come "modificabile" — permettere il cheat locale non è un problema di design

Se in futuro si aggiunge una classifica online, il salvataggio lato server sarà la fonte di verità e il file locale diventerà irrilevante ai fini competitivi.

---

## 13. Sistema Leaderboard, Dashboard e Achievements

Questo sistema trasforma il gioco da un'esperienza a singola visita a qualcosa di rigiocabile nel tempo. Il principio guida è che ogni partita deve rispondere a domande diverse per giocatori diversi: *"Posso fare di più punti?"*, *"Posso finire più veloce?"*, *"Posso farlo senza hint?"*. Metriche diverse creano motivazioni indipendenti.

Il sistema è completamente modulare: il motore fornisce l'infrastruttura, il gioco definisce gli obiettivi specifici tramite configurazione JSON.

---

### Architettura — Moduli Coinvolti

```
save_manager.py        ← già esistente, espanso con run_history e achievements
leaderboard_manager.py ← nuovo — calcolo ranking, trend, valutazione achievements
dashboard_screen.py    ← nuovo — stato del motore per la schermata dashboard
```

La separazione è netta:
- `save_manager` si occupa solo di leggere e scrivere su disco
- `leaderboard_manager` si occupa di tutta la logica (calcoli, ordinamenti, valutazione condizioni)
- `dashboard_screen` si occupa solo della presentazione UI

---

### Metriche Tracciate

Per ogni **run completata** (livello portato a termine) il motore salva automaticamente:

| Metrica | Descrizione |
|---|---|
| `score` | Punteggio totale della run |
| `time_seconds` | Tempo totale impiegato (somma delle scene) |
| `hints_used` | Numero totale di hint usati nel livello |
| `wrong_clicks` | Numero totale di click sbagliati |
| `stars` | Stelle ottenute (1–3) |
| `date` | Data e ora ISO 8601 |

Queste quattro metriche — punteggio, tempo, hint, precisione — creano motivazioni di rigiocabilità **indipendenti**: un giocatore che ha già il punteggio massimo può tornare per migliorare il tempo; uno che ha già il tempo record può tornare per la run senza hint.

---

### Struttura Dati del Salvataggio — Espansione

Il file di salvataggio esistente viene espanso. I campi precedenti (`best_score`, `stars`, `completed`) restano invariati per compatibilità. Si aggiungono `best_time_seconds`, `runs` e `achievements`:

```json
{
  "version": "1.1",
  "levels": {
    "level1_giardino": {
      "completed": true,
      "stars": 3,
      "best_score": 2450,
      "best_time_seconds": 187,
      "runs": [
        {
          "date": "2025-04-10T14:23:00",
          "score": 2100,
          "time_seconds": 243,
          "hints_used": 3,
          "wrong_clicks": 12,
          "stars": 2
        },
        {
          "date": "2025-04-12T16:45:00",
          "score": 2450,
          "time_seconds": 187,
          "hints_used": 0,
          "wrong_clicks": 3,
          "stars": 3
        }
      ],
      "scenes": {
        "scene1_fontana": {
          "best_score": 820,
          "best_time_seconds": 58,
          "runs": [...]
        }
      }
    }
  },
  "achievements": {
    "no_hints_giardino": { "unlocked": true,  "date": "2025-04-12T16:45:00" },
    "speed_giardino":     { "unlocked": true,  "date": "2025-04-15T10:12:00" },
    "perfect_giardino":   { "unlocked": false, "date": null },
    "game_complete":      { "unlocked": false, "date": null }
  }
}
```

**Limite run history**: massimo 20 run per livello (configurabile in `config.ini`). Quando si supera il limite, la run più vecchia viene scartata. Il file di salvataggio non cresce indefinitamente.

---

### Il Modulo `leaderboard_manager.py`

Espone un'interfaccia pulita verso `dashboard_screen` e verso gli altri moduli che ne hanno bisogno (es. `level_manager` per valutare gli achievements a fine livello).

**Metodi principali:**

```python
leaderboard_manager.get_level_summary(level_id)
# → { best_score, best_time, best_accuracy, stars, run_count, trend }
# trend: lista degli ultimi N score ordinati per data — usato per il grafico

leaderboard_manager.get_game_summary()
# → { total_stars, max_stars, levels_completed, total_levels,
#     global_best_score, total_play_time, achievements_unlocked }

leaderboard_manager.get_scene_summary(level_id, scene_id)
# → { best_score, best_time, best_accuracy, best_hints }

leaderboard_manager.evaluate_achievements(run_data, level_id)
# → lista di achievement_id appena sbloccati
# chiamato da level_manager subito dopo LEVEL_COMPLETE

leaderboard_manager.format_time(seconds)
# → "3:07"  — usato ovunque nella UI per consistenza
```

**Calcolo accuracy:**
```
accuracy = (oggetti_trovati × 100) / (oggetti_trovati + wrong_clicks)
```
Arrotondata all'intero più vicino. Mostrata come percentuale nella dashboard.

**Calcolo trend:**
Restituisce la lista degli score delle ultime N run (default 10) in ordine cronologico, già normalizzati per essere disegnati su un grafico semplice. Il `dashboard_screen` non deve fare calcoli — riceve dati pronti da disegnare.

---

### Il Sistema Achievements

Gli achievements sono definiti **interamente dal gioco** in `game_config.json` — il motore non conosce il significato di nessun achievement specifico. Il motore fornisce solo un catalogo di **condizioni valutabili**, ognuna con i propri parametri.

#### Definizione in `game_config.json`

```json
"achievements": [
  {
    "id": "no_hints_giardino",
    "name_key": "ach_no_hints_giardino",
    "description_key": "ach_no_hints_giardino_desc",
    "icon": "achievements/no_hints.png",
    "condition": "level_no_hints",
    "params": { "level_id": "level1_giardino" }
  },
  {
    "id": "speed_giardino",
    "name_key": "ach_speed_giardino",
    "description_key": "ach_speed_giardino_desc",
    "icon": "achievements/speed.png",
    "condition": "level_under_time",
    "params": { "level_id": "level1_giardino", "max_seconds": 180 }
  },
  {
    "id": "sharp_eye_giardino",
    "name_key": "ach_sharp_eye",
    "description_key": "ach_sharp_eye_desc",
    "icon": "achievements/eye.png",
    "condition": "level_max_wrong_clicks",
    "params": { "level_id": "level1_giardino", "max_wrong": 3 }
  },
  {
    "id": "perfect_giardino",
    "name_key": "ach_perfect",
    "description_key": "ach_perfect_desc",
    "icon": "achievements/perfect.png",
    "condition": "level_perfect",
    "params": { "level_id": "level1_giardino" }
  },
  {
    "id": "game_complete",
    "name_key": "ach_game_complete",
    "description_key": "ach_game_complete_desc",
    "icon": "achievements/trophy.png",
    "condition": "all_levels_complete",
    "params": {}
  },
  {
    "id": "all_stars",
    "name_key": "ach_all_stars",
    "description_key": "ach_all_stars_desc",
    "icon": "achievements/stars.png",
    "condition": "all_levels_three_stars",
    "params": {}
  }
]
```

#### Condizioni Supportate dal Motore

| Condizione | Parametri | Si attiva quando |
|---|---|---|
| `level_no_hints` | `level_id` | Livello completato con 0 hint usati |
| `level_under_time` | `level_id`, `max_seconds` | Livello completato in meno di N secondi |
| `level_max_wrong_clicks` | `level_id`, `max_wrong` | Livello completato con ≤ N click sbagliati |
| `level_three_stars` | `level_id` | Livello completato con 3 stelle |
| `level_perfect` | `level_id` | 3 stelle + 0 hint + 0 click sbagliati |
| `scene_under_time` | `level_id`, `scene_id`, `max_seconds` | Scena specifica completata in meno di N secondi |
| `all_levels_complete` | — | Tutti i livelli del gioco completati almeno una volta |
| `all_levels_three_stars` | — | Tutti i livelli completati con 3 stelle |

Aggiungere una nuova condizione al motore richiede solo di aggiungere un metodo di valutazione in `leaderboard_manager.py` — nessuna modifica al resto del codice.

#### Valutazione degli Achievements

La valutazione avviene **una sola volta** in `leaderboard_manager.evaluate_achievements()`, chiamato da `level_manager` immediatamente dopo `LEVEL_COMPLETE`, prima di mostrare la schermata Fine Livello. Il risultato è una lista di achievement ID appena sbloccati — se vuota, nessuna notifica.

Gli achievements già sbloccati non vengono rivalutati — il check è `if not already_unlocked`.

#### Notifica Achievement in-game

Quando un achievement viene sbloccato, appare una **notifica non invasiva** nell'angolo in alto a destra:

```
┌──────────────────────────────┐
│  🏆  Achievement sbloccato!  │
│      Senza Suggerimenti      │
│      Il Giardino             │
└──────────────────────────────┘
```

- Appare con slide-in da destra (0.3s)
- Rimane visibile 3 secondi
- Poi slide-out (0.3s)
- Se più achievement vengono sbloccati contemporaneamente, appaiono in coda, uno alla volta

La notifica appare sulla schermata Fine Livello, non durante la scena, per non interrompere il gameplay.

---

### La Dashboard — Struttura e Navigazione

La dashboard è accessibile da tre punti:

1. **Menu principale** → pulsante "Classifiche" (sempre disponibile)
2. **Selezione Livello** → click sull'icona `↗` su ogni livello completato
3. **Fine Livello** → pulsante "Classifiche" nella schermata di riepilogo

La dashboard è uno **stato del motore** (`STATE_DASHBOARD`), gestito da `dashboard_screen.py`, con tre livelli di profondità navigabili:

```
Dashboard Globale
      ↓  (click su un livello)
Dashboard Livello
      ↓  (click su una scena)
Dashboard Scena
```

Il pulsante "Indietro" (`Backspace` o `ESC`) risale di un livello.

---

### Dashboard Globale

Panoramica dell'intero gioco. Risponde alla domanda: *"Come sto andando complessivamente?"*

```
┌─────────────────────────────────────────────────────┐
│  CLASSIFICHE — La Villa Segreta                     │
│                                                     │
│  ★ 18 / 27  stelle totali   ████████████░░░░  67%  │
│  Livelli completati: 2 / 3                          │
│  Ore di gioco: 2h 14m                               │
│  Accuracy media: 89%                                │
│                                                     │
│  LIVELLO              BEST SCORE  BEST TIME  STELLE │
│  ──────────────────────────────────────────────── │
│  Il Giardino ★★★       2.450 pt    3:07       [↗]  │
│  Il Castello ★★☆       4.780 pt    4:23       [↗]  │
│  La Città    🔒         —           —               │
│                                                     │
│  ACHIEVEMENTS   ████████████░░░░░░░░  8 / 12       │
│                                                     │
│  🏆 Senza hint     ✓   ⚡ Speed run  ✓              │
│  🎯 Occhio acuto   ✓   ⭐ Perfetto   ✗              │
│  🏁 Completo       ✗   🌟 Tutte ★★★  ✗              │
│                                                     │
│  [ Chiudi ]                                         │
└─────────────────────────────────────────────────────┘
```

**Note di design:**
- Le stelle totali mostrano anche una barra di progresso percentuale — il giocatore vede a colpo d'occhio quanto manca al 100%
- Gli achievements mostrano icona + nome + spunta/X — quelli non sbloccati sono visibili ma grigi, così il giocatore sa sempre a cosa puntare
- I livelli bloccati sono mostrati con lucchetto e nessun dato

---

### Dashboard Livello

Dettaglio per un singolo livello. Risponde a: *"In cosa posso migliorare qui?"*

```
┌─────────────────────────────────────────────────────┐
│  ← Indietro      IL GIARDINO ABBANDONATO  ★★★       │
│                                                     │
│  RECORD          SCORE      TEMPO    ACCURACY       │
│  Migliore        2.450 pt   3:07     96%            │
│  Ultima run      2.320 pt   3:45     91%            │
│  Media           2.180 pt   3:58     88%            │
│                                                     │
│  ANDAMENTO (ultime 10 run)                          │
│   2500 ┤                              ●             │
│   2300 ┤              ●    ●    ●  ●  │             │
│   2100 ┤  ●    ●    ●                 │             │
│   1900 ┤                                            │
│        └──┬────┬────┬────┬────┬────┬────           │
│           1    2    3    4    5    6   10            │
│                              trend: ↗ +16%          │
│                                                     │
│  SCENE            BEST SCORE   BEST TIME   HINTS   │
│  1. La Fontana       820 pt      0:58        0     [↗]  │
│  2. Il Pergolato     790 pt      1:12        1     [↗]  │
│  3. La Rimessa       840 pt      0:57        0     [↗]  │
│                                                     │
│  ACHIEVEMENTS DI QUESTO LIVELLO                     │
│  🏆 Senza hint  ✓   ⚡ <3 min  ✓   🎯 ≤3 err  ✗    │
│  ⭐ Perfetto     ✗                                  │
│                                                     │
│  [ Rivedi Livello ]              [ Chiudi ]         │
└─────────────────────────────────────────────────────┘
```

**Il grafico trend:**
- Asse Y: punteggio (range adattato automaticamente alle run del giocatore — non fisso)
- Asse X: numero run progressivo
- Il punto del record è evidenziato in giallo
- Sotto il grafico: la percentuale di miglioramento tra la prima e l'ultima run

---

### Dashboard Scena

Drill-down sulla singola scena. Accessibile solo dalla Dashboard Livello.

```
┌─────────────────────────────────────────────────────┐
│  ← Indietro         SCENA 1 — LA FONTANA            │
│                                                     │
│  Record assoluto:   820 pt   in 0:58   96% acc  0 hint │
│  Ultima run:        780 pt   in 1:04   91% acc  0 hint │
│                                                     │
│  ANDAMENTO SCORE (ultime 10 run)                    │
│  [grafico a linea come sopra]                       │
│                                                     │
│  ANDAMENTO TEMPO (ultime 10 run)                    │
│  [grafico a linea invertita — meno è meglio]        │
│                                                     │
│  [ Chiudi ]                                         │
└─────────────────────────────────────────────────────┘
```

---

### Integrazione con la Schermata Fine Livello

La schermata Fine Livello esistente viene arricchita con il **confronto con il record precedente** — mostrato solo se il livello era già stato completato almeno una volta:

```
TOTALE:  2.450 pt   ★★★
         ▲ +350 pt rispetto al tuo record  ← nuovo record!
         ▲ -0:56 rispetto al tuo miglior tempo
```

Se l'achievement viene sbloccato in questa run, appare la notifica dopo le animazioni delle stelle.

---

### Integrazione con la Selezione Livello

Ogni card di livello già completato mostra i dati essenziali del record:

```
┌───────────────────────────┐
│  [thumbnail]              │
│  Il Giardino Abbandonato  │
│  ★★★                      │
│  2.450 pt  |  3:07        │
│  8/12 achievement    [↗]  │
└───────────────────────────┘
```

Il pulsante `↗` apre direttamente la Dashboard Livello.

---

### Configurazione nell'Editor

Il creatore di contenuti gestisce gli achievements nella sezione **"Configurazione Gioco"** dell'editor (non nella Vista Scena o Vista Livello — è una configurazione globale del gioco).

**Pannello Achievements nell'editor:**

- Lista di tutti gli achievement definiti con icona, nome e condizione
- Pulsante "Nuovo Achievement" → dialog con:
  - Upload icona PNG (copiata in `achievements/`)
  - Chiave nome e descrizione (vanno poi completate nei file `strings/`)
  - Dropdown condizione (lista delle condizioni supportate dal motore)
  - Campi parametri dinamici (cambiano in base alla condizione scelta)
- Pulsante "Test Achievement" → simula la condizione con dati fittizi e verifica che il sistema la riconosca
- Visualizzazione conteggio: "12 achievements definiti — il giocatore ne vedrà X/12 nella dashboard"

---

### Scalabilità Futura — Leaderboard Online

Il `leaderboard_manager` è progettato con un'interfaccia che astrae lo storage. Oggi l'implementazione usa il file locale (`save_manager`). In futuro, senza modificare nessun altro modulo, si può aggiungere una implementazione `OnlineLeaderboardManager` che:

- Invia i dati della run a un endpoint REST dopo ogni `LEVEL_COMPLETE`
- Scarica i punteggi migliori globali per popolare una tab "Classifica Mondiale" nella dashboard
- Mantiene il salvataggio locale come cache offline

La dashboard accetterebbe entrambe le implementazioni tramite dependency injection in `core.py` — nessuna modifica al codice della UI o del motore.

---

### Struttura Cartelle Aggiornata — Nuovi File

```
engine/
├── leaderboard_manager.py   ← nuovo
├── dashboard_screen.py      ← nuovo
└── ...

games/villa_segreta/
├── achievements/            ← nuova cartella icone achievement
│   ├── no_hints.png
│   ├── speed.png
│   ├── eye.png
│   └── trophy.png
├── game_config.json         ← espanso con sezione "achievements"
└── ...
```

---

## 14. Il Gioco di Esempio — "La Villa Segreta"

Il gioco incluso nel progetto serve a tre scopi: dimostrare le capacità del motore, fornire un template concreto per nuovi giochi, e servire come test di regressione durante lo sviluppo del motore.

### Struttura Narrativa

La Villa Segreta è un gioco di atmosfera mystery ambientato in una villa italiana abbandonata. Il giocatore esplora ambienti diversi alla ricerca di oggetti nascosti che rivelano i segreti della famiglia che vi abitava.

### Livelli e Scene

**Livello 1 — Il Giardino Abbandonato** (difficoltà: facile)
- Scena 1: La Fontana — 8 oggetti, 120 secondi
- Scena 2: Il Pergolato — 10 oggetti, 90 secondi
- Scena 3: La Rimessa — 12 oggetti, 60 secondi

**Livello 2 — Il Castello** (difficoltà: media)
- Scena 1: La Cucina — 12 oggetti, 100 secondi
- Scena 2: La Torre — 14 oggetti, 80 secondi
- Scena 3: Il Dungeon — 10 oggetti, 90 secondi

**Livello 3 — La Città Antica** (difficoltà: difficile)
- Scena 1: Il Mercato — 15 oggetti, 90 secondi
- Scena 2: La Cattedrale — 12 oggetti, 75 secondi
- Scena 3: Il Porto — 18 oggetti, 60 secondi

### Lingue Incluse

Italiano, Inglese, Francese.

### Obiettivo del Gioco di Esempio

Ogni livello usa feature diverse del motore — il Livello 1 usa solo rilevamento circle e rect base; il Livello 2 introduce il rilevamento mask per oggetti irregolari; il Livello 3 usa scene con background_scale > 1 (navigazione pan/zoom). In questo modo l'intero motore viene esercitato dal gioco di esempio.

---

## 15. L'Editor di Livelli — Specifica Dettagliata

L'editor è uno strumento standalone (`editor/`) che affianca il motore. Il suo unico scopo è permettere al creatore di contenuti di costruire scene giocabili complete — sfondo, oggetti posizionati, hit area, proprietà — e produrre i file JSON corretti, senza mai scrivere JSON a mano e senza conoscere Python.

Esistono due versioni dell'editor, sviluppate in fasi diverse:

- **Editor Base** (`editor/editor_base.py`) — disponibile dalla Fase 2. Finestra Pygame semplice, utilizzabile. Copre il 90% dei casi d'uso.
- **Editor Completo** (`editor/editor_main.py`) — disponibile dalla Fase 5. Aggiunge GUI Tkinter per i pannelli laterali, gestione catalogo avanzata e anteprima integrata.

---

### Il Catalogo degli Oggetti — Concetto Fondamentale

Prima di posizionare qualsiasi oggetto in una scena, quell'oggetto deve esistere nel **catalogo del gioco**. Il catalogo è una libreria centralizzata di tutti gli oggetti cercabili in quel gioco. Ogni oggetto viene definito una sola volta — icona, nome localizzato, tipo di rilevamento predefinito — e poi scelto e posizionato in ogni scena in cui appare.

Il catalogo risiede in `games/nome_gioco/objects_catalog.json`:

```json
{
  "objects": [
    {
      "id": "chiave",
      "label_key": "obj_chiave",
      "icon": "objects/chiave_icon.png",
      "default_detection": "circle",
      "default_radius": 25,
      "default_hint_delay": 30,
      "tags": ["piccolo", "metallo"]
    },
    {
      "id": "gatto",
      "label_key": "obj_gatto",
      "icon": "objects/gatto_icon.png",
      "default_detection": "rect",
      "default_width": 80,
      "default_height": 60,
      "default_hint_delay": 45,
      "tags": ["animale", "grande"]
    },
    {
      "id": "libro",
      "label_key": "obj_libro",
      "icon": "objects/libro_icon.png",
      "default_detection": "mask",
      "default_mask": "objects/libro_mask.png",
      "default_hint_delay": 35,
      "tags": ["oggetto", "rettangolare"]
    }
  ]
}
```

Le icone degli oggetti (`objects/*.png`) sono immagini quadrate 64×64 px in riferimento 1280×720. Vengono scalate dalla HUD automaticamente.

**Relazione catalogo → scene.json**

Il `scene.json` non ridefinisce l'icona o la chiave di testo: le eredita dal catalogo tramite l'`id`. Definisce solo posizione, dimensioni hit area e hint_delay specifici per quella scena (che possono differire dai default del catalogo):

```json
{
  "id": "scene1_fontana",
  "background": "background.jpg",
  "background_scale": 1.0,
  "objects": [
    {
      "catalog_id": "chiave",
      "x": 342, "y": 187,
      "detection_type": "circle",
      "radius": 25,
      "hint_delay": 30
    },
    {
      "catalog_id": "gatto",
      "x": 120, "y": 400,
      "detection_type": "rect",
      "width": 80, "height": 60,
      "hint_delay": 45
    }
  ]
}
```

---

### Il Sistema di Coordinate dell'Editor

Tutte le posizioni salvate in `scene.json` sono sempre in **coordinate di riferimento 1280×720**, indipendentemente da:
- La risoluzione dello schermo su cui gira l'editor
- Il fatto che l'immagine di sfondo sia più grande (background_scale > 1.0)
- Lo zoom con cui il creatore sta guardando la scena nell'editor

L'editor mostra l'immagine adattata alla sua finestra (che può essere qualsiasi dimensione), ma converte ogni click in coordinate di riferimento prima di salvare. Il creatore non deve mai preoccuparsi delle coordinate: clicca dove vede l'oggetto nell'immagine, l'editor fa il resto.

**Caso background_scale > 1.0**

Quando la scena è più grande di 1280×720 (es. `background_scale: 1.5` → immagine 1920×1080), l'editor mostra l'intera immagine scrollabile, e le coordinate salvate sono già in spazio-scena (0–1920 × 0–1080 in questo esempio). Il motore le interpreta correttamente perché conosce il `background_scale`.

---

### Workflow Completo — Dal Foglio Bianco alla Scena Giocabile

Questo è il percorso che compie il creatore di contenuti ogni volta che crea una nuova scena:

```
1. Preparazione materiali
      ↓
2. Apertura/creazione del gioco nell'editor
      ↓
3. Gestione catalogo (aggiunta nuovi oggetti se servono)
      ↓
4. Creazione della scena (sfondo + proprietà)
      ↓
5. Selezione degli oggetti dalla lista catalogo
      ↓
6. Posizionamento di ogni oggetto nella scena
      ↓
7. Revisione visiva degli overlay
      ↓
8. Test nel motore
      ↓
9. Aggiustamenti e salvataggio finale
```

---

### Fase 1 — Preparazione Materiali

Prima di aprire l'editor, il creatore deve avere:

- **L'immagine di sfondo** (`background.jpg`) della scena — qualsiasi risoluzione, l'editor la gestisce
- **Le icone degli oggetti** da cercare (`64×64 px PNG` con trasparenza)
- **Le mask degli oggetti** a forma irregolare (se `detection_type: mask`), in bianco/nero puro: bianco = area cliccabile, nero = trasparente
- Una idea di quali oggetti nascondere in questa scena e dove

---

### Fase 2 — Apertura del Gioco nell'Editor

All'avvio, l'editor mostra la selezione del gioco. Il creatore sceglie il gioco da `games/` oppure ne crea uno nuovo (l'editor crea la struttura di cartelle vuota).

Struttura che l'editor crea automaticamente per un nuovo gioco:
```
games/
└── nome_gioco/
    ├── game_config.json     ← compilato dall'editor
    ├── objects_catalog.json ← inizialmente vuoto
    ├── objects/             ← cartella icone
    ├── strings/
    │   └── it.json          ← creato vuoto, da riempire
    ├── audio/
    └── levels/
```

---

### Fase 3 — Gestione del Catalogo Oggetti

Prima di creare scene, il creatore popola o aggiorna il catalogo del gioco. L'editor mostra:

**Vista Catalogo** — griglia di tutte le icone oggetti esistenti con nome e ID.

**Aggiunta nuovo oggetto:**
1. Pulsante "Nuovo Oggetto"
2. Dialog con campi:
   - `id` — identificatore univoco (es. `chiave`, `gatto`)
   - File dialog per caricare l'icona PNG → copiata automaticamente in `objects/`
   - Tipo rilevamento predefinito (circle / rect / mask)
   - Dimensioni/raggio predefiniti (modificabili per ogni scena)
   - Hint delay predefinito
   - Tag opzionali per filtrare (es. `piccolo`, `animale`)
3. Il `label_key` viene generato automaticamente come `obj_{id}` — il testo vero va inserito nei file `strings/*.json`

**Modifica oggetto esistente:** doppio click sull'icona nella griglia catalogo.

**Eliminazione:** solo se l'oggetto non è usato in nessuna scena esistente — l'editor lo verifica prima di procedere.

---

### Fase 4 — Creazione della Scena

Il creatore seleziona o crea un livello, poi crea una nuova scena. L'editor apre il **Pannello Proprietà Scena**:

| Campo | Tipo | Descrizione |
|---|---|---|
| `id` | testo | Identificatore scena (es. `scene1_fontana`) |
| `background` | file dialog | Carica `background.jpg` — copiata nella cartella scena |
| `background_scale` | numero (1.0–3.0) | Quanto è più grande dell'area di gioco. Default 1.0 |
| `time_limit` | numero (secondi) | Tempo disponibile. 0 = senza limite |
| `objects_to_show` | numero | Quanti oggetti vengono mostrati per run. Dettaglio sotto. |
| `music` | file dialog | File audio opzionale per questa scena |
| `name_key` | testo | Chiave del titolo della scena (es. `scene1_fontana_name`) |

#### Il Campo `objects_to_show` — Dettaglio

È il campo più importante per bilanciare difficoltà e rigiocabilità. Controlla quanti oggetti vengono estratti dal pool e presentati al giocatore per ogni singola run.

Il pannello mostra sempre un **indicatore di stato** aggiornato in tempo reale mentre il creatore lavora:

```
Pool totale:    24 oggetti
Di cui fissi:    3 oggetti  (always_show)
Da estrarre:    5 casuali   (= objects_to_show 8 − fissi 3)
─────────────────────────────────
Oggetti per run: 8 / 24
```

Se `objects_to_show` è impostato a 0 o non specificato, vengono mostrati tutti gli oggetti del pool (nessuna randomizzazione). La UI mostra in questo caso: `"Modalità: tutti gli oggetti"`.

**Slider + campo numerico**: il valore si può impostare sia con un cursore (da 1 al massimo del pool) sia digitando il numero. Il cursore evidenzia con un colore diverso la zona dove `objects_to_show` sarebbe maggiore del numero di fissi — zona valida.

**Avvisi in tempo reale:**
- `objects_to_show > pool totale` → bordo rosso + messaggio "Non ci sono abbastanza oggetti nel pool"
- `fissi > objects_to_show` → bordo arancione + "Hai più oggetti fissi di quanti ne mostri per run"
- Pool < 3 oggetti con `objects_to_show` impostato → suggerimento "Aggiungi più oggetti per una selezione significativa"

Dopo aver caricato lo sfondo, l'editor apre la **Vista Scena** — l'immagine di sfondo occupa la parte principale della finestra.

---

### Fase 5 — Selezione degli Oggetti dalla Lista Catalogo

A sinistra della Vista Scena compare la **Lista Catalogo** — elenco scorrevole di tutti gli oggetti del gioco con icona e nome. Il creatore scorre la lista e **trascina** un oggetto dalla lista sulla scena, oppure fa click sull'oggetto in lista e poi click sulla scena per posizionarlo.

Filtri disponibili nella lista catalogo:
- **Per tag** — mostra solo oggetti con quel tag
- **Per testo** — cerca nel nome o nell'ID
- **Già usati in questa scena** — evidenzia gli oggetti già posizionati
- **Non ancora usati** — mostra solo gli oggetti disponibili

Un oggetto può apparire **più volte** nella stessa scena (es. due chiavi diverse posizionate in punti diversi). In questo caso l'editor gli assegna automaticamente un suffisso numerico nell'istanza (`chiave_1`, `chiave_2`).

---

### Fase 6 — Posizionamento degli Oggetti nella Scena

Questo è il cuore dell'editor. Ogni oggetto trascinato dalla lista entra in **modalità posizionamento** per il tipo di hit area corrispondente al suo default nel catalogo (modificabile).

#### Modalità Circle

Il tipo più comune per oggetti piccoli (chiavi, monete, bottoni).

1. L'oggetto segue il cursore con un cerchio di anteprima
2. **Click sinistro** — fissa il centro del cerchio
3. Il cerchio mostra il raggio default del catalogo
4. **Rotella del mouse** (o campo numerico nel pannello) — regola il raggio
5. **Click sinistro** di conferma o **Invio** — salva la posizione

Visivamente: cerchio semi-trasparente colorato (colore unico per questo oggetto), con cross al centro e label.

#### Modalità Rect

Per oggetti rettangolari (libri, quadri, finestre).

1. **Click e trascina** sull'immagine — disegna il rettangolo
2. Il rettangolo mostra larghezza e altezza in px di riferimento mentre si trascina
3. **Rilascio** — il rettangolo viene fissato
4. Le **maniglie agli angoli** permettono di ridimensionarlo dopo il posizionamento
5. Click fuori dal rettangolo o **Invio** — conferma

Visivamente: rettangolo semi-trasparente con bordo colorato e maniglie di ridimensionamento.

#### Modalità Mask

Per oggetti a forma irregolare (gatti, figure umane, oggetti organici).

1. Dopo aver trascinato l'oggetto sulla scena, si apre automaticamente un **file dialog** per selezionare la mask PNG (bianco/nero)
2. La mask viene caricata e sovrapposta all'immagine di sfondo nella posizione indicata
3. L'editor mostra il **contorno** dell'area bianca della mask in verde
4. **Click e trascina** — sposta la mask sulla scena fino a farla coincidere con l'oggetto reale nell'immagine di sfondo
5. La posizione salvata è il **punto di origine** (angolo top-left) della mask in coordinate di riferimento
6. **Invio** — conferma

La mask viene copiata automaticamente nella cartella `objects/` della scena se non è già lì.

**Suggerimento per creare mask**: il creatore apre `background.jpg` in qualsiasi editor di immagini, dipinge in bianco l'area esatta dell'oggetto su un layer nero, esporta come PNG 1-bit. Non serve precisione millimetrica — le mask approssimative funzionano bene in pratica.

---

### Fase 7 — Revisione Visiva degli Overlay

Dopo aver posizionato tutti gli oggetti, il creatore attiva la **Vista Overlay** (tasto `O` o pulsante nel pannello). Mostra simultaneamente tutte le hit area con una codifica colore immediata:

| Colore bordo | Significato |
|---|---|
| **Giallo** | Oggetto fisso (`always_show: true`) — appare sempre in ogni run |
| **Bianco** | Oggetto casuale (`always_show: false`) — estratto dal pool |
| **Rosso** | Sovrapposizione critica (>30%) con un altro oggetto |
| **Grigio** | Oggetto sul layer `overlay` (non cliccabile) |

Il pannello overlay mostra anche il **riepilogo pool** in tempo reale:

```
Pool: 24 oggetti  |  Fissi: 3 (giallo)  |  Casuali: 21 (bianco)
Per run: 8 oggetti mostrati  →  3 fissi + 5 casuali estratti
```

Questa vista serve per:
- **Verificare che le hit area siano ben posizionate** sull'oggetto visivo
- **Controllare il bilanciamento fissi/casuali** — troppi fissi riducono la varietà tra run
- **Verificare le sovrapposizioni** — rischio click ambigui tra oggetti vicini
- **Identificare oggetti non configurati** (nessuna hit area posizionata)

L'editor evidenzia in rosso le sovrapposizioni superiori al 30% dell'area dell'oggetto più piccolo — non blocca il salvataggio, ma avverte.

**Navigazione nella vista overlay:**
- **Rotella** — zoom in/out sull'immagine
- **Tasto centrale / Spazio+drag** — pan sull'immagine
- **Click su una hit area** — la seleziona e apre il pannello proprietà dell'oggetto per modifiche rapide

---

### Ridimensionamento degli Oggetti — Modalità Selezione

Dopo aver posizionato un oggetto, si può selezionarlo con un click e modificarne forma e dimensioni direttamente sull'immagine. L'editor non entra in una modalità separata: le maniglie appaiono sull'oggetto selezionato senza interruzione del flusso.

**Circle selezionato:**

```
         ○ ← handle nord (trascina per cambiare raggio)
    ┌────┼────┐
○ ──┤    ●    ├── ○  ← handle est/ovest
    └────┼────┘
         ○ ← handle sud
```

- Drag su qualsiasi handle → cambia il raggio uniformemente
- Drag sul centro `●` → sposta il cerchio senza cambiarne il raggio
- Rotella del mouse (con oggetto selezionato) → incrementa/decrementa il raggio di 1px di riferimento per scatto
- `Shift` + rotella → incrementi di 5px

**Rect selezionato:**

```
○──────────○──────────○
│          │          │
○          │          ○
│          │          │
○──────────○──────────○
```

- **8 handle** (4 angoli + 4 lati): drag libero per ridimensionare
- `Shift` + drag su angolo → mantiene le proporzioni (aspect ratio lock)
- `Alt` + drag su angolo → ridimensiona simmetricamente dal centro
- Drag interno (area piena) → sposta senza ridimensionare
- Doppio click su un handle → campo di input numerico per quel bordo specifico

**Mask selezionata:**

La mask non si edita pixel per pixel — per questo esiste un editor di immagini. L'editor gestisce scala e posizione della mask come unità intera.

- Handle agli 4 angoli del bounding box → scala uniforme (`mask_scale`)
- `Shift` + drag su angolo → scala non uniforme (`mask_scale_x`, `mask_scale_y` indipendenti)
- Drag interno → sposta il punto di origine della mask
- Pulsante "**Sostituisci mask**" nel pannello → file dialog per caricare una nuova immagine PNG

I valori `mask_scale`, `mask_scale_x`, `mask_scale_y` vengono salvati nel `scene.json` e applicati dal motore in fase di caricamento prima di mettere la mask in cache.

**Snap alla griglia:**

Se la griglia è attiva (toggle `G`), durante qualsiasi drag (spostamento o ridimensionamento) gli edge si agganciano automaticamente alla griglia. `Ctrl` durante il drag sospende temporaneamente lo snap per movimenti liberi.

---

### Pannello Proprietà Oggetto (click su hit area selezionata)

Quando un oggetto è selezionato nella scena, compare un pannello laterale con tutti i suoi parametri modificabili. Le modifiche sono immediatamente riflesse sull'overlay nell'immagine — nessun pulsante "Applica".

| Campo | Tipo controllo | Descrizione |
|---|---|---|
| ID catalogo | Solo lettura | Mostra l'oggetto di riferimento con icona |
| Layer | Dropdown | Layer di appartenenza — vedi §15 Sistema Layer |
| Tipo hit area | Dropdown | `circle` / `rect` / `mask` — cambiarlo rientra in modalità posizionamento |
| Coordinate X, Y | Campi numerici | Modificabili numericamente oltre che con drag |
| Raggio *(circle)* | Campo numerico + slider | Sincronizzato con le maniglie sull'immagine |
| Larghezza, Altezza *(rect)* | Campi numerici | Sincronizzati con le maniglie |
| Scala mask *(mask)* | Campo numerico (1.0 default) | Scala uniforme; se diversi, `mask_scale_x` e `mask_scale_y` separati |
| Hint delay | Campo numerico (secondi) | Override rispetto al default del catalogo per questa istanza |
| **Fisso (always_show)** | Toggle on/off | Se attivo, questo oggetto appare in ogni run — non viene mai saltato dall'estrazione casuale. Gli oggetti fissi sono evidenziati con un bordo giallo nell'overlay |
| Pulsante "Rigenera da catalogo" | Pulsante | Ripristina dimensioni e hint_delay ai valori default del catalogo |
| Pulsante "Duplica" | Pulsante | Crea un'altra istanza dello stesso oggetto catalogo nella stessa posizione, pronta per essere spostata |
| Pulsante "Rimuovi" | Pulsante (rosso) | Elimina questo posizionamento dalla scena |

---

### Sistema Layer — Gestione della Profondità

Il sistema layer controlla due aspetti distinti e indipendenti:

1. **Priorità di click detection** — quando due hit area si sovrappongono, l'oggetto sul layer più alto riceve il click
2. **Ordine di rendering degli effetti** — glow hint, animazione trovato e sprite overlay seguono l'ordine dei layer

#### Layer Predefiniti

Il motore definisce cinque layer fissi non eliminabili, con z-value interni crescenti:

| Layer | Z-value | Uso tipico |
|---|---|---|
| `background` | 0 | Riservato allo sfondo — nessun oggetto posizionabile qui |
| `objects_low` | 10 | Oggetti visivamente in profondità, molto nascosti |
| `objects_mid` | 20 | **Default** — tutti gli oggetti nuovi vanno qui |
| `objects_high` | 30 | Oggetti in primo piano, visivamente davanti ad altri |
| `overlay` | 40 | Elementi decorativi **non cliccabili** — foglie, cornici, nebbia sovrapposta agli oggetti |

Il layer `overlay` è l'unico dove gli oggetti non sono mai rilevabili dal click detector — serve esclusivamente per effetti visivi decorativi che migliorano la profondità della scena senza interferire col gameplay.

#### Layer Personalizzati

Il creatore può definire layer aggiuntivi con z-value **tra** quelli predefiniti (es. z=25 tra `objects_mid` e `objects_high`). Si creano dalla toolbar del pannello Layer con il pulsante `[+]`. Ogni layer personalizzato ha:
- Nome libero (es. `primo_piano`, `dietro_albero`)
- Z-value numerico (inserito al momento della creazione, modificabile dopo)
- Colore identificativo nell'overlay editor (opzionale)

Il motore non distingue tra layer predefiniti e personalizzati a runtime — usa solo il z-value numerico.

#### Pannello Layer nell'Editor

Posizionato nella barra laterale destra, sempre visibile in Vista Scena. Layout simile a Photoshop/Figma:

```
LAYER                         👁  🔒
──────────────────────────────────────
  overlay         z=40   (2)   ●   ○
  objects_high    z=30   (3)   ●   ○
▶ objects_mid     z=20  (12)   ●   ○   ← attivo
  objects_low     z=10   (4)   ●   ○
  [+ nuovo layer]
```

- **Numero tra parentesi** — quanti oggetti sono in quel layer nella scena corrente
- **Triangolo `▶`** — layer attivo: i nuovi oggetti trascinati dal catalogo vanno automaticamente qui
- **Icona occhio `👁`** — toggle visibilità: nasconde tutti gli oggetti di quel layer nell'editor (non nel gioco)
- **Icona lucchetto `🔒`** — toggle lock: gli oggetti del layer bloccato non sono selezionabili né modificabili; utile per "congelare" un layer già completato e lavorare sugli altri senza selezionare per errore
- **Click** su un layer → lo rende attivo
- **Doppio click** sul nome → rinomina (solo layer personalizzati)
- **Drag** → riordina i layer personalizzati (i predefiniti non si riordinano)
- **Click destro** → menu contestuale: Duplica layer, Unisci con layer sotto, Elimina (solo personalizzati, solo se vuoto)

#### Selezione di Oggetti Sovrapposti

Quando il creatore clicca in un punto dove più oggetti si sovrappongono, viene selezionato quello con z-value più alto (più in primo piano). Per selezionare un oggetto "sotto":

- **`Tab`** — cicla attraverso tutti gli oggetti sovrapposti nel punto, dal più alto al più basso
- Un tooltip mostra: `"Oggetto 2 di 3 in questo punto: gatto (objects_mid)"`

Questo elimina la necessità di nascondere layer per accedere agli oggetti sottostanti, anche se quella opzione rimane disponibile.

#### Visibilità Layer a Runtime (nel Gioco)

La visibilità dei layer nell'editor è solo un ausilio visivo per il creatore — non ha effetto sul gioco. Nel gioco tutti i layer sono sempre attivi, eccetto `overlay` che è visivo ma non interattivo.

Il layer di un oggetto può influenzare visivamente il **colore/intensità del suo glow hint**: oggetti su `objects_low` ricevono un hint più pronunciato (sono più nascosti), oggetti su `objects_high` un hint più sottile. Questo è configurabile nel `game_config.json`:

```json
"layer_hint_intensity": {
  "objects_low":  1.5,
  "objects_mid":  1.0,
  "objects_high": 0.7
}
```

Se non specificato, tutti i layer usano intensità 1.0.

#### Nel `scene.json` — Campo `layer`

```json
{
  "catalog_id": "chiave",
  "x": 342, "y": 187,
  "detection_type": "circle",
  "radius": 25,
  "hint_delay": 30,
  "layer": "objects_high"
}
```

Il campo `layer` è **opzionale**: se assente, il motore usa `objects_mid`. La retrocompatibilità con scene esistenti senza il campo è garantita.

#### Nel `click_detector.py` — Logica Z-Index

Quando un click viene ricevuto:

```
1. Raccoglie tutti gli oggetti non ancora trovati la cui hit area
   contiene il punto (dopo trasformazione coordinate schermo → scena)
2. Scarta gli oggetti su layer "overlay" (non cliccabili)
3. Ordina per z-value decrescente
4. In caso di parità di z-value, usa l'ordine di definizione nel JSON
   (l'oggetto definito prima ha precedenza)
5. Restituisce il primo della lista (il più in primo piano)
   oppure null se la lista è vuota (click sbagliato)
```

#### Nel `game_config.json` — Definizione Layer del Gioco

I layer predefiniti del motore sono sempre disponibili. Il gioco può aggiungere layer personalizzati che vengono caricati e riconosciuti dall'editor e dal motore:

```json
"custom_layers": [
  {
    "id": "dietro_albero",
    "z_value": 15,
    "label": "Dietro all'albero",
    "hint_intensity": 1.8
  }
]
```

---

### Fase 8 — Test nel Motore

Il pulsante **"Test Scena"** (o `Ctrl+T`) salva temporaneamente il `scene.json` e lancia il motore direttamente su questa scena, con:

- Timer funzionante
- Click detection attiva
- HUD visibile
- Feedback "Trovato!" e "Sbagliato!"

L'editor rimane aperto in background. Chiudendo la finestra di gioco, l'editor ritorna in primo piano. Eventuali modifiche successive non richiedono di rilanciare il test da capo — il pulsante Test rilancia sempre la versione più recente.

Se mancano risorse necessarie (musica non trovata, icona mancante), il motore le ignora e logga l'avviso — non crasha. Il creatore vede i warning nel pannello log dell'editor.

---

### Fase 9 — Salvataggio

**Salvataggio automatico** ogni 60 secondi in un file temporaneo (`scene.json.autosave`). Se l'editor viene chiuso accidentalmente, al riavvio propone di ripristinare il lavoro non salvato.

**Salvataggio manuale** (`Ctrl+S`) — scrive direttamente `scene.json` nella cartella corretta della scena.

Il file viene sempre validato contro `engine/schemas/scene_schema.json` prima di essere scritto. Se la validazione fallisce (situazione rara — l'editor costruisce sempre JSON valido), mostra il dettaglio dell'errore e non sovrascrive il file esistente.

---

### Vista Livello — Gestione del Flusso

L'editor ha due modalità principali distinte: **Vista Scena** (posizionamento oggetti, già descritta) e **Vista Livello** (gestione del flusso, sequenza, transizioni). Si passa da una all'altra con un pulsante nella toolbar o con `Tab`.

**Pannello di navigazione** (sempre visibile in entrambe le viste):

```
[Villa Segreta]
├── Livello 1 — Il Giardino        [timer_behavior: complete]
│   ├── 1 — La Fontana      ✓ 8/24 obj  120s  →slide_left
│   ├── 2 — Il Pergolato    ✓ 10/30 obj  90s  →slide_left
│   └── 3 — La Rimessa      ⚠ 0/0 obj    60s  →fade
├── Livello 2 — Il Castello        [timer_behavior: complete]
│   └── (vuoto — nessuna scena)
└── [+ Nuovo Livello]
```

Icone di stato per ogni scena:
- `✓` — completa (sfondo + almeno 1 oggetto)
- `⚠` — parziale (sfondo ma 0 oggetti, oppure oggetti ma nessun sfondo)
- `✗` — vuota (nessun contenuto)

Le scene `⚠` e `✗` vengono incluse nel `level_config.json` ma il motore le skippa durante il gioco reale, loggando un avviso. In Developer Mode vengono comunque eseguite per permettere di testare il flusso anche su lavori in corso.

---

### Vista Livello — Configurazione del Flusso

In Vista Livello, la parte principale della finestra mostra il **diagramma di flusso del livello** in forma visiva:

```
[INTRO]  →  [Scena 1: La Fontana]  →  [Scena 2: Il Pergolato]  →  [Scena 3: La Rimessa]  →  [FINE LIVELLO]
              120s  8 oggetti           90s  10 oggetti             60s  0 oggetti ⚠
                         ↓slide_left              ↓slide_left              ↓fade
```

Ogni blocco scena nel diagramma è cliccabile:
- **Click singolo** → apre pannello laterale con proprietà della scena (time_limit, transition_out)
- **Doppio click** → passa alla Vista Scena per quella scena
- **Drag** → riordina le scene nel flusso, aggiorna automaticamente i campi `order` in `level_config.json`

**Pannello proprietà livello** (sempre visibile in Vista Livello):

| Campo | Controllo | Descrizione |
|---|---|---|
| `timer_behavior` | Toggle `complete` / `fail` | Comportamento globale timer per questo livello |
| `difficulty` | Dropdown easy/normal/hard | Etichetta difficoltà (non influenza il motore, solo display) |
| `star_thresholds` | 3 campi numerici | Punteggi soglia per 1, 2, 3 stelle sul totale livello |
| `intro_image` | File dialog | Immagine schermata intro (opzionale) |
| `intro_text_key` | Testo | Chiave del testo narrativo intro |
| `completion_reward` | Testo | ID del livello da sbloccare al completamento |

**Pannello proprietà scena** (appare quando si clicca su una scena nel diagramma):

| Campo | Controllo | Descrizione |
|---|---|---|
| `time_limit` | Numero (secondi) | 0 = nessun limite |
| `transition_out` | Dropdown | `fade` / `slide_left` / `slide_right` |

---

### Operazioni sulle Scene nel Flusso

**Aggiungere una scena al livello:**
- Pulsante `[+]` a destra dell'ultima scena nel diagramma, oppure trascinamento di una scena esistente dal pannello di navigazione nel diagramma
- Apre dialog: "Nuova scena" (crea cartella e file vuoti) oppure "Importa scena esistente" (riusa una cartella scena già presente nella struttura)

**Rimuovere una scena dal livello:**
- Tasto `Canc` sulla scena selezionata nel diagramma
- Dialog di conferma: "Rimuovere la scena dal livello? I file della scena non verranno cancellati dal disco."
- La cartella rimane intatta — la scena è solo rimossa dalla lista `scenes` in `level_config.json`

**Cancellare definitivamente una scena:**
- Solo dalla vista file (click destro → "Elimina definitivamente") con doppia conferma

**Duplicare una scena:**
- Click destro su scena → "Duplica" → crea una copia della cartella con un nuovo ID, aggiunge la copia in fondo al livello

---

### Test del Flusso — Developer Mode

Il pulsante **"Test Livello"** (`Ctrl+L`) lancia il motore dall'inizio del livello corrente con la **Developer Mode** attiva. Questa modalità è riconoscibile da un piccolo banner "DEV" nell'angolo in alto a sinistra della finestra di gioco.

In Developer Mode sono disponibili tasti rapidi per chi sviluppa e deve testare senza giocare per 6 minuti:

| Tasto | Azione |
|---|---|
| `F1` | Trova immediatamente tutti gli oggetti della scena corrente |
| `F2` | Salta la scena corrente (come se fosse completata con 0 punti) |
| `F3` | Timer 10× più veloce (toggle) |
| `F4` | Timer fermo (toggle pausa timer senza aprire menu pausa) |
| `F5` | Mostra/nascondi overlay hit area (come in editor) |
| `F6` | Mostra/nascondi pannello debug: FPS, stato preloading, stato thread audio, memoria cache |
| `F7` | Forza scadenza timer immediata (testa il comportamento `timer_behavior`) |

Developer Mode non è disponibile nell'EXE distribuito al giocatore finale — viene compilata via flag `DEBUG = False` in `engine/utils.py`.

**Chiudendo la finestra di test**, l'editor torna in primo piano sul punto in cui era. Il pulsante "Test Livello" è sempre disponibile — ogni click rilancia il motore sulla versione più recente salvata del livello.

---

### Shortcut da Tastiera dell'Editor

**Modalità e strumenti:**

| Tasto | Azione |
|---|---|
| `1` | Strumento circle |
| `2` | Strumento rect |
| `3` | Strumento mask |
| `S` | Strumento selezione (modalità default) |
| `Tab` | Con oggetto selezionato: cicla tra oggetti sovrapposti nello stesso punto |

**Visibilità e navigazione:**

| Tasto | Azione |
|---|---|
| `O` | Toggle overlay tutte le hit area |
| `H` | Toggle overlay hint area (verifica difficoltà) |
| `L` | Toggle pannello Layer |
| `G` | Toggle griglia e snap |
| `Spazio + drag` | Pan sull'immagine |
| `+` / `-` | Zoom in/out immagine nell'editor |
| `F` | Fit — adatta l'immagine alla finestra |

**Layer rapidi (con oggetto selezionato):**

| Tasto | Azione |
|---|---|
| `Ctrl+1` | Sposta oggetto su layer `objects_low` |
| `Ctrl+2` | Sposta oggetto su layer `objects_mid` |
| `Ctrl+3` | Sposta oggetto su layer `objects_high` |
| `Ctrl+4` | Sposta oggetto su layer `overlay` |
| `Ctrl+]` | Sposta oggetto su layer superiore |
| `Ctrl+[` | Sposta oggetto su layer inferiore |

**Ridimensionamento (con oggetto selezionato):**

| Tasto | Azione |
|---|---|
| Rotella mouse | Cambia raggio (circle) di 1px per scatto |
| `Shift` + rotella | Cambia raggio di 5px per scatto |
| `Ctrl` + drag | Sospende snap durante ridimensionamento |
| `Shift` + drag angolo | Mantiene proporzioni (rect) |
| `Alt` + drag angolo | Ridimensiona dal centro (rect) |

**Editing:**

| Tasto | Azione |
|---|---|
| `Canc` | Rimuove oggetto selezionato |
| `Ctrl+D` | Duplica oggetto selezionato |
| `Ctrl+Z` | Undo (fino a 50 passi) |
| `Ctrl+Y` | Redo |
| `Ctrl+S` | Salva scena corrente |
| `Ctrl+T` | Test scena nel motore |
| `Ctrl+L` | Test livello completo nel motore |
| `Ctrl+E` | Esporta livello corrente |
| `Esc` | Annulla azione in corso / deseleziona |

---

### Tecnologia dell'Editor

**Editor Base (Fase 2)** — `editor/editor_base.py`
- Interamente in Pygame: finestra unica con pannello laterale disegnato in Pygame
- Nessuna dipendenza aggiuntiva oltre a Pygame
- Supporta circle, rect, salvataggio JSON
- Non supporta mask, undo, test integrato

**Editor Completo (Fase 5)** — `editor/editor_main.py`
- Tkinter per la finestra principale, pannelli laterali, dialogs, form
- Pillow (`Pillow>=10.0`) per la visualizzazione dell'immagine nel canvas Tkinter
- Il motore viene lanciato come subprocess per il test (`subprocess.Popen`)
- Supporta tutte le funzionalità descritte in questa sezione

Dipendenze aggiuntive per l'editor completo (non necessarie per il motore di gioco):
```
Pillow>=10.0.0
```

L'editor non è incluso nell'EXE distribuito al giocatore finale — è uno strumento di sviluppo.

---

## 16. Roadmap di Sviluppo

Lo sviluppo è organizzato in fasi sequenziali, ognuna con un obiettivo verificabile.

### Fase 1 — Nucleo Funzionante
**Obiettivo**: una scena si carica, il click funziona, gli oggetti vengono trovati.

- Struttura cartelle del progetto
- `engine/utils.py` con `get_resource_path()` e `get_writable_path()` — **primo file da scrivere**, usato da tutti i moduli successivi
- `core.py` con game loop base e gestione argomento `--game` da CLI
- `scaling_manager.py` con scaling semplice (senza pan/zoom, senza caching avanzato)
- `json_validator.py` con schemi per `scene.json` e `level_config.json` — attivo fin dalla Fase 1 per evitare errori durante lo sviluppo
- `scene_loader.py` con lettura e validazione JSON
- `click_detector.py` con rilevamento circle e rect
- `hud_manager.py` base (lista oggetti + timer semplice + troncamento etichette con tooltip)
- `hiddenengine.spec` base — verificato che il build PyInstaller funzioni già da qui
- Prima scena del gioco di esempio funzionante e buildabile in EXE

### Fase 2 — HUD Evoluta, Feedback e Tool Editor Minimo
**Obiettivo**: il gioco si sente "polished" nelle interazioni base. Il creatore di contenuti ha già uno strumento per produrre scene senza scrivere JSON a mano.

- `effects_engine.py` (animazione trovato, animazione sbagliato) con profili qualità Alta/Media/Bassa
- HUD completa con punteggio animato e stelle
- `hint_system.py` base
- `audio_manager.py` base con suoni WAV sincroni (senza thread separato)
- **`editor/editor_cli.py`** — editor minimo da riga di comando: carica un'immagine, permette di posizionare oggetti con click e salva `scene.json`. Nessuna GUI elaborata — basta essere usabile.

> Motivazione: senza un tool editor, tutte le scene del gioco di esempio nelle fasi successive vengono scritte a mano in JSON. Questo è lento e fonte di errori. Un editor CLI minimo nella Fase 2 accelera tutte le fasi successive.

### Fase 3 — Flusso Multi-Scena e Multi-Livello
**Obiettivo**: il gioco ha un inizio, una fine e la progressione funziona.

- `level_manager.py` completo
- `transition_manager.py` con fade e slide
- Schermata risultato scena e fine livello
- Selezione livello con thumbnail e stelle
- `save_manager.py` completo
- Menu di selezione gioco all'avvio (se nessun gioco è specificato in `config.ini`)

### Fase 4 — Audio Thread Separato e Multilingua
**Obiettivo**: audio professionale e supporto lingue.

- `audio_manager.py` con pattern *audio command dispatcher* (thread pianificatore + mixer nel main loop)
- `language_manager.py` completo con gestione chiavi mancanti e fallback
- Schermata Impostazioni completa
- Menu principale completo
- Modalità schermo fullscreen e borderless
- Test HUD con lingue lunghe (tedesco, finlandese)

### Fase 5 — Scaling Avanzato, Pan/Zoom ed Editor Visuale
**Obiettivo**: feature avanzate, strumenti definitivi, qualità di produzione.

- Scaling con caching LRU delle Surface (64 MB default)
- Pan/zoom nella scena con pipeline di trasformazione coordinate schermo → scena
- Rilevamento mask pixel-perfect (con caching obbligatorio)
- Resize finestra tra schermate (non durante scena attiva)
- `editor/editor_main.py` — editor visuale completo con GUI Pygame/Tkinter
- Test completo su risoluzioni diverse (720p, 1080p, 1440p, 4K)
- Documentazione finale e commenti nel codice

---

## 17. Pacchettizzazione e Distribuzione in EXE

Il motore e il gioco devono essere distribuibili come singolo eseguibile Windows (`.exe`) senza richiedere l'installazione di Python o di alcuna dipendenza. Tutto il codice è scritto con questa destinazione in mente fin dalla Fase 1.

**Tool raccomandato**: **PyInstaller** (≥ 6.x). È il più diffuso per applicazioni Pygame su Windows e produce un eseguibile self-contained o una cartella distribuibile.

---

### Il Pattern `get_resource_path()` — Regola Fondamentale

Quando un eseguibile PyInstaller viene lanciato, le risorse (immagini, JSON, audio, font) vengono estratte in una cartella temporanea accessibile tramite `sys._MEIPASS`. In sviluppo questa cartella non esiste. **Ogni accesso a un file nel progetto deve usare questa funzione** — nessun path hardcoded, nessun `__file__` usato direttamente:

```python
import sys
import os

def get_resource_path(relative_path: str) -> str:
    """
    Restituisce il path assoluto a una risorsa del progetto.
    Funziona sia in sviluppo (Python normale) sia in un eseguibile PyInstaller.
    """
    if getattr(sys, 'frozen', False):
        # Eseguibile PyInstaller: le risorse sono in sys._MEIPASS
        base = sys._MEIPASS
    else:
        # Sviluppo: le risorse sono nella cartella radice del progetto
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, relative_path)
```

Questa funzione risiede in `engine/utils.py` ed è importata da tutti i moduli che aprono file. **Nessun modulo del motore usa `open()`, `pygame.image.load()`, `pygame.mixer.music.load()` o simili con path relativi o costruiti con `__file__`.**

Esempi di utilizzo corretto:

```python
# scene_loader.py
from engine.utils import get_resource_path

bg_path = get_resource_path(os.path.join("games", game_id, "levels", level_id, scene_id, "background.jpg"))
surface = pygame.image.load(bg_path)

# language_manager.py
lang_path = get_resource_path(os.path.join("games", game_id, "strings", f"{lang}.json"))
with open(lang_path, encoding="utf-8") as f:
    data = json.load(f)
```

---

### Path Scrivibili — Salvataggi e Configurazione

`sys._MEIPASS` è **read-only**. Salvataggi e `config.ini` non possono essere scritti lì. I file che il motore deve poter **scrivere** usano una cartella dedicata nella directory utente:

```python
import os

def get_writable_path(relative_path: str) -> str:
    """
    Restituisce il path per file scrivibili (salvataggi, config).
    Su Windows usa %APPDATA%\HiddenEngine\
    """
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    base = os.path.join(appdata, "HiddenEngine")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, relative_path)
```

| File | Funzione da usare |
|---|---|
| `save_*.json` (salvataggi) | `get_writable_path()` |
| `config.ini` (impostazioni persistenti) | `get_writable_path()` |
| Log di errori | `get_writable_path()` |
| Immagini, JSON, audio, font | `get_resource_path()` |

Alla prima esecuzione il motore copia `config.ini` dalla cartella risorse (default di fabbrica) nella cartella scrivibile, se non esiste già.

---

### Struttura della Cartella Aggiunta — `engine/utils.py`

```
engine/
├── core.py
├── utils.py          ← get_resource_path(), get_writable_path(), logging
├── scaling_manager.py
└── ...
```

---

### Import — Regole Obbligatorie

Per garantire il funzionamento in un eseguibile PyInstaller, tutti gli import del progetto devono seguire queste regole:

1. **Import assoluti sempre** — mai import relativi impliciti. PyInstaller risolve meglio i moduli con path espliciti.
   ```python
   # CORRETTO
   from engine.utils import get_resource_path
   from engine.scaling_manager import ScalingManager

   # SBAGLIATO
   from .utils import get_resource_path   # import relativo — problematico in alcuni contesti frozen
   ```

2. **Nessun `import *`** — rende impossibile a PyInstaller rilevare le dipendenze staticamente.

3. **Dipendenze opzionali gestite esplicitamente** — se un modulo è opzionale (es. `jsonschema` per la validazione), usare un try/except con fallback chiaro:
   ```python
   try:
       import jsonschema
       VALIDATION_AVAILABLE = True
   except ImportError:
       VALIDATION_AVAILABLE = False
   ```

---

### File `.spec` — Configurazione PyInstaller

Il file `hiddenengine.spec` va incluso nel repository. I punti critici da configurare:

```python
# hiddenengine.spec (estratto rilevante)

a = Analysis(
    ['main.py'],
    datas=[
        # Includi tutte le risorse del motore
        ('engine/schemas', 'engine/schemas'),
        # Includi il gioco di esempio (e tutti i giochi presenti)
        ('games', 'games'),
        # config.ini di default (template)
        ('config.ini', '.'),
    ],
    hiddenimports=[
        'pygame',
        'pygame.mixer',
        'pygame.font',
        'pygame.image',
        'jsonschema',
        'queue',
    ],
    ...
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='HiddenEngine',
    icon='games/villa_segreta/ui/icon.ico',
    console=False,   # Nessuna finestra terminale visibile all'utente finale
    ...
)
```

**Note importanti sul `.spec`:**
- `console=False` è obbligatorio per un gioco distribuibile — la console nera non deve apparire
- Le cartelle `games/` vengono incluse interamente — aggiungere un nuovo gioco significa ricompilare l'eseguibile o distribuire la cartella separatamente
- I font `.ttf` personalizzati in `games/*/ui/` sono inclusi automaticamente se la cartella `games` è nei `datas`

---

### Dipendenze Python — `requirements.txt`

```
pygame>=2.5.0
jsonschema>=4.0.0
```

Nessuna altra dipendenza esterna. Il motore usa solo la libreria standard Python per tutto il resto (threading, queue, json, os, sys, configparser, hashlib).

---

### Checklist Pre-Build

Prima di ogni build dell'eseguibile:

- [ ] Tutti gli `open()` e i load di asset usano `get_resource_path()` o `get_writable_path()`
- [ ] Nessun path hardcoded con backslash Windows (`C:\...`) nel codice
- [ ] Nessun `__file__` usato per costruire path a risorse
- [ ] `console=False` nel `.spec`
- [ ] Test dell'eseguibile su una macchina senza Python installato
- [ ] Verifica che i salvataggi vengano scritti in `%APPDATA%\HiddenEngine\` e non nella cartella dell'exe

---

## 18. Glossario

| Termine | Significato |
|---|---|
| **Motore (Engine)** | La parte del progetto che contiene tutta la logica e il codice Python |
| **Gioco (Game)** | La parte del progetto che contiene solo dati: immagini, JSON, audio |
| **Scena** | Una singola immagine di sfondo con un insieme di oggetti nascosti da trovare |
| **Livello** | Un gruppo di scene tematicamente collegate, da completare in sequenza |
| **Risoluzione di riferimento** | 1280×720 px — la base su cui vengono definite tutte le posizioni e dimensioni |
| **Fattore di scala** | Il moltiplicatore calcolato dal motore per adattare 1280×720 alla risoluzione reale |
| **Hit area** | L'area di click associata a un oggetto nascosto (circle, rect o mask) |
| **HUD** | Heads-Up Display — l'interfaccia visibile durante il gioco (timer, punteggio, ecc.) |
| **Hint** | Suggerimento visivo che indica la posizione di un oggetto non ancora trovato |
| **Crossfade** | Transizione audio fluida tra due tracce musicali diverse |
| **Thread audio** | Processo parallelo dedicato esclusivamente alla gestione dell'audio |
| **Coda messaggi** | Sistema di comunicazione thread-safe tra game loop e thread audio |
| **Chiave di testo** | Identificatore univoco per un testo localizzato (es. `"btn_play"`) |
| **Stato di gioco** | La schermata corrente attiva nel motore (menu, scena, pausa, ecc.) |
| **Delta time** | Il tempo trascorso tra un frame e il successivo, usato per animazioni fluide |
| **Pan** | Navigazione nella scena trascinando lo sfondo |
| **Zoom** | Avvicinamento o allontanamento sulla scena |
| **Mask** | Immagine in bianco e nero che definisce l'area esatta di un oggetto irregolare |
| **Thumbnail** | Immagine di anteprima usata nella schermata di selezione livello |
| **Letterbox** | Bande nere ai lati dello schermo quando il rapporto d'aspetto non corrisponde |
| **Splash screen** | Schermata iniziale con logo che appare all'avvio del gioco |
| **Cache LRU** | Cache con politica "Least Recently Used" — scarta gli elementi usati meno di recente quando si raggiunge il limite di memoria |
| **Audio command dispatcher** | Pattern architetturale: il thread audio pianifica i comandi, il main loop esegue le chiamate a `pygame.mixer` |
| **JSON Schema** | Standard per descrivere e validare la struttura di file JSON — usato per dare errori chiari su file di gioco malformati |
| **Profilo qualità** | Configurazione degli effetti visivi attivi (Alta/Media/Bassa) per adattarsi all'hardware del giocatore |
| **Coordinate scena** | Coordinate in riferimento 1280×720, indipendenti da zoom/pan — usate internamente per hit area e posizioni oggetti |
| **Coordinate schermo** | Coordinate pixel reali sullo schermo — convertite in coordinate scena prima del rilevamento click |
| **Catalogo oggetti** | Libreria centralizzata degli oggetti cercabili di un gioco (`objects_catalog.json`). Ogni oggetto è definito una sola volta e poi referenziato nelle scene tramite `catalog_id` |
| **catalog_id** | Campo in `scene.json` che referenzia un oggetto nel catalogo — sostituisce la definizione ridondante di icona e chiave in ogni scena |
| **Mask** (editor) | Immagine PNG bianco/nero che definisce l'area cliccabile di un oggetto irregolare. Bianco = area attiva, nero = trasparente |
| **Vista Overlay** | Modalità dell'editor che sovrappone all'immagine di sfondo tutte le hit area posizionate — utile per verificare correttezza e sovrapposizioni |
| **Editor Base** | Versione minimale dell'editor (Fase 2), interamente in Pygame, sufficiente per circle e rect |
| **Editor Completo** | Versione avanzata (Fase 5) con GUI Tkinter+Pillow, supporto mask, undo, test integrato |
| **Vista Scena** | Modalità editor per posizionare oggetti in una singola scena |
| **Vista Livello** | Modalità editor per gestire il flusso del livello: ordine scene, transizioni, proprietà globali |
| **Developer Mode** | Modalità del motore attivabile solo in sviluppo, con tasti F1-F7 per test rapido del flusso senza giocare per intero |
| **PreloadedScene** | Struttura dati che contiene la scena successiva già caricata e scalata in memoria, pronta per la transizione immediata |
| **SCENE_COMPLETE** | Evento interno emesso da `level_manager` quando tutti gli oggetti sono trovati o il timer scade |
| **LEVEL_COMPLETE** | Evento interno emesso da `level_manager` quando l'ultima scena del livello è completata |
| **timer_behavior** | Campo in `level_config.json` che determina cosa succede allo scadere del timer: `"complete"` (avanza comunque) o `"fail"` (richiede rifacimento) |
| **on_midpoint_callback** | Funzione chiamata da `transition_manager` quando lo schermo è completamente nero/opaco — momento sicuro per scambiare la scena attiva |
| **Run** | Una singola partita completata a un livello, con tutte le metriche associate (score, tempo, hint, wrong click) |
| **Run history** | Storico delle ultime N run per livello — base per il calcolo del trend e della media |
| **Achievement** | Obiettivo secondario definito dal gioco in `game_config.json`, valutato dal motore a fine livello tramite condizioni parametrizzate |
| **Condizione achievement** | Tipo di regola valutabile dal motore (es. `level_no_hints`, `level_under_time`) — il gioco sceglie quale usare e con quali parametri |
| **leaderboard_manager** | Modulo che calcola ranking, trend, accuracy, valuta achievement — interfaccia tra dati e UI della dashboard |
| **dashboard_screen** | Stato del motore che gestisce la visualizzazione della dashboard a tre livelli (globale → livello → scena) |
| **Trend** | Lista degli score delle ultime N run in ordine cronologico — usato per il grafico di andamento nella Dashboard Livello |
| **Accuracy** | Percentuale di click corretti sul totale dei click effettuati in una run |
| **Notifica achievement** | Overlay non invasivo (slide-in da destra, 3s) che appare sulla schermata Fine Livello quando un achievement viene sbloccato |
| **Layer** | Livello di profondità nominato a cui appartiene un oggetto nella scena — controlla priorità di click detection e ordine di rendering degli effetti |
| **Z-value** | Valore numerico interno di un layer — più alto = più in primo piano. Il creatore usa i nomi dei layer, non i numeri direttamente |
| **Layer `overlay`** | Layer z=40 non interattivo — gli oggetti qui sono visibili ma non ricevono click. Usato per elementi decorativi (foglie, cornici) che si sovrappongono visivamente agli oggetti cercabili |
| **Layer attivo** | Layer selezionato nel pannello Layer dell'editor — i nuovi oggetti vengono automaticamente assegnati a questo layer |
| **Lock layer** | Stato di un layer che impedisce la selezione e modifica degli oggetti al suo interno — utile per congelare layer già completati |
| **Snap** | Aggancio automatico degli edge a una griglia durante drag e ridimensionamento — disattivabile con `Ctrl` durante il drag |
| **mask_scale** | Fattore di scala applicato alla mask in memoria senza modificare il file originale — salvato in `scene.json` |
| **layer_hint_intensity** | Configurazione in `game_config.json` che regola l'intensità visiva del glow hint per layer — oggetti più nascosti possono avere hint più visibili |
| **Pool oggetti** | Insieme completo degli oggetti posizionati in una scena dal creatore — può essere molto più grande del numero mostrato al giocatore per ogni run |
| **objects_to_show** | Campo in `scene.json` — quanti oggetti vengono estratti dal pool e mostrati al giocatore per ogni singola run. Motore della rigiocabilità. |
| **always_show** | Flag su un singolo oggetto del pool — se true, quell'oggetto appare sempre in ogni run, prima dell'estrazione casuale degli altri |
| **Estrazione casuale** | Processo eseguito da `scene_loader` ad ogni avvio scena: seleziona `objects_to_show` oggetti dal pool (fissi sempre inclusi, casuali mescolati con shuffle) |
| **`game_config.json`** | File di configurazione globale del gioco — identità visiva, HUD, lingua, achievements, layer personalizzati. Letto una sola volta all'avvio. |
| **`objects_catalog.json`** | Libreria centralizzata degli oggetti cercabili del gioco. Ogni oggetto è definito una volta (id, icona, label\_key, detection default) e referenziato nelle scene tramite `catalog_id`. |
| **`game_id`** | Identificatore univoco del gioco in `game_config.json` — usato come nome del file di salvataggio e come cartella in `%APPDATA%`. |
| **Campi obbligatori minimi** | Sottoinsieme di `game_config.json` sufficiente per far girare il gioco: `game_id`, `version`, `title_key`, `menu.background`, `default_language`. |

---

*Documento redatto per HiddenEngine v1.0 — Aprile 2025*  
*Tutti i nomi di file, strutture JSON e specifiche tecniche descritte in questo documento sono da considerarsi la specifica ufficiale di riferimento per lo sviluppo del motore e del gioco di esempio.*
