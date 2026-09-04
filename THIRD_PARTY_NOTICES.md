# Third-party notices — HiddenIndexEngine

This document lists the third-party components distributed in the repository or
required at runtime, with their licenses.

HiddenIndexEngine's code is under the PolyForm Noncommercial License 1.0.0
([LICENSE](LICENSE), with commercial terms in [LICENSING.md](LICENSING.md)); the project's
assets are CC BY-NC 4.0 ([LICENSE-ASSETS.md](LICENSE-ASSETS.md)). Nothing listed below is
covered by those licenses: each component keeps its own.

---

## Fonts (distributed in the repository)

| Font | Path | Author | License |
|------|------|--------|---------|
| Share Tech Mono | `engine/assets/themes/cyber_neon/fonts/` | Carrois Type Design, Ralph du Carrois | SIL OFL 1.1 (`OFL.txt`) |
| Marcellus | `engine/assets/themes/default/fonts/` | Brian J. Bonislawsky, Astigmatic (AOETI) | SIL OFL 1.1 (`OFL.txt`) |
| Creepster | `engine/assets/themes/horror/fonts/` | Font Diner, Inc | SIL OFL 1.1 (`OFL.txt`) |
| Bubblegum Sans | `engine/assets/themes/kids/fonts/` | Angel Koziupa, Alejandro Paul (Sudtipos) | SIL OFL 1.1 (`OFL.txt`) |
| Special Elite | `engine/assets/themes/mystery/fonts/` | Brian J. Bonislawsky, Astigmatic (AOETI) | Apache-2.0 (`LICENSE.txt`) |

All fonts come from [Google Fonts](https://fonts.google.com/). The full license text sits
in the same folder as the `.ttf` file, as required by OFL 1.1 (clause 2) and by
Apache-2.0 (clause 4).

The font names are **Reserved Font Names** under the OFL: a modified version of a font
may not reuse the original name.

---

## Icons in the README diagram

`docs/images/pipeline.svg` and `docs/images/pipeline.png` embed icons from
[Lucide](https://lucide.dev/) (monitor, globe, smartphone, pencil-ruler, layers, images,
music, languages, puzzle, wand-sparkles, folder-tree, gamepad-2), ISC license:

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

## Platform logos in the README

`docs/images/icons/` holds the logos shown next to the three export targets, used only
to indicate platform compatibility:

| File | Source | License / trademark |
|------|--------|---------------------|
| `android.svg` | [Simple Icons](https://simpleicons.org/) (icon data CC0 1.0) | The Android robot is reproduced or modified from work created and shared by Google and used according to terms described in the Creative Commons 3.0 Attribution License. Android is a trademark of Google LLC. |
| `html5.svg` | [Simple Icons](https://simpleicons.org/) (icon data CC0 1.0) | W3C HTML5 logo, Creative Commons Attribution 3.0 license. |
| `windows.svg` | [Devicon](https://devicon.dev/) (MIT) | Windows is a trademark of Microsoft Corporation. |

The trademarks remain the property of their respective owners and are not covered by
the project licenses.

---

## Runtime dependencies

Installed via `pip install -r requirements.txt`. They are not redistributed in the
repository, but they end up in the bundles produced by the build system (PyInstaller
EXE, Android APK).

| Package | Version | License | Notes |
|---------|---------|---------|-------|
| [pygame](https://www.pygame.org/) | 2.6.1 | LGPL-2.1-or-later | Includes SDL2 (zlib). Redistributed in the bundles: see the LGPL note below. |
| [numpy](https://numpy.org/) | 2.3.5 | BSD-3-Clause | |
| [scipy](https://scipy.org/) | 1.15.3 | BSD-3-Clause | |
| [opencv-python](https://github.com/opencv/opencv-python) | 4.9.0.80 | Apache-2.0 (OpenCV 4.5+) / MIT (wrapper) | Optional: without it, video backgrounds are disabled. |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT | Optional: without it, schema validation is skipped. |

### LGPL note on pygame

`pygame` is LGPL-2.1-or-later. HIE uses it as an unmodified dynamic library: the LGPL
therefore allows distributing an application under a different license, provided that:

1. pygame's LGPL license is included in the distribution;
2. the end user can replace the pygame version in use.

The build system takes care of point 1: every build (EXE, web export, APK) ships a
`licenses/` folder with this document, the engine terms and the asset terms. If you
repackage a build by hand, carry that folder with it.

---

## Development / build dependencies

Installed via `pip install -r requirements-dev.txt`. They do **not** end up in the
bundles shipped to players.

| Package | Version | License |
|---------|---------|---------|
| [pyinstaller](https://pyinstaller.org/) | 6.20.0 | GPL-2.0-or-later with linking exception (the produced bundles are not GPL) |
| [pytest](https://pytest.org/) | 9.0.2 | MIT |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | >=1.2.0 | MIT |

---

## Optional tools, not versioned

Used by the editor when present in the environment, never imported as a mandatory
dependency and never redistributed:

| Tool | License | Use in HIE |
|------|---------|------------|
| [rembg](https://github.com/danielgatis/rembg) | MIT (U2-Net models: Apache-2.0) | Background removal in `add-asset` / the editor's PNG studio |
| [Pillow](https://python-pillow.org/) | MIT-CMU | Image manipulation in the import scripts |

---

## Android toolchain

Android builds use [python-for-android / buildozer](https://github.com/kivy/python-for-android)
(MIT) and Google's Android NDK/SDK, subject to their respective license terms.
Neither is included in the repository.
