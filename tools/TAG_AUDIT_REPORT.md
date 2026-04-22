# Tag Audit Report — 2026-04-20

## Stato post-migrazione

| Metrica | Prima | Dopo | Δ |
|---------|-------|------|---|
| Oggetti | 1084 | 1084 | — |
| Tag istanze totali | 5087 | 4993 | -94 |
| Tag unici | 372 | 301 | **-71** |
| Media tag/oggetto | 4.69 | 4.61 | -0.08 |

---

## Cosa è stato applicato

### Fix encoding/lingua
| Vecchio | Nuovo | Oggetti |
|---------|-------|---------|
| `casin\ufffd` (corrotto) | `casinò` | 4 |
| `casino` (senza accento) | `casinò` | 4 |
| `game` (inglese) | `gioco` | 2 |
| `nature` (inglese) | `natura` | 1 |

### Sinonimi consolidati
| Vecchio | Nuovo | Oggetti |
|---------|-------|---------|
| `tech` | `elettronica` | 28 |
| `vestiti` | `abbigliamento` | 3 |
| `soldi` | `denaro` | 2 |
| `2000s` | `retro` | 9 |
| `quotidiano` | `giornale` | 1 |
| `accetta` | `ascia` | 1 |
| `scrivere` | `scrittura` | 1 |
| `meccanismo` | `meccanico` | 1 |
| `calza` | `calzino` | 1 |
| `piuma` | `piume` | 1 |
| `pop_art` | `arte` | 1 |
| `pennellessa` | `pennello` | 1 |
| `colorato` | `colore` | 1 |
| `ferro` | `metallo` | 1 |

### Categorie consolidate
| Vecchio | Nuovo | Oggetti |
|---------|-------|---------|
| `scarpa`, `stivale`, `ciabatta`, `pattini`, `infradito`, `pantofola`, `tacco` | `calzatura` | 17 |
| `fedora`, `giullare`, `cowboy`, `pompieri`, `panama`, `sherlock`, `bombetta`, `polizia`, `berretto` | `cappello` | 9 |
| Tutti i salumi specifici | `salume` | 9 |
| `italia`, `francia`, `germania`, `spagna`, `uk`, `grecia`, `svizzera`, `svezia` | `europa` | 8 |
| `foglia`, `fungo`, `seme`, `pigna`, `bacche`, `nido` | `biologico` | 6 |
| `porcellana` | `ceramica` | 1 |
| `marmo` | `pietra` | 2 |

### Materiale
| Vecchio | Nuovo | Note |
|---------|-------|------|
| `porcellana` | `ceramica` | sottoinsieme |
| `marmo` | `pietra` | sottoinsieme |
| `ferro` | `metallo` | sottoinsieme |

### Tag rimossi (privi di significato)
| Tag | Oggetti | Motivo |
|-----|---------|--------|
| `oggetto` | 9 | Tutto è un oggetto, tautologico |
| `parole` | 1 | Troppo vago |
| `culturale` | 1 | Troppo generico |

### Fix per-oggetto
| Oggetto | Tag rimosso | Motivo |
|---------|-------------|--------|
| `ritual_dagger` | `tecnologia` | Un pugnale rituale horror non è tecnologia |
| `chef_knife` | `tecnologia` | Coltello da cucina non è tecnologia |
| `cleaver` | `tecnologia` | Mannaia non è tecnologia |
| `pipe_wrench` | `tecnologia` | Chiave inglese non è tecnologia |
| `hammer` | `tecnologia` | Martello non è tecnologia |
| `horse_saddle` | `pelle` | Già taggato `cuoio`, ridondante |
| `whip_rolled` | `pelle` | Già taggato `cuoio`, ridondante |
| `obj_business_briefcase` | `pelle` | Già taggato `cuoio`, ridondante |
| `spray_can` | `bomboletta` | Già taggato `spray`, ridondante |

### Deduplicati
74 tag duplicati rimossi da singoli oggetti.

---

## Tassonomia canonica

La gerarchia completa è definita in `tools/tag_taxonomy.json`.

### Namespace e tag canonici

```
DIMENSIONE (3):     piccolo · medio · grande
MATERIALE (14):     metallo · legno · carta · plastica · vetro · stoffa · ceramica · 
                    gomma · cuoio · pietra · cristallo · cera · osso · biologico
DOMINIO (36):       abbigliamento · accessorio · calzatura · cappello · arma · attrezzo ·
                    elettronica · tecnologia · cucina · cibo · bevanda · salume · gioco ·
                    giocattolo · videogame · sport · musica · arte · arredamento · 
                    decorazione · viaggio · officina · medico · ufficio · studio · bagno ·
                    giardino · pulizia · comunicazione · veicolo · poster · bandiera · 
                    nazione · carte_da_gioco · carta_individuale · slot · casinò ·
                    fumetti · cinema · foto · dati · luce · colore · denaro · gioiello · orologio
TEMA (12):          horror · vintage · retro · scifi · noir · cult · pop · fantasy · 
                    mistero · circo · oceano · isometrico
MOOD (8):           pericolo · macabro · occulto · magia · prezioso · rotto · variante · gruppo_oggetti
NATURA (4):         natura · biologico · insetto · vola
GEOGRAFIA (6):      europa · nordamerica · sudamerica · centroamerica · orientale · nordico
COLORE (12):        rosso · verde · blu · giallo · nero · bianco · arancione · viola · 
                    cyan · rosa · marrone · argento
```

---

## Problemi residui (da valutare manualmente)

### Tag singleton (1 occorrenza) — 156 tag

Molti sono corretti e utili (oggetti unici nel catalogo). Quelli che potrebbero essere consolidati:

| Tag | Oggetto | Suggerimento |
|-----|---------|--------------|
| `alchimia` | `poison_bottle` | → merge in `occulto` o `magia` |
| `cappuccio` | `pen_cap_blue` | → rimuovere (non è un copricapo) |
| `spaghetti` | `spaghetti_pack` | → ridondante con `pasta` già presente |
| `frutta` | `cherries_pair` | → tieni `frutta`, valuta rimozione `ciliegie` |
| `fumo` | `cigarette_smoking` | → valuta se tenerlo distinto da `sigaretta` |
| `spirale` | `mosquito_coil` | → troppo generico come forma |
| `edificio` | `obj_horror_slot_gate` | → non adeguato come tag oggetto |
| `interfaccia` | `obj_slot_losing_x` | → non adeguato come tag oggetto |

### Tag con 2 occorrenze — 23 tag

La maggior parte sono corretti (es. `mouse` su 2 mouse diversi, `violino` non è qui ma `binocolo` su 2 binocoli diversi). Nessuna azione richiesta.

### `tecnologia` (133 occorrenze)

Dopo la rimozione dai 5 oggetti sbagliati, il tag rimane su 133 oggetti. La maggior parte sono corretti (gadget tech, dispositivi moderni). Verificare manualmente se ulteriori rimozioni sono necessarie con:

```bash
python3 -X utf8 -c "
import json
with open('engine/data/global_objects_catalog.json', encoding='utf-8') as f:
    data = json.load(f)
for o in data['objects']:
    if 'tecnologia' in o.get('tags', []) and 'elettronica' not in o.get('tags', []):
        print(o['id'], o['tags'])
"
```

---

## Strumenti disponibili

```bash
# Audit completo del catalogo corrente
python3 -X utf8 tools/tag_migrate.py --audit

# Dry-run di nuove migrazioni (dopo aver aggiornato MERGE_MAP nel file)
python3 -X utf8 tools/tag_migrate.py --dry-run

# Applica migrazione con backup automatico
python3 -X utf8 tools/tag_migrate.py

# Verbose (dettaglio per ogni oggetto modificato)
python3 -X utf8 tools/tag_migrate.py --dry-run --verbose
```
