# Third-party notices — HiddenIndexEngine

Questo documento elenca i componenti di terze parti distribuiti nel repository o
richiesti a runtime, con le rispettive licenze.

Il codice di HiddenIndexEngine e' Apache-2.0 ([LICENSE](LICENSE)); gli asset del
progetto sono CC BY 4.0 ([LICENSE-ASSETS.md](LICENSE-ASSETS.md)). Nulla di quanto
segue e' coperto da quelle licenze.

---

## Font (distribuiti nel repository)

| Font | Percorso | Autore | Licenza |
|------|----------|--------|---------|
| Share Tech Mono | `engine/assets/themes/cyber_neon/fonts/` | Carrois Type Design, Ralph du Carrois | SIL OFL 1.1 (`OFL.txt`) |
| Marcellus | `engine/assets/themes/default/fonts/` | Brian J. Bonislawsky, Astigmatic (AOETI) | SIL OFL 1.1 (`OFL.txt`) |
| Creepster | `engine/assets/themes/horror/fonts/` | Font Diner, Inc | SIL OFL 1.1 (`OFL.txt`) |
| Bubblegum Sans | `engine/assets/themes/kids/fonts/` | Angel Koziupa, Alejandro Paul (Sudtipos) | SIL OFL 1.1 (`OFL.txt`) |
| Special Elite | `engine/assets/themes/mystery/fonts/` | Brian J. Bonislawsky, Astigmatic (AOETI) | Apache-2.0 (`LICENSE.txt`) |

Tutti i font provengono da [Google Fonts](https://fonts.google.com/). Il testo
integrale della licenza si trova nella stessa cartella del file `.ttf`, come
richiesto dalla OFL 1.1 (clausola 2) e dalla Apache-2.0 (clausola 4).

I nomi dei font sono **Reserved Font Names** ai sensi della OFL: una versione
modificata del font non puo' riusare il nome originale.

---

## Icone nel diagramma del README

`docs/images/pipeline.svg` e `docs/images/pipeline.png` incorporano icone di
[Lucide](https://lucide.dev/) (monitor, globe, smartphone, pencil-ruler, layers, images,
music, languages, puzzle, wand-sparkles, folder-tree, gamepad-2), licenza ISC:

```
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any purpose with or
without fee is hereby granted, provided that the above copyright notice and this
permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO
THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO
EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL
DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN
AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

---

## Dipendenze di runtime

Installate via `pip install -r requirements.txt`. Non sono ridistribuite nel
repository, ma finiscono nei bundle prodotti dal sistema di build (EXE PyInstaller,
APK Android).

| Pacchetto | Versione | Licenza | Note |
|-----------|----------|---------|------|
| [pygame](https://www.pygame.org/) | 2.6.1 | LGPL-2.1-or-later | Include SDL2 (zlib). Ridistribuito nei bundle: vedi nota LGPL sotto. |
| [numpy](https://numpy.org/) | 2.3.5 | BSD-3-Clause | |
| [scipy](https://scipy.org/) | 1.15.3 | BSD-3-Clause | |
| [opencv-python](https://github.com/opencv/opencv-python) | 4.9.0.80 | Apache-2.0 (OpenCV 4.5+) / MIT (wrapper) | Opzionale: senza, i background video sono disattivati. |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT | Opzionale: senza, la validazione schema viene saltata. |

### Nota LGPL su pygame

`pygame` e' LGPL-2.1-or-later. HIE lo usa come libreria dinamica senza modificarlo:
la LGPL consente quindi di distribuire un'applicazione con licenza diversa
(qui Apache-2.0), a condizione che:

1. la licenza LGPL di pygame sia inclusa nella distribuzione;
2. l'utente finale possa sostituire la versione di pygame usata.

Chi distribuisce build di HIE (EXE, APK) deve includere il testo LGPL e la nota
di attribuzione a pygame nei propri materiali di distribuzione.

---

## Dipendenze di sviluppo / build

Installate via `pip install -r requirements-dev.txt`. **Non** finiscono nei bundle
distribuiti al giocatore.

| Pacchetto | Versione | Licenza |
|-----------|----------|---------|
| [pyinstaller](https://pyinstaller.org/) | 6.20.0 | GPL-2.0-or-later con eccezione di linking (i bundle prodotti non sono GPL) |
| [pytest](https://pytest.org/) | 9.0.2 | MIT |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | >=1.2.0 | MIT |

---

## Strumenti opzionali non versionati

Usati dall'editor quando presenti nell'ambiente, mai importati come dipendenza
obbligatoria e mai ridistribuiti:

| Strumento | Licenza | Uso in HIE |
|-----------|---------|------------|
| [rembg](https://github.com/danielgatis/rembg) | MIT (modelli U2-Net: Apache-2.0) | Rimozione sfondo in `add-asset` / studio PNG dell'editor |
| [Pillow](https://python-pillow.org/) | MIT-CMU | Manipolazione immagini negli script di import |

---

## Toolchain Android

Le build Android usano [python-for-android / buildozer](https://github.com/kivy/python-for-android)
(MIT) e l'Android NDK/SDK di Google, soggetti ai rispettivi termini di licenza.
Nessuno dei due e' incluso nel repository.
