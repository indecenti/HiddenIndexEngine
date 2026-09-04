# Tag Taxonomy - Canonical Reference

> **Source file (source of truth)**: [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json)
> This document is the operating guide; the JSON is authoritative.

The tag system is the heart of smart navigation in the editor's OBJ tab.
Every object has **multiple tags** organized in semantic namespaces (not hierarchical).

> **Note on naming**: tag identifiers are Italian words (`piccolo`, `metallo`, `cucina`, ...)
> for historical reasons: they are data keys used in every catalog and localized in the
> editor UI through `tag_<id>` strings. Do not translate existing identifiers; new tags
> follow the same convention for consistency.

---

## Principle: namespaces, not levels

Tags belong to a typed namespace:

| Namespace     | Required?        | Description                                              |
|---------------|------------------|----------------------------------------------------------|
| `DIMENSIONE`  | **Always**       | Physical size of the object in the game                  |
| `MATERIALE`   | **Always**       | Prevailing material of the object                        |
| `DOMINIO`     | **Always**       | Functional/thematic category                             |
| `TEMA`        | If applicable    | Predominant narrative aesthetic                          |
| `MOOD`        | If applicable    | Emotional or qualitative attribute                       |
| `NATURA`      | Natural/bio only | Objects of the natural world                             |
| `GEOGRAFIA`   | If relevant      | Cultural/geographic origin                               |
| `COLORE`      | Only if defining | Dominant color, only when it is the identifying trait    |

**Golden rule**: every object must have at least one tag from DIMENSIONE, one from MATERIALE
and one from DOMINIO (or NATURA if it is a living being/plant).

---

## NAMESPACE: DIMENSIONE (size)

Technical tags hidden from the UI chips but present in the JSON and searchable.

| Tag       | Approximate threshold                              |
|-----------|----------------------------------------------------|
| `piccolo` | Radius < 25 px or side < 40 px                     |
| `medio`   | Radius 25–50 px or side 40–90 px                   |
| `grande`  | Radius > 50 px or side > 90 px                     |

---

## NAMESPACE: MATERIALE (material)

Prevailing material. An object can have more than one if composite.

| Tag        | Typical use                                                  |
|------------|--------------------------------------------------------------|
| `metallo`  | Iron, steel, aluminum, copper, brass, gold, silver           |
| `legno`    | Raw or worked wood, plywood                                  |
| `carta`    | Paper, cardboard, card stock, books, posters                 |
| `plastica` | Synthetic polymers, resins, PVC                              |
| `vetro`    | Glass, transparent crystal, mirrors                          |
| `stoffa`   | Fabric, canvas, padding, felt                                |
| `ceramica` | Ceramic, terracotta, porcelain, majolica                     |
| `gomma`    | Natural or synthetic rubber, latex, silicone                 |
| `cuoio`    | Tanned hide, worked leather (belts, saddles, bags)           |
| `pietra`   | Stone, marble, minerals, fossils, meteorites                 |
| `cristallo`| Crystal, gems, transparent quartz                            |
| `cera`     | Beeswax, paraffin, candles                                   |
| `osso`     | Bones, ivory, animal horn, teeth                             |
| `biologico`| Non-animal organic material or biological parts              |

> **Note**: `pelle` (skin/flesh) stays distinct from `cuoio` (worked leather).
> Use `cuoio` for leather accessories, `biologico` + `pelle` for horror body parts.

---

## NAMESPACE: DOMINIO (domain)

Functional/thematic category. These are the **clickable chips in the editor UI**.
Every object must have at least one.

### Clothing and accessories
| Tag             | Typical objects                                             |
|-----------------|-------------------------------------------------------------|
| `abbigliamento` | Clothes, gloves, protective masks, suits                    |
| `accessorio`    | Glasses, bags, brooches, pendants, wearable objects         |
| `calzatura`     | Shoes, boots, sandals, slippers, skates, flip-flops         |
| `cappello`      | Hats, caps, helmets, headwear in general                    |
| `gioiello`      | Rings, necklaces, bracelets, precious amulets               |
| `orologio`      | Wristwatches, table clocks, alarm clocks, pendulum clocks   |

### Weapons and tools
| Tag         | Typical objects                                               |
|-------------|---------------------------------------------------------------|
| `arma`      | Swords, guns, knives, axes, maces, offensive whips            |
| `attrezzo`  | Hand tools: hammers, pliers, rulers, screwdrivers             |
| `officina`  | Workshop equipment: drills, welders, vises, calipers          |
| `chiave`    | Keys of every kind (door, antique, magic)                     |

### Kitchen and food
| Tag       | Typical objects                                                 |
|-----------|-----------------------------------------------------------------|
| `cucina`  | Pots, kitchen knives, cooking utensils, appliances              |
| `cibo`    | Solid food: fruit, bread, meat, pizza, sweets, cured meats      |
| `bevanda` | Drinkable liquids, full bottles, cups with content              |
| `salume`  | Italian cured meats: prosciutto, salami, mortadella, speck      |
| `dolce`   | Sweets: cakes, candy, ice cream, biscuits, chocolate            |
| `salato`  | Savory snacks: chips, pretzels, crackers, peanuts               |

### Home and furnishing
| Tag            | Typical objects                                              |
|----------------|--------------------------------------------------------------|
| `arredamento`  | Furniture, mirrors, frames, cushions, fixed decor            |
| `decorazione`  | Decorative objects without a primary practical function      |
| `casa`         | Generic household objects not classifiable elsewhere         |
| `luce`         | Lamps, lanterns, lit candles, torches, projectors            |
| `pulizia`      | Brooms, sponges, detergents, mops, buckets                   |
| `bagno`        | Hygiene objects: razor, toothbrush, soap, towel              |
| `giardino`     | Gardening tools, potted plants, gnomes, fountains            |

### Technology and electronics
| Tag             | Typical objects                                             |
|-----------------|-------------------------------------------------------------|
| `elettronica`   | Electronic devices: computers, chips, consoles, sensors     |
| `tecnologia`    | Modern technical or advanced mechanical objects (broader)   |
| `comunicazione` | Phones, radios, walkie-talkies, intercoms                   |
| `dati`          | Data media: floppy disks, USB sticks, CDs, hard disks, memory cards |
| `audio`         | Headphones, speakers, microphones, walkmans, audio cassettes|
| `video`         | VHS, DVD, projectors, displays, webcams                     |

> **`elettronica` vs `tecnologia`**: `elettronica` = the device has circuits.
> `tecnologia` = an object of the modern technological era (includes advanced
> mechanical, digital, computing). They often coexist.

### Games and entertainment
| Tag                 | Typical objects                                           |
|---------------------|-----------------------------------------------------------|
| `gioco`             | Board games, playing cards, dice, puzzles, ouija          |
| `giocattolo`        | Toys: dolls, plush toys, action figures, models           |
| `videogame`         | Consoles, controllers, cartridges, gaming accessories     |
| `carte_da_gioco`    | Card decks: poker, tarot, UNO, magic                      |
| `carta_individuale` | A single card taken from a deck                           |
| `slot`              | Slot machines, roulette wheels, casino components         |
| `casinò`            | Casino objects: chips, tables, markers                    |
| `sport`             | Sports equipment: rackets, balls, weights, trophies       |
| `collezione`        | Collectibles: models, limited editions                    |
| `modello`           | Scale models: planes, ships, cars, trains                 |

### Art, culture, media
| Tag       | Typical objects                                                 |
|-----------|-----------------------------------------------------------------|
| `arte`    | Brushes, palettes, canvases, sculptures, creative tools         |
| `musica`  | Musical instruments, vinyl records, sheet music, DJ headphones  |
| `cinema`  | Film reels, clapperboards, projectors, DVDs                     |
| `fumetti` | Comic books, manga, superhero gadgets, trading cards            |
| `poster`  | Posters, bills, playbills                                       |
| `foto`    | Photographs, cameras, albums, polaroids                         |
| `maschera`| Masks: Venetian, carnival, theatrical, horror                   |

### Office and study
| Tag      | Typical objects                                                   |
|----------|-------------------------------------------------------------------|
| `ufficio`| Stationery: pens, paper clips, staplers, printer                  |
| `studio` | Books, atlases, globes, dictionaries, library objects             |

### Medical
| Tag      | Typical objects                                                   |
|----------|-------------------------------------------------------------------|
| `medico` | Medical instruments, syringes, gauze, first-aid kits, face masks  |

### Travel and transport
| Tag        | Typical objects                                               |
|------------|---------------------------------------------------------------|
| `viaggio`  | Suitcases, compasses, maps, backpacks, canteens, tents        |
| `veicolo`  | Vehicles or their parts: cars, bikes, motorcycles             |

### Symbols, money, signage
| Tag           | Typical objects                                             |
|---------------|-------------------------------------------------------------|
| `simbolo`     | Symbols, crests, amulets, graphic icons (peace, yin-yang)   |
| `denaro`      | Coins, banknotes, wallets, piggy banks, cash boxes          |
| `bandiera`    | National or symbolic flags                                  |
| `nazione`     | Objects symbolizing a specific nation                       |
| `segnaletica` | Road signs, danger signs, indicators                        |
| `tradizione`  | Objects of local tradition or folklore                      |

---

## NAMESPACE: TEMA (theme)

Prevailing narrative aesthetic. Visible as secondary chips.

| Tag        | Precise definition                                                   |
|------------|----------------------------------------------------------------------|
| `horror`   | Disturbing objects, tied to terror or mystery                        |
| `vintage`  | **Pre-1960s** aesthetic: antique, Victorian, art deco, colonial      |
| `retro`    | **1960s–1990s** aesthetic: pop nostalgia, retrocomputing, VHS        |
| `scifi`    | Science fiction: future, space, robots, aliens, dystopia             |
| `noir`     | Noir aesthetic: shadow, detectives, 1940s–1950s, smoke               |
| `cult`     | Iconic pop-culture objects or cult classics                          |
| `pop`      | Contemporary pop culture: mainstream, colorful                       |
| `fantasy`  | Fantastic objects: magic, dragons, medieval weapons, elves           |
| `circo`    | Circus aesthetic: clowns, acrobats, stage magic                      |
| `oceano`   | Marine, naval, underwater, pirate objects                            |
| `isometrico`| Objects drawn in isometric perspective (technical tag)              |

> **`vintage` vs `retro`**: `vintage` for genuinely old objects
> (pre-1960). `retro` for 1960s–1990s nostalgia (floppy disks, VHS, walkmans,
> SNES controllers). Never use both on the same object.

> **Note**: `mistero` was merged into `horror` (v1.2).

---

## NAMESPACE: MOOD

Emotional or qualitative attributes.

| Tag             | Use                                                           |
|-----------------|---------------------------------------------------------------|
| `pericolo`      | Dangerous object or one that evokes immediate risk            |
| `occulto`       | Esoteric, tied to rituals or secret symbols                   |
| `magia`         | Magical object or one with supernatural properties            |
| `prezioso`      | High-value, rare or fine object                               |
| `rotto`         | Damaged, worn, rusty, used-up object                          |
| `variante`      | Aesthetic variant of an object already in the catalog         |
| `gruppo_oggetti`| Object that visually represents a set of items                |

> **Note**: `macabro` removed (v1.2) — it always co-occurred with `horror`.

---

## NAMESPACE: NATURA (nature)

For living beings, plants, fungi, objects of the natural world.

| Tag        | Use                                                            |
|------------|----------------------------------------------------------------|
| `natura`   | Natural objects in general: plants, rocks, outdoor elements    |
| `biologico`| Organic material: body parts, tissues, organic matter          |
| `insetto`  | Insects and arthropods                                         |
| `vola`     | Animals or objects able to fly                                 |
| `bosco`    | Forest objects: acorns, pine cones, nests, forest mushrooms    |
| `abisso`   | Objects of the ocean depths                                    |

---

## NAMESPACE: GEOGRAFIA (geography)

Geographic or cultural origin. Use only when it is a relevant identifying trait.

| Tag             | Use                                                |
|-----------------|----------------------------------------------------|
| `europa`        | Europe (includes every European country)           |
| `nordamerica`   | USA, Canada                                        |
| `sudamerica`    | South America                                      |
| `centroamerica` | Central America                                    |
| `caraibi`       | Caribbean culture                                  |
| `orientale`     | Asia: Japan, China, India, Middle East             |
| `nordico`       | Scandinavia, Nordic cultures                       |

> **Rule**: do NOT add specific countries (italia, francia, etc.) as tags.
> Always use the macro-area (`europa`). If the object clearly belongs to a
> specific country, add `tradizione` + the macro-area.

---

## NAMESPACE: COLORE (color)

**Only when the color is the primary identifying trait** of the object
(e.g. "red die" as opposed to "blue die"). Do not tag colors for standard
monochrome objects (a gold coin does not need `giallo`).

| `rosso` | `verde` | `blu` | `giallo` | `nero` | `bianco` | `arancione` | `viola` | `cyan` | `rosa` | `marrone` | `argento` |

---

## Internal technical tags

Low-frequency tags used for disambiguation. Do not create new tags of this kind
without consulting the team.

| Tag                | Objects | Meaning                                           |
|--------------------|---------|---------------------------------------------------|
| `carta_individuale`| ~53     | Single playing card                               |
| `volante`          | 2       | Drone/flying object                               |
| `mouse`            | 2       | Computer mouse                                    |
| `tablet`           | 2       | Digital tablet                                    |
| `tastiera`         | 3       | Computer keyboard                                 |
| `visore`           | 2       | VR headset                                        |
| `geometria`        | 9       | Pure geometric shapes (tetrominoes, cubes)        |
| `minerale`         | 2       | Mineral fragments/rocks                           |
| `fumo`             | 7       | Smoking accessories: pipes, cigars, lighters      |
| `prigione`         | 1       | Restraint/imprisonment objects                    |
| `lento`            | 1       | Slow animals (snail)                              |
| `notturno`         | 1       | Nocturnal animals (bat)                           |
| `mimetico`         | 1       | Camouflaging animals (chameleon)                  |
| `abisso`           | 7       | Objects of the deep sea                           |

---

## How to tag a new object correctly

**Step 1 — Identify the DOMAIN**
Open [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json) and find
the `dominio` namespace. Pick the most specific tag describing what the object DOES or
WHAT it IS. Examples: a kitchen knife -> `cucina` + `arma`;
a globe -> `studio` + `arredamento`.

**Step 2 — Identify SIZE and MATERIAL**
- `piccolo` / `medio` / `grande` based on the radius/dimensions in the JSON
- One or more material tags (e.g. `metallo` + `legno` for a hammer)

**Step 3 — Add THEME/MOOD if evident**
Only if the object has a clear aesthetic or mood:
- A wax skull -> `horror`
- A walkman -> `retro`
- A medieval sword -> `fantasy` + `vintage`

**Step 4 — Check that you are not creating orphan tags**
```bash
python -X utf8 tools/audit_catalog.py
```

**Step 5 — Final JSON**
```json
{
  "id": "my_new_object",
  "label_key": "obj_my_new_object",
  "tags": ["domain1", "domain2", "material1", "theme1", "piccolo"]
}
```

---

## How to create a new tag (only if strictly necessary)

A new tag is justified **only if**:
1. It describes a category that fits no existing tag
2. It will be used on **at least 3 distinct objects**
3. It is not a synonym or subset of an existing tag

**Procedure**:

1. **Check that it does not exist already**: consult the tables above
2. **Pick the right namespace**: which of the 8 categories does it belong to?
3. **Pick the identifier following the existing convention** (Italian word, lowercase, no spaces, `_` for compounds)
4. **Update [engine/data/tags_taxonomy.json](../../engine/data/tags_taxonomy.json)**: add the tag to the right namespace with a description
5. **Update this document**: add the tag to the namespace table
6. **Update `CHIP_TAG_HIDDEN`** in [editor/mixins/render_panels.py](../../editor/mixins/render_panels.py) if the tag must be hidden from the UI chips
7. **Apply it retroactively** to every existing object that deserves the new tag

**Do NOT create tags for**:
- Single specific European nations (use `europa` + `tradizione`)
- Sub-specifications of existing materials (e.g. `acciaio` when `metallo` exists)
- Single objects (if only one object would use it)
- Subjective sensory qualities (e.g. `morbido`, `pesante`)
- Brand or specific model names (e.g. `nike`, `ferrari`)

---

## Maintenance tools

All in [tools/](../../tools/):

```bash
# Full audit: statistics, orphan tags, under-tagged objects
python -X utf8 tools/audit_catalog.py

# Tag migration (merge/rename)
python -X utf8 tools/tag_migrate.py --dry-run   # preview
python -X utf8 tools/tag_migrate.py             # apply with backup

# Add missing tags to specific objects
python -X utf8 tools/tag_fix_pass2.py --dry-run
python -X utf8 tools/tag_fix_pass2.py
```

To add a merge/rename to `tag_migrate.py`, add a line to `MERGE_MAP`:
```python
"old_tag": "new_tag",   # or None to remove it
```

To add missing tags to specific objects, edit `ADD_TAGS` in `tag_fix_pass2.py`:
```python
"object_id": ["tag_to_add_1", "tag_to_add_2"],
```

---

## Examples

### Well-tagged object

```json
{
  "id": "skull_candle",
  "label_key": "obj_skull_candle",
  "tags": ["cera", "decorazione", "horror", "luce", "medio", "osso"]
}
```

Breakdown:
- `decorazione` -> **DOMINIO** (what it is: a decorative object)
- `luce` -> secondary **DOMINIO** (function: it emits light)
- `horror` -> **TEMA** (aesthetic and emotional tone)
- `osso`, `cera` -> **MATERIALE** (what it is made of)
- `medio` -> **DIMENSIONE** (hidden from the UI chips)

### Badly tagged object (to avoid)

```json
{
  "id": "ritual_dagger",
  "tags": ["arma", "horror", "medio", "mistero", "occulto", "tecnologia"]
}
```

Problems: `tecnologia` on a ritual dagger is semantically wrong;
`mistero` and `macabro` are now merged into `horror`.

Correct:

```json
{
  "id": "ritual_dagger",
  "tags": ["arma", "horror", "medio", "metallo", "occulto"]
}
```

---

## Current statistics (updated 2026-04-20, v1.3)

| Metric                     | raw       | v1.1        | v1.2        | v1.3        |
|----------------------------|-----------|-------------|-------------|-------------|
| Total objects              | 1084      | 1084        | 1118        | **1127**    |
| Total tag instances        | 5087      | 5396        | 5484        | **5430**    |
| Unique tags                | 372       | 301         | 299         | **205**     |
| Average tags per object    | 4.69      | 4.98        | 4.91        | **4.82**    |

**v1.3 cleanup**: aggressive removal of 94 redundant/name tags (ascia, coltello,
candela, ventilatore, synonyms such as ciliegie->frutta, bowling->palla,
nani->gnomo). Only categorizing tags are kept. Fix: `lipstick` now has
`accessorio`+`cosmetico` (not `abbigliamento`).
