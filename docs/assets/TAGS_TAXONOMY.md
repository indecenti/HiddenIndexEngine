# Tassonomia Tag - Riferimento Canonico

> **File sorgente (fonte di verità)**: [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json)
> Questo documento è la guida operativa; il JSON è autoritativo.

Il sistema di tag è il cuore della navigazione intelligente nella tab OBJ dell'editor.
Ogni oggetto ha **tag multipli** organizzati in namespace semantici (non gerarchici).

---

## Principio: namespace, non livelli

I tag appartengono a un namespace tipizzato:

| Namespace     | Obbligatorio?    | Descrizione                                              |
|---------------|------------------|----------------------------------------------------------|
| `DIMENSIONE`  | **Sempre**       | Dimensione fisica dell'oggetto nel gioco                 |
| `MATERIALE`   | **Sempre**       | Materiale prevalente dell'oggetto                        |
| `DOMINIO`     | **Sempre**       | Categoria funzionale/tematica                            |
| `TEMA`        | Se applicabile   | Estetica narrativa predominante                          |
| `MOOD`        | Se applicabile   | Attributo emotivo o qualitativo                          |
| `NATURA`      | Solo nat./biol.  | Oggetti del mondo naturale                               |
| `GEOGRAFIA`   | Se rilevante     | Origine culturale/geografica                             |
| `COLORE`      | Solo se identif. | Colore dominante, solo se è il tratto identificativo     |

**Regola d'oro**: ogni oggetto deve avere almeno un tag da DIMENSIONE, uno da MATERIALE
e uno da DOMINIO (o NATURA se è un essere vivente/pianta).

---

## NAMESPACE: DIMENSIONE

Tag tecnici nascosti dai chip UI ma presenti nel JSON e ricercabili.

| Tag       | Soglia approssimativa                              |
|-----------|----------------------------------------------------|
| `piccolo` | Radius < 25px oppure lato < 40px                   |
| `medio`   | Radius 25–50px oppure lato 40–90px                 |
| `grande`  | Radius > 50px oppure lato > 90px                   |

---

## NAMESPACE: MATERIALE

Materiale prevalente. Un oggetto può averne più di uno se composto.

| Tag        | Uso tipico                                                   |
|------------|--------------------------------------------------------------|
| `metallo`  | Ferro, acciaio, alluminio, rame, ottone, oro, argento        |
| `legno`    | Legno grezzo o lavorato, compensato                          |
| `carta`    | Carta, cartone, cartoncino, libri, manifesti                 |
| `plastica` | Polimeri sintetici, resine, PVC                              |
| `vetro`    | Vetro, cristallo trasparente, specchi                        |
| `stoffa`   | Tessuto, tela, imbottitura, feltro                           |
| `ceramica` | Ceramica, terracotta, porcellana, maiolica                   |
| `gomma`    | Gomma naturale o sintetica, latex, silicone                  |
| `cuoio`    | Pelle conciata, cuoio lavorato (cinture, selle, borse)       |
| `pietra`   | Pietra, marmo, minerali, fossili, meteoriti                  |
| `cristallo`| Cristallo, gemme, quarzi trasparenti                         |
| `cera`     | Cera d'api, paraffina, candele                               |
| `osso`     | Ossa, avorio, corno animale, denti                           |
| `biologico`| Materiale organico non-animale o parti biologiche            |

> **Nota**: `pelle` (skin/flesh) rimane distinto da `cuoio` (leather lavorato).
> Usa `cuoio` per accessori in cuoio, `biologico` + `pelle` per parti corporee horror.

---

## NAMESPACE: DOMINIO

Categoria funzionale/tematica. Sono i **chip cliccabili nell'editor UI**.
Ogni oggetto deve averne almeno uno.

### Abbigliamento e accessori
| Tag             | Oggetti tipici                                              |
|-----------------|-------------------------------------------------------------|
| `abbigliamento` | Vestiti, guanti, maschere protettive, tute                  |
| `accessorio`    | Occhiali, borse, spille, pendenti, oggetti indossabili      |
| `calzatura`     | Scarpe, stivali, sandali, pantofole, pattini, infradito     |
| `cappello`      | Cappelli, berretti, elmetti, copricapi in genere            |
| `gioiello`      | Anelli, collane, bracciali, amuleti preziosi                |
| `orologio`      | Orologi da polso, da tavolo, sveglie, orologi a pendolo     |

### Armi e strumenti
| Tag         | Oggetti tipici                                                |
|-------------|---------------------------------------------------------------|
| `arma`      | Spade, pistole, coltelli, asce, mazze, fruste offensive       |
| `attrezzo`  | Utensili manuali: martelli, pinze, righelli, cacciaviti       |
| `officina`  | Attrezzatura da officina: trapani, saldatori, morse, calibri  |
| `chiave`    | Chiavi di ogni tipo (del porta, antiche, magiche)             |

### Cucina e cibo
| Tag       | Oggetti tipici                                                  |
|-----------|-----------------------------------------------------------------|
| `cucina`  | Pentole, coltelli da cucina, utensili culinari, elettrodomestici|
| `cibo`    | Alimenti solidi: frutta, pane, carne, pizza, dolci, salumi      |
| `bevanda` | Liquidi potabili, bottiglie piene, tazze con contenuto          |
| `salume`  | Salumi italiani: prosciutto, salame, mortadella, speck          |
| `dolce`   | Dolciumi: torte, caramelle, gelati, biscotti, cioccolato        |
| `salato`  | Snack salati: patatine, pretzel, crackers, noccioline           |

### Casa e arredamento
| Tag            | Oggetti tipici                                               |
|----------------|--------------------------------------------------------------|
| `arredamento`  | Mobili, specchi, cornici, cuscini, oggetti d'arredo fissi    |
| `decorazione`  | Oggetti decorativi senza funzione pratica primaria           |
| `casa`         | Oggetti domestici generici non classificabili altrove        |
| `luce`         | Lampade, lanterne, candele accese, torce, proiettori         |
| `pulizia`      | Scope, spugne, detergenti, mop, secchi                       |
| `bagno`        | Oggetti igienici: rasoio, spazzolino, sapone, asciugamano    |
| `giardino`     | Attrezzi da giardinaggio, piante in vaso, gnomi, fontane     |

### Tecnologia ed elettronica
| Tag             | Oggetti tipici                                              |
|-----------------|-------------------------------------------------------------|
| `elettronica`   | Dispositivi elettronici: computer, chip, console, sensori   |
| `tecnologia`    | Oggetti tecnici moderni o meccanici avanzati (più ampio)    |
| `comunicazione` | Telefoni, radio, walkie-talkie, citofoni                    |
| `dati`          | Supporti dati: floppy, USB, CD, hard disk, schede memoria   |
| `audio`         | Cuffie, speaker, microfoni, walkman, cassette audio         |
| `video`         | VHS, DVD, proiettori, display, webcam                       |

> **Differenza `elettronica` vs `tecnologia`**: `elettronica` = il dispositivo
> ha circuiti. `tecnologia` = oggetto dell'era tecnologica moderna (include
> meccanici avanzati, digitali, informatici). Spesso coesistono.

### Giochi e intrattenimento
| Tag                 | Oggetti tipici                                            |
|---------------------|-----------------------------------------------------------|
| `gioco`             | Giochi da tavolo, carte da gioco, dadi, puzzle, ouija     |
| `giocattolo`        | Giocattoli: pupazzi, peluche, action figure, modellini    |
| `videogame`         | Console, controller, cartucce, accessori gaming           |
| `carte_da_gioco`    | Mazzi di carte: poker, tarocchi, UNO, magic               |
| `carta_individuale` | Singola carta estratta da un mazzo                        |
| `slot`              | Slot machine, ruote della roulette, componenti da casinò  |
| `casinò`            | Oggetti da casinò: fiches, tavoli, segnalatori            |
| `sport`             | Attrezzatura sportiva: racchette, palloni, pesi, trofei   |
| `collezione`        | Oggetti da collezione: modellini, edizioni limitate       |
| `modello`           | Modellini in scala: aerei, navi, auto, treni              |

### Arte, cultura, media
| Tag       | Oggetti tipici                                                  |
|-----------|-----------------------------------------------------------------|
| `arte`    | Pennelli, palette, tele, sculture, strumenti creativi           |
| `musica`  | Strumenti musicali, vinili, partiture, cuffie da DJ             |
| `cinema`  | Pellicole, ciak, proiettori, DVD                                |
| `fumetti` | Albi a fumetti, manga, gadget supereroi, trading card           |
| `poster`  | Poster, manifesti, locandine                                    |
| `foto`    | Fotografie, macchine fotografiche, album, polaroid              |
| `maschera`| Maschere: veneziane, di carnevale, teatrali, horror             |

### Ufficio e studio
| Tag      | Oggetti tipici                                                    |
|----------|-------------------------------------------------------------------|
| `ufficio`| Cancelleria: penne, graffette, pinzatrici, stampante              |
| `studio` | Libri, atlanti, globi, dizionari, oggetti da biblioteca           |

### Medico
| Tag      | Oggetti tipici                                                    |
|----------|-------------------------------------------------------------------|
| `medico` | Strumenti medici, siringhe, garze, kit pronto soccorso, mascherine|

### Viaggio e trasporti
| Tag        | Oggetti tipici                                                |
|------------|---------------------------------------------------------------|
| `viaggio`  | Valigie, bussole, mappe, zaini, borracce, tende da campo      |
| `veicolo`  | Veicoli o loro componenti: auto, bici, moto                   |

### Simboli, denaro, segnaletica
| Tag           | Oggetti tipici                                              |
|---------------|-------------------------------------------------------------|
| `simbolo`     | Simboli, stemmi, amuleti, icone grafiche (pace, yin-yang)   |
| `denaro`      | Monete, banconote, portafogli, salvadanai, casse            |
| `bandiera`    | Bandiere nazionali o simboliche                             |
| `nazione`     | Oggetti simbolo di una nazione specifica                    |
| `segnaletica` | Cartelli stradali, segnali di pericolo, indicatori          |
| `tradizione`  | Oggetti della tradizione locale o folkloristica             |

---

## NAMESPACE: TEMA

Estetica narrativa prevalente. Visibili come chip secondari.

| Tag        | Definizione precisa                                                  |
|------------|----------------------------------------------------------------------|
| `horror`   | Oggetti inquietanti, legati al terrore o al mistero                  |
| `vintage`  | Estetica **pre-anni '60**: antico, vittoriano, art déco, coloniale   |
| `retro`    | Estetica **anni '60–'90**: nostalgia pop, retrocomputing, VHS        |
| `scifi`    | Fantascienza: futuro, spazio, robot, alieni, distopia                |
| `noir`     | Estetica noir: ombra, detective, anni '40–'50, fumo                  |
| `cult`     | Oggetti iconici di cultura pop o cult classics                       |
| `pop`      | Cultura pop contemporanea: mainstream, colorato                      |
| `fantasy`  | Oggetti fantastici: magia, draghi, armi medievali, elfi              |
| `circo`    | Estetica circense: clown, acrobati, magia di scena                   |
| `oceano`   | Oggetti marini, navali, subacquei, pirati                            |
| `isometrico`| Oggetti rappresentati in prospettiva isometrica (tag tecnico)       |

> **`vintage` vs `retro`**: `vintage` per oggetti genuinamente antichi
> (pre-1960). `retro` per nostalgia degli anni '60–'90 (floppy, VHS, walkman,
> controller SNES). Mai usarli entrambi sullo stesso oggetto.

> **Nota**: `mistero` è stato unificato in `horror` (v1.2).

---

## NAMESPACE: MOOD

Attributi emotivi o qualitativi.

| Tag             | Uso                                                           |
|-----------------|---------------------------------------------------------------|
| `pericolo`      | Oggetto pericoloso o che evoca rischio immediato              |
| `occulto`       | Esoterico, legato a rituali o simboli segreti                 |
| `magia`         | Oggetto magico o con proprietà soprannaturali                 |
| `prezioso`      | Oggetto di valore elevato, raro o pregiato                    |
| `rotto`         | Oggetto danneggiato, consumato, arrugginito, usurato          |
| `variante`      | Variante estetica di un oggetto già presente nel catalogo     |
| `gruppo_oggetti`| Oggetto che rappresenta visivamente un insieme di elementi    |

> **Nota**: `macabro` rimosso (v1.2) — era sempre co-presente con `horror`.

---

## NAMESPACE: NATURA

Per esseri viventi, piante, funghi, oggetti del mondo naturale.

| Tag        | Uso                                                            |
|------------|----------------------------------------------------------------|
| `natura`   | Oggetti naturali in generale: piante, rocce, elementi outdoor  |
| `biologico`| Materiale organico: parti corporee, tessuti, materia organica  |
| `insetto`  | Insetti e artropodi                                            |
| `vola`     | Animali o oggetti capaci di volare                             |
| `bosco`    | Oggetti del bosco: ghiande, pigne, nidi, funghi boschivi       |
| `abisso`   | Oggetti delle profondità oceaniche                             |

---

## NAMESPACE: GEOGRAFIA

Origine geografica o culturale. Usare solo quando è un tratto identificativo rilevante.

| Tag             | Uso                                                |
|-----------------|----------------------------------------------------|
| `europa`        | Europa (include tutti i paesi europei)             |
| `nordamerica`   | USA, Canada                                        |
| `sudamerica`    | America del Sud                                    |
| `centroamerica` | America Centrale                                   |
| `caraibi`       | Cultura caraibica                                  |
| `orientale`     | Asia: Giappone, Cina, India, Medio Oriente         |
| `nordico`       | Scandinavia, culture nordiche                      |

> **Regola**: NON aggiungere paesi specifici (italia, francia, ecc.) come tag.
> Usa sempre la macro-area (`europa`). Se l'oggetto è chiaramente di un paese
> specifico, aggiungi `tradizione` + la macro-area.

---

## NAMESPACE: COLORE

**Solo quando il colore è il tratto identificativo primario** dell'oggetto
(es. "dado rosso" distinto da "dado blu"). Non taggare colori per oggetti
monocromatici standard (una moneta d'oro non ha bisogno di `giallo`).

| `rosso` | `verde` | `blu` | `giallo` | `nero` | `bianco` | `arancione` | `viola` | `cyan` | `rosa` | `marrone` | `argento` |

---

## Tag tecnici interni

Tag a bassa frequenza per disambiguare. Non creare nuovi tag di questo tipo
senza consultare il team.

| Tag                | Oggetti | Significato                                       |
|--------------------|---------|---------------------------------------------------|
| `carta_individuale`| ~53     | Singola carta da gioco                            |
| `volante`          | 2       | Drone/oggetto volante                             |
| `mouse`            | 2       | Mouse da computer                                 |
| `tablet`           | 2       | Tablet digitale                                   |
| `tastiera`         | 3       | Tastiera da computer                              |
| `visore`           | 2       | Visore VR                                         |
| `geometria`        | 9       | Forme geometriche pure (tetramino, cubi)          |
| `minerale`         | 2       | Frammenti minerali/rocce                          |
| `fumo`             | 7       | Accessori per fumatori: pipe, sigari, accendini   |
| `prigione`         | 1       | Oggetti di contenzione/prigionia                  |
| `lento`            | 1       | Animali lenti (lumaca)                            |
| `notturno`         | 1       | Animali notturni (pipistrello)                    |
| `mimetico`         | 1       | Animali mimetici (camaleonte)                     |
| `abisso`           | 7       | Oggetti delle profondità marine                   |

---

## Come aggiungere correttamente i tag a un nuovo oggetto

**Step 1 — Identifica il DOMINIO**
Apri [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json) e trova
il namespace `dominio`. Scegli il tag più specifico che descrive cosa FA o
COSA È l'oggetto. Esempi: un coltello da cucina → `cucina` + `arma`;
un globo → `studio` + `arredamento`.

**Step 2 — Identifica DIMENSIONE e MATERIALE**
- `piccolo` / `medio` / `grande` in base al radius/dimensioni nel JSON
- Uno o più tag materiale (es. `metallo` + `legno` per un martello)

**Step 3 — Aggiungi TEMA/MOOD se evidenti**
Solo se l'oggetto ha un'estetica o mood chiaro:
- Un teschio di cera → `horror`
- Un walkman → `retro`
- Una spada medievale → `fantasy` + `vintage`

**Step 4 — Verifica di non creare tag orfani**
```bash
python -X utf8 tools/audit_catalog.py
```

**Step 5 — JSON finale**
```json
{
  "id": "my_new_object",
  "label_key": "obj_my_new_object",
  "tags": ["dominio1", "dominio2", "materiale1", "tema1", "piccolo"]
}
```

---

## Come creare un nuovo tag (solo se strettamente necessario)

Un nuovo tag è giustificato **solo se**:
1. Descrive una categoria che non rientra in nessun tag esistente
2. Verrà usato su **almeno 3 oggetti distinti**
3. Non è sinonimo o sottoinsieme di un tag già esistente

**Procedura**:

1. **Verifica che non esista già**: consulta le tabelle sopra
2. **Scegli il namespace corretto**: in quale delle 8 categorie rientra?
3. **Scegli il nome in italiano**, minuscolo, senza spazi (usa `_` se composto)
4. **Aggiorna [engine/data/tags_taxonomy.json](../engine/data/tags_taxonomy.json)**: aggiungi il tag al namespace corretto con descrizione
5. **Aggiorna questo documento**: aggiungi il tag alla tabella del namespace
6. **Aggiorna `CHIP_TAG_HIDDEN`** in [editor/mixins/render_panels.py](../editor/mixins/render_panels.py) se il tag deve essere nascosto dai chip UI
7. **Applica retroattivamente** a tutti gli oggetti esistenti che meritano il nuovo tag

**NON creare tag per**:
- Singole nazioni europee specifiche (usa `europa` + `tradizione`)
- Sottospecifiche di materiali già presenti (es. `acciaio` se esiste `metallo`)
- Oggetti singoli (se solo un oggetto lo userebbe)
- Qualità sensoriali soggettive (es. `morbido`, `pesante`)
- Nomi di brand o modelli specifici (es. `nike`, `ferrari`)

---

## Tool di manutenzione

Tutti in [tools/](../tools/):

```bash
# Audit completo: statistiche, tag orfani, oggetti sotto-taggati
python -X utf8 tools/audit_catalog.py

# Migrazione tag (merge/rename)
python -X utf8 tools/tag_migrate.py --dry-run   # anteprima
python -X utf8 tools/tag_migrate.py             # applica con backup

# Aggiunta tag mancanti a oggetti specifici
python -X utf8 tools/tag_fix_pass2.py --dry-run
python -X utf8 tools/tag_fix_pass2.py
```

Per aggiungere un merge/rename a `tag_migrate.py`, aggiungi una riga a `MERGE_MAP`:
```python
"vecchio_tag": "nuovo_tag",   # o None per rimuoverlo
```

Per aggiungere tag mancanti a oggetti specifici, modifica `ADD_TAGS` in `tag_fix_pass2.py`:
```python
"id_oggetto": ["tag_da_aggiungere_1", "tag_da_aggiungere_2"],
```

---

## Esempi

### Oggetto ben taggato

```json
{
  "id": "skull_candle",
  "label_key": "obj_skull_candle",
  "tags": ["cera", "decorazione", "horror", "luce", "medio", "osso"]
}
```

Breakdown:
- `decorazione` → **DOMINIO** (cosa è: un oggetto decorativo)
- `luce` → **DOMINIO** secondario (funzione: emette luce)
- `horror` → **TEMA** (estetica e tono emotivo)
- `osso`, `cera` → **MATERIALE** (di cosa è fatto)
- `medio` → **DIMENSIONE** (nascosto dai chip UI)

### Oggetto mal taggato (da evitare)

```json
{
  "id": "ritual_dagger",
  "tags": ["arma", "horror", "medio", "mistero", "occulto", "tecnologia"]
}
```

Problemi: `tecnologia` su un pugnale rituale è semanticamente sbagliato;
`mistero` e `macabro` sono ora unificati in `horror`.

Corretto:

```json
{
  "id": "ritual_dagger",
  "tags": ["arma", "horror", "medio", "metallo", "occulto"]
}
```

---

## Statistiche correnti (aggiornate 2026-04-20, v1.3)

| Metrica                    | raw       | v1.1        | v1.2        | v1.3        |
|----------------------------|-----------|-------------|-------------|-------------|
| Oggetti totali             | 1084      | 1084        | 1118        | **1127**    |
| Tag istanze totali         | 5087      | 5396        | 5484        | **5430**    |
| Tag unici                  | 372       | 301         | 299         | **205**     |
| Media tag per oggetto      | 4.69      | 4.98        | 4.91        | **4.82**    |

**v1.3 Cleanup**: Rimozione aggressiva di 94 tag ridondanti/nomi (ascia, coltello,
candela, ventilatore, sinonimi come ciliegie→frutta, bowling→palla,
nani→gnomo). Mantiene solo tag categorizzanti. Fix: `lipstick` ha ora
`accessorio`+`cosmetico` (non `abbigliamento`).
