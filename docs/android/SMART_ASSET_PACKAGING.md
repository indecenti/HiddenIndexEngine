# Smart Asset Packaging System

## Overview

The build system implements **Smart Asset Packaging**: when creating a package it bundles **ONLY the assets used** by the game, minimizing the size of the distributable.

## How it works

### 1. Level analysis
```python
# The build system reads every scene.json
for scene in game/levels/*/scene.json:
    extract the object_id of every object in use
    -> set of "used_objects"
```

### 2. Smart asset copy
```
For every object in used_objects:
  Copy {object_id}.png from games/<game_id>/objects/
  -> The final package contains ONLY these files

Example:
- The catalog has 150 objects available
- The scenes use 28 objects
- The package contains ONLY 28 images (not 150)
```

### 3. Centralized catalog
```
engine/data/global_*_catalog.json
  |
  Copied into the package as engine/data/global_*_catalog.json
  |
  The game reads the metadata of ALL objects
  (but the PNG icons are in the game, not in the engine)
```

## Final layout

### During development (main.py)
```
HiddenIndexEngine/
├── engine/
│   ├── data/
│   │   ├── global_*_catalog.json          <- centralized catalogs
│   │   └── ... (other engine resources)
│   └── ... (rest of the engine)
└── games/
    └── <game_id>/
        ├── objects/                       <- PNG icons (not all copied into the build)
        │   ├── runed_skull.png
        │   ├── ritual_dagger.png
        │   └── ... (all icons)
        ├── levels/
        │   └── <level>/
        │       ├── <scene>/scene.json     <- declares which objects it uses
        │       └── ...
        └── game_config.json
```

### In the final package (build)
```
build/<game_id>/1.0/main/
├── main.exe
├── engine/
│   ├── data/
│   │   └── global_*_catalog.json          <- catalogs only
│   └── ...
└── games/
    └── <game_id>/
        ├── objects/                       <- ONLY the USED assets
        │   ├── runed_skull.png            used
        │   ├── ritual_dagger.png          used
        │   └── ... (28 files out of 150)  used only
        ├── levels/
        │   └── ...
        └── game_config.json
```

## Benefits

**Small packages**
- Sizes drop drastically
- Example: 150 icons (15 MB) -> 28 icons (3 MB) = -80%

**Works everywhere**
- In development with `main.py` (accesses all assets)
- In the EXE build (packages only what is needed)
- Scales to multiple games

**Easy maintenance**
- Centralized catalog (metadata)
- Assets stay isolated in the game
- Adding objects is simple

**Zero breaking changes**
- Keeps working as before
- The build system is just smarter (transparent)

## Technical implementation

### Functions in build_system.py

#### `_get_used_objects(game_path) -> set[str]`
Analyzes every `scene.json` and returns the object_ids in use.

```python
used_objects = _get_used_objects(games_src)
# Result: {'runed_skull', 'ritual_dagger', 'oil_lantern', ...}
```

#### `_copy_smart_assets(games_src, games_dst, used_objects) -> (count, size_mb)`
Copies only the used assets.

```python
asset_count, asset_size_mb = _copy_smart_assets(
    games_src,
    games_dst,
    used_objects
)
# Result: (28, 3.5)  <- 28 files, 3.5 MB
```

## Build logging

When you run a build you see:
```
[Smart Pack] Objects used by the game: 28
[Smart Pack] Assets copied: 28 files (3.5 MB)
[Copy] games/<game_id>/ -> main/ (4.2 MB)
```

## Future scalability

If you add a new game:
```
games/
├── game_a/
│   └── objects/        <- 150 icons (all)
└── game_b/
    └── objects/        <- 45 icons (all)

Build game_a  -> package with 28 icons
Build game_b  -> package with 12 icons
(different for every game)
```

## Important notes

**Do not modify the centralized catalog during development**
- Read it when you add new objects
- If you add objects, update it first

**The PNG assets stay in the game**
- They are not in `engine/data/objects/`
- They stay in `games/{game_id}/objects/`
- (Only the catalog is centralized)

---

**Result**: small packages, guaranteed operation, clean scalability.
