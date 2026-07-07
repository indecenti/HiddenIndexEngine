"""
editor/android_build_ui.py

Finestra Tkinter di progresso per la build APK Android (Buildozer via WSL).
Wrapper sottile su editor/build_common.BaseBuildProgressWindow, simmetrico a
editor/build_ui.py (pipeline EXE). Differenze parametrizzate:
  - niente checkbox ZIP; checkbox "Release (firma per Play Store)" -> --release;
  - polling timeout esteso a 90 minuti (cross-compile Python+pygame per ARM
    puo' richiedere ~50 min alla prima build);
  - banner informativo sulla durata della prima build;
  - annulla: terminate del manager + pkill dell'albero buildozer dentro WSL;
  - lancia editor/android_build_manager.py.

Lanciata come subprocess dall'editor (editor/mixins/game_select.py):
    python editor/android_build_ui.py <game_id> <version> <build_dir> [<status_file>]
"""

import subprocess
import sys
from pathlib import Path
from tkinter import Frame, IntVar
from tkinter import ttk
from typing import Optional

# Root del progetto nel PYTHONPATH: lanciata come script, sys.path[0] = editor/.
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from editor.build_common import BaseBuildProgressWindow, logger

# Timeout di polling esteso: la build APK puo' durare ~50 min la prima volta.
# Il subprocess android_build_manager applica un suo timeout interno;
# qui controlliamo solo la mancanza di fine build.
POLLING_TIMEOUT = 5400  # 90 minuti

# Timeout del pkill dentro WSL su annulla.
_WSL_PKILL_TIMEOUT = 30

# Fasce di progresso con animazione a punti (fasi lunghe e poco verbose).
_CROSSCOMPILE_ANIM_MIN = 45
_CROSSCOMPILE_ANIM_MAX = 80
_PACKAGING_ANIM_MIN = 95
_CROSSCOMPILE_DOTS_MOD = 6
_PACKAGING_DOTS_MOD = 4


class AndroidBuildProgressWindow(BaseBuildProgressWindow):
    """Finestra Tkinter per la build APK."""

    window_title_fmt = "Compilazione APK: {game_id} v{version}"
    header_text_fmt = "Compilazione APK Android: {game_id} v{version}"
    header_font_size = 13
    geometry = "680x540"
    progressbar_length = 620
    log_area_width = 80
    polling_timeout = POLLING_TIMEOUT
    initial_status_text = "In attesa: WSL Ubuntu + Buildozer + JDK17 + NDK 27c"
    info_banner_text = (
        "Prima build: ~30-50 minuti (scarica/compila Python 3.14 + pygame-ce "
        "per ARM64 e ARMv7).\n"
        "Build successive: ~5 minuti grazie alla cache .buildozer/."
    )
    log_label_text = "Registro build APK:"
    start_button_text = "Avvia Build APK"
    open_folder_button_text = "Apri Cartella APK"
    running_status_text = "Build APK in corso (può durare 30-50 min)..."
    start_error_prefix = "Impossibile avviare build APK:"
    manager_script_name = "android_build_manager.py"
    manager_frozen_flag = "--android-build-manager"
    timeout_message_fmt = (
        "Build APK in timeout dopo {timeout_min:.0f} min.\n"
        "Il processo potrebbe essere bloccato (controllare WSL).\n"
        "Chiudere la finestra per terminare il build."
    )
    timeout_status_text = "✗ TIMEOUT Build APK"
    failure_status_text = "✗ Errore build APK"
    failure_msg_prefix = "Build APK fallito:"
    cancel_confirm_text = "Annullare la build APK?"
    close_confirm_text = "La build APK è ancora in corso. Chiudere comunque?"
    canceled_error_msg = "Build APK annullato dall'utente"
    # L'albero di build reale (buildozer/gradle) vive dentro WSL: il taskkill
    # dell'albero Windows non lo raggiungerebbe. Terminate semplice del manager
    # + pkill dentro la distro in _extra_cancel_cleanup().
    kill_tree_on_cancel = False
    # Niente popup di stallo: le fasi 45-80% (Python ARM compile) e 95-99%
    # (gradle/dexing/signing) sono naturalmente lunghe e poco verbose;
    # il banner in alto avvisa gia' della durata.
    stall_warning_after_s = None

    def _create_option_widgets(self, button_frame: Frame) -> None:
        """Checkbox release (default: build debug)."""
        self.release_var = IntVar(value=0)
        self.release_check = ttk.Checkbutton(
            button_frame,
            text="Release (firma per Play Store)",
            variable=self.release_var,
        )
        self.release_check.pack(side="left", padx=15)

    def _extra_manager_args(self) -> list[str]:
        """Aggiunge --release se il checkbox e' selezionato."""
        return ["--release"] if self.release_var.get() == 1 else []

    def _disable_option_widgets(self) -> None:
        self.release_check.config(state="disabled")

    def _percent_label_text(
        self, progress: int, status: dict, time_since_change: float
    ) -> Optional[str]:
        """Animazione a punti per le fasi lunghe e silenti della build APK."""
        if _CROSSCOMPILE_ANIM_MIN <= progress < _CROSSCOMPILE_ANIM_MAX:
            dots = "." * ((self._anim_tick % _CROSSCOMPILE_DOTS_MOD) + 1)
            return f"{progress}%  cross-compile{dots}"
        if progress >= _PACKAGING_ANIM_MIN:
            # Fase finale: gradle assemble + d8 dex + apksigner + copy bin/.
            # Poco verbose ma molto attiva: mostriamo solo un segno di vita.
            dots = "." * ((self._anim_tick % _PACKAGING_DOTS_MOD) + 1)
            return f"{progress}%  packaging finale{dots}  ({time_since_change/60:.1f} min)"
        return None

    def _success_status_text(self, status: dict) -> str:
        return "✓ APK pronto!"

    def _success_message(self, status: dict) -> str:
        apk_path = status.get("apk_path")
        apk_size = status.get("apk_size_mb")
        size_str = f" ({apk_size:.1f} MB)" if apk_size else ""
        return f"APK pronto!{size_str}\n\n{apk_path}" if apk_path else "Build completata."

    def _extra_cancel_cleanup(self) -> None:
        """
        Termina anche l'albero buildozer/gradle DENTRO la distro WSL: uccidere
        il processo Windows non propaga ai processi Linux, che altrimenti
        continuano un cross-compile multi-GB di ~50 minuti in background.
        """
        try:
            subprocess.run(
                ["wsl", "-u", "root", "-e", "bash", "-lc",
                 "pkill -9 -f buildozer; pkill -9 -f gradle; pkill -9 -f sdkmanager; true"],
                capture_output=True, timeout=_WSL_PKILL_TIMEOUT,
            )
        except Exception as e:
            logger.error(f"[Cancel] WSL pkill fallito: {e}")


def show_android_build_progress(
    game_id: str, version: str, build_dir: str, status_file: str
) -> None:
    """Entry point per lanciare la finestra UI."""
    window = AndroidBuildProgressWindow(game_id, version, build_dir, status_file)
    window.run()


if __name__ == "__main__":
    # Esecuzione da riga di comando (stesso contratto CLI storico).
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <game_id> <version> <build_dir> [<status_file>]")
        sys.exit(1)

    game_id = sys.argv[1]
    version = sys.argv[2]
    build_dir = sys.argv[3]
    status_file = sys.argv[4] if len(sys.argv) > 4 else str(Path(build_dir) / "build_status.json")

    show_android_build_progress(game_id, version, build_dir, status_file)
