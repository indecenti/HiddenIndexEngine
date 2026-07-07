"""
editor/build_ui.py

Finestra Tkinter di progresso per la build EXE desktop (PyInstaller).
Wrapper sottile su editor/build_common.BaseBuildProgressWindow: qui vivono
solo le differenze della pipeline desktop (timeout 10 minuti, checkbox
"Genera Archivio ZIP" -> flag --no-zip, lancio di editor/build_manager.py,
kill dell'intero albero processi via taskkill su annulla).

Lanciata come subprocess indipendente dall'editor Pygame
(editor/mixins/game_select.py):
    python editor/build_ui.py <game_id> <version> <build_dir> <status_file>
Comunica col build manager via file JSON di stato.
"""

import sys
from pathlib import Path
from tkinter import Frame, IntVar
from tkinter import ttk
from typing import Optional

# Root del progetto nel PYTHONPATH: lanciata come script, sys.path[0] = editor/.
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

from editor.build_common import BaseBuildProgressWindow

# Timeout del polling: 10 minuti senza fine build prima di segnalare blocco.
POLLING_TIMEOUT = 600

# Secondi di progresso fermo prima del popup di avviso stallo.
STALL_WARNING_AFTER = 120

# Fascia di progresso in cui PyInstaller lavora a lungo senza update:
# la label percentuale mostra un'animazione a punti.
_PYINSTALLER_ANIM_MIN = 70
_PYINSTALLER_ANIM_MAX = 85
_ANIM_DOTS_MOD = 6


class BuildProgressWindow(BaseBuildProgressWindow):
    """Finestra Tkinter che mostra il progresso del build EXE."""

    window_title_fmt = "Compilazione: {game_id} v{version}"
    header_text_fmt = "Compilazione: {game_id} v{version}"
    header_font_size = 14
    geometry = "600x500"
    progressbar_length = 550
    log_area_width = 70
    polling_timeout = POLLING_TIMEOUT
    initial_status_text = "Inizializzazione..."
    log_label_text = "Registro compilazione:"
    start_button_text = "Avvia Build"
    open_folder_button_text = "Apri Cartella"
    running_status_text = "Build in corso..."
    start_error_prefix = "Impossibile avviare build:"
    manager_script_name = "build_manager.py"
    manager_frozen_flag = "--build-manager"
    timeout_message_fmt = (
        "Build in timeout dopo {timeout_s:.0f}s.\n"
        "Il processo potrebbe essere bloccato.\n"
        "Chiudere la finestra per terminare il build."
    )
    timeout_status_text = "✗ TIMEOUT Build"
    failure_status_text = "✗ Errore compilazione"
    failure_msg_prefix = "Build fallito:"
    cancel_confirm_text = "Annullare la compilazione?"
    close_confirm_text = "La compilazione è ancora in corso. Chiudere comunque?"
    canceled_error_msg = "Build annullato dall'utente"
    kill_tree_on_cancel = True
    stall_warning_after_s = STALL_WARNING_AFTER

    def _create_option_widgets(self, button_frame: Frame) -> None:
        """Checkbox ZIP opzionale (default disattivato)."""
        self.zip_var = IntVar(value=0)
        self.zip_check = ttk.Checkbutton(
            button_frame,
            text="Genera Archivio ZIP",
            variable=self.zip_var,
            style="Small.TCheckbutton",
        )
        self.zip_check.pack(side="left", padx=15)

    def _extra_manager_args(self) -> list[str]:
        """Aggiunge --no-zip se il checkbox non e' selezionato."""
        return ["--no-zip"] if self.zip_var.get() == 0 else []

    def _disable_option_widgets(self) -> None:
        self.zip_check.config(state="disabled")

    def _percent_label_text(
        self, progress: int, status: dict, time_since_change: float
    ) -> Optional[str]:
        """Animazione durante PyInstaller (resta tra 70-85% per minuti)."""
        if _PYINSTALLER_ANIM_MIN <= progress < _PYINSTALLER_ANIM_MAX:
            dots = "." * ((self._anim_tick % _ANIM_DOTS_MOD) + 1)
            return f"{progress}%  PyInstaller{dots}"
        return None

    def _success_status_text(self, status: dict) -> str:
        return "✓ Compilazione completata!"

    def _success_message(self, status: dict) -> str:
        zip_path = status.get("zip_path")
        zip_line = f"\nZIP: {zip_path}" if zip_path else "\n(nessun archivio ZIP creato)"
        return f"Build completato!{zip_line}"


def show_build_progress(game_id: str, version: str, build_dir: str, status_file: str) -> None:
    """Entry point per lanciare la finestra UI."""
    window = BuildProgressWindow(game_id, version, build_dir, status_file)
    window.run()


if __name__ == "__main__":
    # Esecuzione da riga di comando (stesso contratto CLI storico).
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <game_id> <version> <build_dir> <status_file>")
        sys.exit(1)

    game_id = sys.argv[1]
    version = sys.argv[2]
    build_dir = sys.argv[3]
    status_file = sys.argv[4] if len(sys.argv) > 4 else "build_status.json"

    show_build_progress(game_id, version, build_dir, status_file)
