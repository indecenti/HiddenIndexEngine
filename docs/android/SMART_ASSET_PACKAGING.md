# 📦 Smart Asset Packaging System

## Panoramica

Il sistema di build ora implementa **Smart Asset Packaging**: durante la creazione del package, pacchettizza **SOLO gli asset usati** dal gioco, minimizzando la dimensione del distributibile.

## Come Funziona

### 1️⃣ Analisi dei Livelli
```python
# Il build system legge tutti i scene.json
for scene in game/levels/*/scene.json:
    estrai object_id di ogni oggetto usato
    → set di "oggetti_usati"
```

### 2️⃣ Copia Intelligente degli Asset
```
Per ogni oggetto in oggetti_usati:
  Copia {object_id}.png da games/villa_segreta/objects/
  → Package finale contiene SOLO questi file

Esempio:
- Catalog ha 150 oggetti disponibili
- Scene usa 28 oggetti
- Package contiene SOLO 28 immagini (non 150!)
```

### 3️⃣ Catalog Centralizzato
```
engine/data/global_objects_catalog.json
  ↓
  Copiato nel package come engine/data/global_objects_catalog.json
  ↓
  Il gioco legge metadata di TUTTI gli oggetti
  (ma le icone PNG sono nel gioco, non nell'engine)
```

## Struttura Finale

### In Fase di Sviluppo (main.py)
```
HiddenIndexEngine/
├── engine/
│   ├── data/
│   │   ├── global_objects_catalog.json    ← Catalog centralizzato
│   │   └── ... (altre risorse engine)
│   └── ... (resto engine)
└── games/
    └── villa_segreta/
        ├── objects/                       ← Icone PNG (non copiate nel build!)
        │   ├── runed_skull.png
        │   ├── ritual_dagger.png
        │   └── ... (tutte le icone)
        ├── levels/
        │   └── level1_giardino/
        │       ├── scene1/scene.json     ← Specifica quali oggetti usa
        │       └── ...
        └── game_config.json
```

### Nel Package Finale (build)
```
build/villa_segreta/1.0/main/
├── main.exe
├── engine/
│   ├── data/
│   │   └── global_objects_catalog.json   ← Solo il catalog
│   └── ...
└── games/
    └── villa_segreta/
        ├── objects/                      ← SOLO gli asset USATI
        │   ├── runed_skull.png           ✓ Usato
        │   ├── ritual_dagger.png         ✓ Usato
        │   └── ... (28 file su 150)      ✓ Solo usati
        ├── levels/
        │   └── ...
        └── game_config.json
```

## Vantaggi

✅ **Pacchetti Piccoli**
- Riduciamo drasticamente le dimensioni
- Esempio: 150 icone (15 MB) → 28 icone (3 MB) = -80%

✅ **Funziona Ovunque**
- ✓ In sviluppo con `main.py` (accede a tutti gli asset)
- ✓ Nel build EXE (pacchettizza solo quello che serve)
- ✓ Scalabile a più giochi

✅ **Manutenzione Facile**
- Catalog centralizzato (metadata)
- Asset rimangono isolati nel gioco
- Aggiungere oggetti è semplice

✅ **Zero Breaking Changes**
- Continua a funzionare come prima
- Il build system è più intelligente (trasparente)

## Implementazione Tecnica

### Funzioni nel build_system.py

#### `_get_used_objects(game_path) → set[str]`
Analizza tutti i `scene.json` e ritorna gli object_id usati.

```python
used_objects = _get_used_objects(games_src)
# Risultato: {'runed_skull', 'ritual_dagger', 'oil_lantern', ...}
```

#### `_copy_smart_assets(games_src, games_dst, used_objects) → (count, size_mb)`
Copia solo gli asset usati.

```python
asset_count, asset_size_mb = _copy_smart_assets(
    games_src, 
    games_dst, 
    used_objects
)
# Risultato: (28, 3.5)  ← 28 file, 3.5 MB
```

## Logging nel Build

Quando fai una build, vedi:
```
[Smart Pack] Oggetti usati nel gioco: 28
[Smart Pack] Asset copiati: 28 file (3.5 MB)
[Copy] games/villa_segreta/ → main/ (4.2 MB)
```

## Scalabilità Futura

Se aggiungi un nuovo gioco:
```
games/
├── villa_segreta/
│   └── objects/        ← 150 icone (tutte)
└── nuovo_gioco/
    └── objects/        ← 45 icone (tutte)

Build villa_segreta  → Pacchetto con 28 icone
Build nuovo_gioco    → Pacchetto con 12 icone
(diversi per ogni gioco!)
```

## Note Importanti

⚠️ **Non modificare il catalog centralizzato durante lo sviluppo**
- Leggilo quando aggiungi nuovi oggetti
- Se aggiungi oggetti, aggiornalo prima

⚠️ **Gli asset PNG rimangono nel gioco**
- Non sono in `engine/data/objects/`
- Rimangono in `games/{game_id}/objects/`
- (Solo il catalog è centralizzato)

---

**Risultato**: Pacchetti piccoli, funzionamento garantito, scalabilità perfetta. 🚀
