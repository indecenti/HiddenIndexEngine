[app]
title = LineVenture
package.name = lineventure
package.domain = org.hiddenindex
version = 1.4

source.dir = .
source.include_exts = py,json,png,jpg,jpeg,ogg,wav,mp3,ttf,ini,txt,xml
source.exclude_dirs = tests,scratch,docs,saves,.git,.claude,__pycache__,bin,.buildozer
source.exclude_patterns = *.pyc,*.pyo,*.autosave,*.bak,*.tmp,*.log,*.spec,*.md,run.bat,*.mp4

# Requirements:
#   - pygame (NON pygame-ce): p4a ha recipe per `pygame` che cross-compila
#     correttamente per ARM. `pygame-ce` non ha recipe → pip → wheel host x86_64
#     viene erroneamente copiata in arm64/ → ImportError EM_X86_64 vs EM_AARCH64
#     al boot. pygame e pygame-ce esportano lo stesso namespace `pygame`, quindi
#     il codice del motore (`import pygame`) funziona identico.
#   - numpy: REQUIRED — eager import in engine/scene_loader.py:13, propagato a tutto
#     il motore via core/click_detector/hud_manager/level_manager/hint_system.
#     Senza numpy il subprocess Python crasha immediatamente al boot.
#   - scipy: opzionale, solo se warp_surface (utils.py) viene chiamato.
requirements = python3,pygame,android,pyjnius,numpy

# Icona app: usa l'icona del gioco selezionata (1024x1024). p4a genera i
# mipmap per tutte le densità. Path relativo alla root del workspace (games/
# viene sincronizzato dallo script di build).
icon.filename = %(source.dir)s/games/LineVenture/assets/icon.png

# Presplash (schermata di caricamento) e colore di sfondo: sostituisce il
# logo Kivy di default con la grafica del gioco.
presplash.filename = %(source.dir)s/games/LineVenture/assets/presplash.png
android.presplash_color = #0a0c12

orientation = landscape
fullscreen = 1

# Android target
# minapi = 24 (Android 7.0): Python 3.14 di p4a usa preadv/pwritev di bionic,
# disponibili solo da API 24. >99% device attivi sono >= API 24 nel 2026.
# NDK 28.2: necessario per 16 KB page size alignment (Android 15+ Pixel 9+).
# NDK 27 e precedenti allineano a 4 KB → dlopen fallisce su device 16 KB.
# archs: arm64-v8a per i device reali del 2026 (armeabi-v7a obsoleto, droppato).
# x86_64 aggiunto per poter testare/eseguire sull'emulatore Android Studio
# (AVD x86_64). Per una release puramente arm si può rimuovere x86_64 e
# ridurre dimensione APK + tempi di build.
android.api = 35
android.minapi = 24
android.ndk = 28b
# Release/produzione: solo arm64-v8a (device reali). x86_64 era solo per
# l'emulatore Android Studio durante lo sviluppo.
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = False
# release optimization: rimuove debug symbols dalle .so → APK più piccolo e
# caricamento marginalmente più veloce. Disattivabile per debug intensivo.
android.release_artifact = aab
android.debug_artifact = apk

# Path WSL ai tool installati (sovrascrive download automatico)
android.sdk_path = /root/android-sdk
android.ndk_path = /root/android-sdk/ndk/28.2.13676358

# Permessi runtime
# WAKE_LOCK: pygame.display.set_allow_screensaver(False) richiede questo permesso
#   per impedire allo schermo di spegnersi durante il gameplay (compliance UX).
android.permissions = android.permission.WAKE_LOCK

# meta-data per ottimizzazioni runtime Android:
# (questi vanno applicati via p4a hook al manifest, qui solo nota per il futuro)
# - android:hardwareAccelerated="true" (default true API 14+)
# - android:largeHeap="true" (aumenta heap a ~256MB/512MB per il bytecode Python)


[buildozer]
log_level = 2
warn_on_root = 0
