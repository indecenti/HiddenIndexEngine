"""
editor/android_build_ui.py

Finestra Tkinter per il progresso della compilazione APK Android.
Simmetrica a editor/build_ui.py (che fa la stessa cosa per la build EXE).

Differenze rispetto a build_ui.py:
  - Niente checkbox "Genera ZIP" (l'output è un APK già confezionato).
  - Checkbox "Release (firma per Play Store)" — default OFF, build debug.
  - Polling timeout esteso a 80 minuti (cross-compile di Python 3.14 +
    pygame-ce per arm64+armv7 può richiedere ~50 min sulla prima build).
  - Lancia editor/android_build_manager.py.
"""

import json
import time
import os
import subprocess
import sys
from pathlib import Path
from tkinter import Tk, Frame, Label, Text, Button, messagebox, IntVar
from tkinter import ttk
from tkinter import scrolledtext

# Assicura che la root del progetto sia nel PYTHONPATH:
# questo modulo viene lanciato come subprocess dall'editor (cwd=root) ma Python
# aggiunge solo `dirname(script)` (ovvero `editor/`) a sys.path[0], non la root.
# Senza questo fix l'import `from engine.utils import ...` fallisce.
_local_root = Path(__file__).resolve().parent.parent
if str(_local_root) not in sys.path:
    sys.path.insert(0, str(_local_root))

# Timeout di polling esteso: build APK può durare ~50 min prima volta.
# Il subprocess android_build_manager applica un suo timeout interno;
# qui controlliamo solo la mancanza di progresso.
POLLING_TIMEOUT = 5400  # 90 minuti


class AndroidBuildProgressWindow:
    """Finestra Tkinter per la build APK."""

    def __init__(self, game_id: str, version: str, build_dir: str, status_file: str):
        self.game_id = game_id
        self.version = version
        self.build_dir = Path(build_dir)
        self.status_file = Path(status_file)
        self.build_process: subprocess.Popen | None = None
        self.should_cancel = False
        self.build_started = False

        self.root = Tk()
        self.root.title(f"Compilazione APK: {game_id} v{version}")
        self.root.geometry("680x540")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.release_var = IntVar(value=0)  # default: build debug

        self.poll_start_time = time.time()
        self.last_progress_change = time.time()
        self.last_progress = 0
        self.last_timestamp = 0
        self._anim_tick = 0

        self._create_widgets()
        self._start_polling()

    def _create_widgets(self) -> None:
        # Header
        header = Frame(self.root, bg="#2c3e50", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        Label(
            header,
            text=f"Compilazione APK Android: {self.game_id} v{self.version}",
            font=("Segoe UI", 13, "bold"),
            fg="#ecf0f1",
            bg="#2c3e50",
        ).pack(pady=10)

        # Status
        status_frame = Frame(self.root)
        status_frame.pack(fill="x", padx=15, pady=10)
        self.status_label = Label(
            status_frame,
            text="In attesa: WSL Ubuntu + Buildozer + JDK17 + NDK 27c",
            font=("Segoe UI", 10),
            fg="#34495e",
        )
        self.status_label.pack(anchor="w")

        # Progress bar
        progress_frame = Frame(self.root)
        progress_frame.pack(fill="x", padx=15, pady=5)
        self.progress_var = IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            length=620,
            mode="determinate",
            variable=self.progress_var,
            maximum=100,
        )
        self.progress_bar.pack(fill="x")
        self.percent_label = Label(progress_frame, text="0%", font=("Segoe UI", 9), fg="#7f8c8d")
        self.percent_label.pack(anchor="e", pady=2)

        # Info banner (avvisa di durata)
        info_frame = Frame(self.root, bg="#fef9e7")
        info_frame.pack(fill="x", padx=15, pady=5)
        Label(
            info_frame,
            text=(
                "⏱  Prima build: ~30-50 minuti (scarica/compila Python 3.14 + pygame-ce per ARM64 e ARMv7).\n"
                "    Build successive: ~5 minuti grazie alla cache .buildozer/."
            ),
            font=("Segoe UI", 9),
            bg="#fef9e7",
            fg="#7d6608",
            justify="left",
        ).pack(anchor="w", padx=8, pady=5)

        # Log
        log_frame = Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)
        Label(log_frame, text="Registro build APK:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            width=80,
            font=("Courier New", 9),
            bg="#ecf0f1",
            fg="#2c3e50",
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, pady=5)

        # Buttons
        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=15, pady=10)

        self.start_btn = Button(
            button_frame,
            text="▶ Avvia Build APK",
            command=self.on_start_build,
            font=("Segoe UI", 10, "bold"),
            bg="#27ae60",
            fg="white",
            padx=20,
            pady=5,
        )
        self.start_btn.pack(side="left", padx=5)

        self.release_check = ttk.Checkbutton(
            button_frame,
            text="Release (firma per Play Store)",
            variable=self.release_var,
        )
        self.release_check.pack(side="left", padx=15)

        self.cancel_btn = Button(
            button_frame,
            text="Annulla",
            command=self.on_cancel,
            font=("Segoe UI", 10),
            bg="#e74c3c",
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=5)

        self.open_folder_btn = Button(
            button_frame,
            text="Apri Cartella APK",
            command=self.on_open_folder,
            font=("Segoe UI", 10),
            bg="#3498db",
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.open_folder_btn.pack(side="left", padx=5)

        self.close_btn = Button(
            button_frame,
            text="Chiudi",
            command=self.on_close,
            font=("Segoe UI", 10),
            bg="#95a5a6",
            fg="white",
            padx=15,
            pady=5,
            state="disabled",
        )
        self.close_btn.pack(side="right", padx=5)

    def _start_polling(self) -> None:
        self.poll_start_time = time.time()
        self.root.after(100, self._poll_status)

    def _poll_status(self) -> None:
        # Timeout di sicurezza
        elapsed_polling = time.time() - self.poll_start_time
        if self.build_started and elapsed_polling > POLLING_TIMEOUT and not self.should_cancel:
            messagebox.showerror(
                "Timeout",
                f"Build APK in timeout dopo {POLLING_TIMEOUT/60:.0f} min.\n"
                "Il processo potrebbe essere bloccato (controllare WSL).\n"
                "Chiudere la finestra per terminare il build.",
            )
            self.status_label.config(text="✗ TIMEOUT Build APK", fg="#e74c3c")
            self.cancel_btn.config(state="normal")
            return

        if not self.build_started:
            self.root.after(500, self._poll_status)
            return

        if not self.status_file.exists():
            self.root.after(500, self._poll_status)
            return

        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                status = json.load(f)

            progress = status.get("progress", 0)
            current_timestamp = status.get("timestamp", 0)
            self.progress_var.set(progress)

            # Track progress change (per animazioni). Niente popup di warning:
            # le fasi 45-80% (Python ARM compile) e 95-99% (gradle/dexing/signing)
            # sono naturalmente lunghe e poco verbose. Il banner giallo in alto
            # già avvisa l'utente che la prima build dura 30-50 min.
            if progress != self.last_progress:
                self.last_progress = progress
                self.last_progress_change = time.time()
                self.last_timestamp = current_timestamp

            time_since_change = time.time() - self.last_progress_change
            log_lines_count = len(status.get("log", []))

            # Animazione punti per le fasi lunghe e silenti
            if 45 <= progress < 80 and self.build_started and status.get("success") is None:
                dots = "." * ((self._anim_tick % 6) + 1)
                self._anim_tick += 1
                self.percent_label.config(text=f"{progress}%  cross-compile{dots}")
            elif progress >= 95 and self.build_started and status.get("success") is None:
                # Fase finale: gradle assemble + d8 dex + apksigner + copy bin/.
                # Poco verbose ma molto attiva, mostriamo solo segno di vita.
                dots = "." * ((self._anim_tick % 4) + 1)
                self._anim_tick += 1
                self.percent_label.config(
                    text=f"{progress}%  packaging finale{dots}  ({time_since_change/60:.1f} min)"
                )
            else:
                self._anim_tick = 0
                self.percent_label.config(text=f"{progress}%")

            step = status.get("step", "")
            self.status_label.config(text=step)

            log_lines = status.get("log", [])
            self._update_log(log_lines)

            if status.get("success") is not None:
                self._on_build_complete(status)
                return

        except (json.JSONDecodeError, IOError):
            pass

        self.root.after(500, self._poll_status)

    def _update_log(self, log_lines: list) -> None:
        self.log_text.config(state="normal")
        current_text = self.log_text.get("1.0", "end-1c")
        new_lines = "\n".join(log_lines)
        if current_text != new_lines:
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", new_lines)
            self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_build_complete(self, status: dict) -> None:
        success = status.get("success", False)
        if success:
            self.status_label.config(text="✓ APK pronto!", fg="#27ae60")
            self.progress_var.set(100)
            self.percent_label.config(text="100%")
            self.cancel_btn.config(state="disabled")
            self.open_folder_btn.config(state="normal")
            self.close_btn.config(state="normal")
            apk_path = status.get("apk_path")
            apk_size = status.get("apk_size_mb")
            size_str = f" ({apk_size:.1f} MB)" if apk_size else ""
            msg = f"APK pronto!{size_str}\n\n{apk_path}" if apk_path else "Build completata."
            messagebox.showinfo("Successo", msg)
        else:
            self.status_label.config(text="✗ Errore build APK", fg="#e74c3c")
            self.cancel_btn.config(state="disabled")
            self.close_btn.config(state="normal")
            error_msg = status.get("error_msg", "Errore sconosciuto")
            messagebox.showerror("Errore", f"Build APK fallito:\n\n{error_msg}")

    def on_start_build(self) -> None:
        if self.build_started:
            messagebox.showwarning("Attenzione", "Build già avviato!")
            return
        self.build_started = True
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        try:
            from engine.utils import get_base_path
            project_root = get_base_path()
            mgr_script = project_root / "editor" / "android_build_manager.py"

            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)

            if getattr(sys, "frozen", False):
                cmd = [
                    sys.executable,
                    "--android-build-manager",
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]
            else:
                cmd = [
                    sys.executable,
                    str(mgr_script),
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]
            if self.release_var.get() == 1:
                cmd.append("--release")

            self.build_process = subprocess.Popen(cmd, cwd=str(project_root), env=env)
            self.status_label.config(text="Build APK in corso (può durare 30-50 min)...", fg="#e67e22")
            self.release_check.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile avviare build APK:\n{e}")
            self.start_btn.config(state="normal")
            self.build_started = False

    def on_cancel(self) -> None:
        if not messagebox.askyesno("Conferma", "Annullare la build APK?"):
            return
        self.should_cancel = True
        self.cancel_btn.config(state="disabled")
        self.status_label.config(text="Annullamento in corso...", fg="#f39c12")

        if self.build_process:
            try:
                self.build_process.terminate()
                try:
                    self.build_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.build_process.kill()
            except Exception as e:
                print(f"[Cancel] Errore termination: {e}")

        # Termina anche l'albero buildozer/gradle DENTRO la distro WSL: uccidere il
        # processo Windows non propaga ai processi Linux, che altrimenti continuano
        # un cross-compile multi-GB di ~50 minuti in background.
        try:
            subprocess.run(
                ["wsl", "-u", "root", "-e", "bash", "-lc",
                 "pkill -9 -f buildozer; pkill -9 -f gradle; pkill -9 -f sdkmanager; true"],
                capture_output=True, timeout=30,
            )
        except Exception as e:
            print(f"[Cancel] WSL pkill fallito: {e}")

        try:
            if self.status_file.exists():
                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)
                status["canceled"] = True
                status["error_msg"] = "Build APK annullato dall'utente"
                with open(self.status_file, "w", encoding="utf-8") as f:
                    json.dump(status, f, indent=2)
        except Exception as e:
            print(f"[Cancel] Errore aggiornamento status: {e}")

    def on_open_folder(self) -> None:
        folder = self.build_dir.resolve()
        if not folder.exists():
            messagebox.showerror("Errore", f"Cartella non trovata:\n{folder}")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire cartella:\n{e}")

    def on_close(self) -> None:
        if self.should_cancel or self.progress_var.get() == 100:
            self.root.destroy()
        else:
            if messagebox.askyesno("Conferma", "La build APK è ancora in corso. Chiudere comunque?"):
                self.should_cancel = True
                self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def show_android_build_progress(game_id: str, version: str, build_dir: str, status_file: str) -> None:
    window = AndroidBuildProgressWindow(game_id, version, build_dir, status_file)
    window.run()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <game_id> <version> <build_dir> [<status_file>]")
        sys.exit(1)

    game_id = sys.argv[1]
    version = sys.argv[2]
    build_dir = sys.argv[3]
    status_file = sys.argv[4] if len(sys.argv) > 4 else str(Path(build_dir) / "build_status.json")

    show_android_build_progress(game_id, version, build_dir, status_file)
