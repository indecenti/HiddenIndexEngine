# Piano Builder APK Android integrato nell'editor

**Status**: Approvato — F1 completata, prossimo step F0 (setup WSL) oppure F2 (prototipo manuale)
**Versione piano**: 2.0
**Data revisione**: 2026-05-13
**Sostituisce**: piano v1.0 (obsoleto su toolchain e disallineato sull'architettura editor)

**Decisioni approvate (2026-05-13)**:
- APK separati per gioco (un APK per LineVenture, uno per Malonno_Survivors)
- Setup WSL gestito da wizard nell'editor (mostra istruzioni + verifica, non installa silenziosamente)
- Orientation: landscape forzato (coerente con 1920x1080 del motore)

---

## 1. Obiettivo

Estendere l'editor con una procedura di pacchettizzazione APK Android **parallela** a quella che oggi produce l'EXE Windows tramite PyInstaller. L'editor stesso **non** finisce nell'APK: gli APK contengono solo `engine/` + `main.py` + `games/<id>/` di un singolo gioco. Un APK per gioco (LineVenture, Malonno_Survivors).

Risultato atteso: dall'editor, accanto al bottone "Compila gioco (Windows EXE)", un bottone "Compila APK Android" che produce `bin/<game_id>-<version>-debug.apk` (o `-release.aab` per Play Store).

---

## 2. Stato della codebase e dipendenze runtime

Verificato in questa sessione:

| Aspetto | Verifica | Esito |
|---------|----------|-------|
| `engine/` importa `editor/`? | `grep "from editor\|import editor" engine/` | ❌ nessun import — `engine` è standalone |
| `main.py` importa `editor/`? | stesso grep | ❌ nessun import |
| Networking runtime | grep `requests/socket/urllib` | ❌ assente |
| `subprocess` nel runtime | grep `subprocess` in `engine/` | ❌ solo `editor/build_system.py` (non runtime) |
| Threading | `engine/audio_manager.py:10-41` | ✅ daemon thread + Queue — supportato su Android |
| File I/O | `engine/save_manager.py:57-63` open() su path locali | ⚠️ va dirottato su Android internal storage |
| Main loop | `engine/core.py:235-246` | ✅ sincrono Pygame standard |
| Input | `engine/core.py:265` MOUSEBUTTONDOWN | ✅ pygame mappa touch→mouse automaticamente |
| `get_base_path()` | `engine/utils.py:32-37` | ⚠️ da estendere con detection p4a |

**Bundle attuale**:
- `engine/` 398 MB di cui `engine/assets/` 383 MB (backgrounds 180 + objects 141 + music 37)
- `engine/*.py` < 300 KB (codice motore)
- `games/LineVenture/` 55 MB, `games/Malonno_Survivors/` 102 MB

L'editor esistente ha **già** uno smart packaging che riduce drasticamente l'output: `editor/build_system.py:34` `_analyze_game_usage()` traccia gli asset effettivamente referenziati dalle scene del gioco e copia solo quelli. La logica APK riuserà queste stesse funzioni.

---

## 3. Architettura proposta

Riproduce in parallelo la triade EXE già funzionante.

```
EXE Windows (esistente)               APK Android (nuovo)
─────────────────────────             ───────────────────────────
editor/build_ui.py            ◄──►    editor/android_build_ui.py
editor/build_manager.py       ◄──►    editor/android_build_manager.py
editor/build_system.py        ◄──►    editor/android_build_system.py
   └─ PyInstaller                       └─ Buildozer (via WSL)
```

Funzioni condivise senza duplicazione:
- `_analyze_game_usage()` — riusata 1:1
- `_copy_smart_assets()` — riusata 1:1
- `next_build_version()` — riusata 1:1

Nuove funzioni in `android_build_system.py`:
- `_verify_wsl_toolchain()` — controlla `wsl --status`, presenza `buildozer` nel venv Linux configurato
- `_generate_buildozer_spec(game_id, version, workspace)` — produce `buildozer.spec` parametrizzato per il gioco
- `_run_buildozer_with_timeout()` — analogo a `_run_pyinstaller_with_timeout`, lancia `wsl -e bash -lc "cd … && buildozer android debug"` e parsa output
- `build_game_apk()` — orchestratore principale (firma simmetrica a `build_game()`)

Il bottone APK nell'editor lancia un subprocess `python editor/android_build_manager.py <game_id> <version> <build_dir> <status_file> [--release]`, che a sua volta apre `BuildProgressWindow` versione Android. Stesso paradigma di comunicazione via `status.json` con watchdog.

---

## 4. Toolchain target 2026

Stack aggiornato ai requisiti Google Play 2026:

| Componente | Versione | Note |
|------------|----------|------|
| WSL2 + Ubuntu | 24.04 LTS | Buildozer non gira su Windows nativo |
| JDK | 17 (Temurin) | Richiesto da Android Gradle Plugin attuale |
| Python (in WSL) | 3.12 | Compatibile p4a stable |
| Android SDK platform | `android-35` | targetSdk obbligatorio per nuove app/aggiornamenti dal 2025 |
| Android SDK build-tools | `35.0.0` | |
| Android NDK | `28.2.13676358` (28b stable) | **Aggiornato 2026-05-13 da 27c**: necessario per 16 KB ELF page-size alignment richiesto da Android 15+ su Pixel 9 e successivi (emulatori Pixel_10 incluso `sdk_gphone16k_x86_64`). NDK 27c allinea a 4 KB → `dlopen` fallisce con `program alignment (4096) cannot be smaller than system page size (16384)` |
| minSdkVersion | `24` (Android 7 Nougat) | Inizialmente pianificato 23, alzato a 24 dopo F2: Python 3.14 di p4a usa `preadv()`/`pwritev()` di bionic, esposti solo da API 24. >99% device attivi sono comunque ≥ API 24 |
| Buildozer | `1.5.x` (stable PyPI) | Niente `develop` branch |
| python-for-android | `2024.x` (stable) | |
| pygame-ce | `2.5.x` | NON pygame originale — pygame-ce è il drop-in moderno usato da p4a |
| Output | APK debug (test) + AAB release (Play Store) | Play Store accetta solo AAB |

Detection Android corretta (env vars effettive di p4a):

```python
def is_android_runtime() -> bool:
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ
```

`ANDROID_APP_PATH` citato nel piano v1.0 **non esiste** in p4a.

---

## 5. Fix runtime necessari nel motore

Modifiche minime e localizzate, nessun refactor.

### 5.1 `engine/utils.py` — `get_base_path()` e `get_writable_path()`

```python
import os

def is_android_runtime() -> bool:
    return 'ANDROID_ARGUMENT' in os.environ or 'P4A_BOOTSTRAP' in os.environ

def get_base_path() -> Path:
    if is_android_runtime():
        # p4a unpacka l'app in /data/data/<package>/files/app
        return Path(os.environ.get('ANDROID_PRIVATE', '/data/data')) / 'app'
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]

def get_writable_path(*parts: str) -> Path:
    if is_android_runtime():
        # Storage privato app, sopravvive a reboot, non richiede permessi runtime
        base = Path(os.environ['ANDROID_PRIVATE']) / 'saves'
    else:
        base = get_base_path() / 'saves'
    base.mkdir(parents=True, exist_ok=True)
    path = base
    for p in parts:
        path = path / p
    if path.parent != base:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path
```

Impatto: zero su Windows/desktop (i nuovi rami sono dietro `if is_android_runtime()`). `SaveManager` non cambia: chiama `get_writable_path()` come oggi.

### 5.2 Touch input

Già funzionante: pygame su Android mappa automaticamente `FINGERDOWN` → `MOUSEBUTTONDOWN` con `event.pos` in pixel device. Il motore (`engine/core.py:265`) usa già `MOUSEBUTTONDOWN`. Nessuna modifica.

### 5.3 Lifecycle pause/resume

Non bloccante per MVP. Su Android quando l'app va in background, pygame riceve `pygame.APP_WILLENTERBACKGROUND` / `APP_DIDENTERBACKGROUND`. Per la prima versione l'app può semplicemente continuare il loop a basso framerate. Hook proprio (pyjnius) sarà aggiunto in F6 se servirà.

### 5.4 AudioManager

Nessuna modifica. Daemon thread + Queue sono supportati nativamente da p4a/Android.

---

## 6. Buildozer.spec template

Generato dinamicamente da `_generate_buildozer_spec()` per ogni gioco. Bozza:

```ini
[app]
title = {game_title}
package.name = {game_id_normalized}
package.domain = org.hiddenindex
version = {version}

source.dir = .
source.include_exts = py,json,png,jpg,jpeg,ogg,ttf
source.exclude_dirs = editor,tests,scratch,build,dist,docs,saves,.git,.claude,__pycache__
source.exclude_patterns = *.pyc,*.pyo,*.autosave,*.bak,*.tmp,*.log,*.md,*.spec,*.ini

requirements = python3,pygame-ce,android,jnius

orientation = landscape
fullscreen = 1

android.api = 35
android.minapi = 24   # vedi nota sezione 4: Python 3.14 richiede API 24+
android.ndk = 27c
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = False
android.accept_sdk_license = True

android.permissions = 

# Icona del gioco (presa da games/<id>/icon.png)
icon.filename = games/{game_id}/icon.png

# Splash
presplash.filename = games/{game_id}/splash.png

[buildozer]
log_level = 2
warn_on_root = 0
```

Note:
- `requirements`: minimo indispensabile, nessuna libreria editor (cv2, numpy, scipy, PyInstaller). pygame-ce su p4a è già pacchettizzato per Android.
- `source.exclude_dirs = editor` esclude esplicitamente la cartella editor dall'APK.
- `arm64-v8a + armeabi-v7a`: copre 100% device moderni.
- `orientation = landscape`: i giochi sono pensati 1920x1080. Lo `scaling_manager` esistente già adatta.
- File generato in workspace temporaneo, non versionato.

---

## 7. Workflow di build APK (lato editor)

Specchio simmetrico di quello EXE. Passo-passo dentro `build_game_apk()`:

1. **Validazione** — `game_id` esiste, `game_config.json` valido. (Identico a `build_game()`.)
2. **Verifica toolchain WSL** — esecuzione di `wsl -e bash -lc "buildozer --version"`. Se fallisce → errore con istruzioni setup.
3. **Workspace temporaneo** in `<temp>/apk_<game_id>/`. Su Windows è una path Windows; Buildozer la userà via path WSL `/mnt/g/...`.
4. **Smart copy engine + game** — riusa `_analyze_game_usage()` e `_copy_smart_assets()`. **Esclude** `editor/`, `tests/`, `scratch/`, `build/`, `dist/`, `saves/`.
5. **Generazione `buildozer.spec`** parametrizzato per il gioco.
6. **Generazione `main.py` shim** se necessario (Buildozer cerca `main.py` come entry; quello esistente va bene così com'è, basta che `config.ini` sia accanto).
7. **Compressione asset** (opzionale, attivabile da UI checkbox):
   - PNG → `oxipng -o4` (lossless, ~30%)
   - WAV/MP3 → `ffmpeg -q:a 5 *.ogg` (lossy ~50%)
8. **Lancio Buildozer**: `wsl -e bash -lc "cd <workspace_wsl_path> && source ~/venv_p4a/bin/activate && buildozer android debug"` con timeout 30 min e parsing output per progress.
9. **Copia APK risultato** da `<workspace>/bin/*.apk` a `build/<game_id>/<version>/<game_id>-<version>-debug.apk`.
10. **Verifica APK** (`aapt dump badging` per leggere package name, version, min/target SDK).
11. **Cleanup workspace temporaneo**.

Per AAB release: identico ma `buildozer android release`, con firma `jarsigner` da chiavi configurate (cfg utente in `editor/android_signing.json`, fuori dal repo).

---

## 8. UI dell'editor

Modifica minima a `editor/build_ui.py` (o pulsante nella schermata principale che invoca la build). Da progettare in dettaglio guardando la UI attuale del builder, ma logicamente:

- Dialog scelta gioco (già esistente per EXE)
- Due bottoni: **"Compila EXE Windows"** | **"Compila APK Android"**
- Per APK, un check "release (firma per Play Store)" opzionale
- Stessa progress window, label di passi adattate a Buildozer

Prima volta che si preme "Compila APK": l'editor verifica WSL/Buildozer. Se mancano, mostra un wizard con i comandi da eseguire (vedi F0) e il bottone "Verifica di nuovo".

---

## 9. Fasi di lavoro

| Fase | Descrizione | Output | Tempo stima |
|------|-------------|--------|------------|
| **F0** | Setup WSL2 + JDK17 + Android SDK + NDK 27c + Buildozer in venv (one-time, lato user con istruzioni dell'editor) | Toolchain WSL funzionante | 1 giorno (download pesanti) |
| **F1** ✅ | Fix runtime motore: `engine/utils.py` `get_base_path()` + `get_writable_path()` + helper `is_android_runtime()` | Completato 2026-05-13. Smoke test Windows: nessuna regressione. | — |
| **F2** | Prototipo standalone APK: copiare manualmente un workspace minimo in WSL e lanciare `buildozer android debug` su LineVenture. Validare che l'APK parta su emulatore Android 15 (API 35) | 1 APK funzionante a mano | 1-2 giorni |
| **F3** | `editor/android_build_system.py` + `editor/android_build_manager.py` (riuso massimo di `build_system.py`) | 2 file nuovi | 1-2 giorni |
| **F4** | Estensione UI editor: bottone APK + finestra progress | Modifica `build_ui.py` (o equivalente) | 0.5-1 giorno |
| **F5** | Asset compression integrata (opt-in) + audit asset effettivamente usati per gioco | APK ridotti del 30-50% | 1 giorno |
| **F6** | Build AAB release firmato + push Play Console (lifecycle hooks se necessari) | App pubblicabile | 1-2 giorni |
| **TOTALE F0–F4 (MVP testabile)** | | APK debug compilabile dall'editor | **3-5 giorni** + F0 setup |

F5–F6 sono iterazioni successive.

---

## 10. F0 — Setup WSL (istruzioni one-time)

Da eseguire prima che il builder APK dell'editor possa funzionare. Verrà incluso come wizard nell'editor (F4) ma documentato qui per primo run manuale.

### 10.1 WSL2 + Ubuntu 24.04 (PowerShell admin, dal sistema Windows)

```powershell
wsl --install -d Ubuntu-24.04
# Riavvio richiesto
```

### 10.2 Dipendenze dentro WSL Ubuntu (sessione `wsl`)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
  git wget curl unzip zip \
  openjdk-17-jdk \
  build-essential libffi-dev libssl-dev \
  autoconf libtool pkg-config zlib1g-dev libncurses-dev libtinfo-dev cmake \
  libltdl-dev

python3.12 -m venv ~/venv_p4a
source ~/venv_p4a/bin/activate
pip install --upgrade pip
pip install buildozer cython==3.0.11
echo 'source ~/venv_p4a/bin/activate' >> ~/.bashrc
```

### 10.3 Android SDK + NDK (in WSL)

```bash
mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip commandlinetools-linux-*.zip
mv cmdline-tools latest
rm commandlinetools-linux-*.zip

cat >> ~/.bashrc <<'EOF'
export ANDROID_HOME=$HOME/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
EOF
source ~/.bashrc

yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" "ndk;27.2.12479018"
```

### 10.4 Verifica

```bash
buildozer --version  # 1.5.x
java -version        # 17.x
sdkmanager --list_installed
```

Tutta questa procedura sarà rieseguibile via un comando dall'editor; in caso di errore l'editor mostrerà esattamente quale step ha fallito.

---

## 11. Limiti noti e mitigazioni

| Problema | Impatto | Mitigazione |
|----------|---------|-------------|
| Bundle game ancora pesante (LineVenture ~55 MB, Malonno_Survivors ~102 MB + engine/assets condivisi) | APK potrebbe superare 150 MB | F5 asset compression + valutare Play Asset Delivery per AAB > 200 MB |
| WSL latency Windows ↔ Linux filesystem | Build APK 2-3× più lento di EXE | Workspace clonato dentro `~/` Linux (non `/mnt/g/`) — gestito dal builder |
| Prima build scarica 1-2 GB (NDK, SDK, recipe p4a) | F0 lunga | Una volta sola, cache persistente in `~/.buildozer/` |
| Risoluzione fissa 1920x1080 | Distorsione su schermi 18:9 o pieghevoli | `scaling_manager` esistente già scala con letterboxing — verificare in F2 |
| Audio MP3 con licenza | Tracce ottenute da fonti libere? | Da verificare prima del Play Store release (F6) |
| Save su `ANDROID_PRIVATE` non condiviso tra device | OK per ora, eventuale cloud-save futuro | Non scope del piano |

---

## 12. Punti aperti che richiedono decisione

Prima di partire con F1 vorrei una conferma su:

1. **APK separato per gioco vs APK launcher con scelta gioco** — il piano assume APK separati (un APK per LineVenture, uno per Malonno_Survivors). Confermi?
2. **Configurazione di firma Play Store** — keystore esistente o da generare in F6?
3. **Wizard setup WSL nell'editor** — è OK avere uno schermo dell'editor che esegue `wsl --install` per l'utente, o preferisci che la prima volta sia manuale e l'editor solo verifichi?
4. **Tablet/orientation** — landscape forzato OK, o vogliamo supportare anche portrait con auto-rotate?

---

## 13. Criteri di accettazione MVP (fine F4)

1. Dall'editor, su Windows, premendo "Compila APK Android" su LineVenture:
   - Si apre la progress window
   - Buildozer parte dentro WSL senza interazione utente
   - Al termine produce `build/LineVenture/<v>/LineVenture-<v>-debug.apk`
2. L'APK installato su emulatore Android 15 (API 35) parte, mostra il menu principale, carica almeno una scena di gioco, riproduce audio, accetta tap.
3. La stessa procedura, ripetuta su Malonno_Survivors, produce un APK distinto (package name diverso).
4. L'editor non viene impacchettato nell'APK (verifica con `unzip -l <apk> | grep editor` → vuoto).
5. Nessuna regressione sul builder EXE esistente.

---

## 14. Cosa NON facciamo in questa iterazione

Per evitare scope creep:

- Niente porting iOS (toolchain completamente diversa)
- Niente in-app purchase / ads / Google Play Services
- Niente cloud save
- Niente leaderboard / achievements native Android
- Niente multi-window / split-screen specifico Android
- Niente refactor del motore oltre i 2-3 metodi in `engine/utils.py`

Tutto questo è territorio post-F6 se mai servirà.
