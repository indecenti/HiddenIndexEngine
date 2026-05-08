"""
editor/build_ui.py

Interfaccia grafica Tkinter per il progresso della compilazione.
Lancia come subprocess indipendente dalla finestra editor Pygame.

Comunica col processo padre via file JSON di stato.
"""

import json
import time
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Tk, Frame, Label, Text, Button, messagebox, simpledialog, IntVar
from tkinter import ttk
from tkinter import scrolledtext

# Timeout per il polling e deadlock detection
POLLING_TIMEOUT = 600  # 10 minuti max senza progresso prima di segnalare blocco
DEADLOCK_CHECK_INTERVAL = 3  # Check ogni 3 secondi


class BuildProgressWindow:
    """Finestra Tkinter che mostra il progresso del build."""

    def __init__(self, game_id: str, version: str, build_dir: str, status_file: str):
        self.game_id = game_id
        self.version = version
        self.build_dir = Path(build_dir)
        self.status_file = Path(status_file)
        self.build_process = None
        self.should_cancel = False
        self.build_started = False

        # Setup window
        self.root = Tk()
        self.root.title(f"Compilazione: {game_id} v{version}")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.zip_var = IntVar(value=0)  # ZIP opzionale, default FALSE

        # Timing per deadlock detection
        self.poll_start_time = time.time()
        self.last_progress_change = time.time()
        self.last_progress = 0
        self.last_timestamp = 0

        self._create_widgets()
        self._start_polling()

    def _create_widgets(self):
        """Crea gli elementi della UI."""
        # ── Header frame ─────────────────────────────────────────────────────
        header = Frame(self.root, bg="#2c3e50", height=60)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        title_label = Label(
            header,
            text=f"Compilazione: {self.game_id} v{self.version}",
            font=("Segoe UI", 14, "bold"),
            fg="#ecf0f1",
            bg="#2c3e50",
        )
        title_label.pack(pady=10)

        # ── Status frame ─────────────────────────────────────────────────────
        status_frame = Frame(self.root)
        status_frame.pack(fill="x", padx=15, pady=10)

        self.status_label = Label(
            status_frame, text="Inizializzazione...", font=("Segoe UI", 10), fg="#34495e"
        )
        self.status_label.pack(anchor="w")

        # ── Progress bar ─────────────────────────────────────────────────────
        progress_frame = Frame(self.root)
        progress_frame.pack(fill="x", padx=15, pady=5)

        self.progress_var = IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            length=550,
            mode="determinate",
            variable=self.progress_var,
            maximum=100,
        )
        self.progress_bar.pack(fill="x")

        self.percent_label = Label(
            progress_frame, text="0%", font=("Segoe UI", 9), fg="#7f8c8d"
        )
        self.percent_label.pack(anchor="e", pady=2)

        # ── Log frame (scrollable text) ──────────────────────────────────────
        log_frame = Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)

        log_label = Label(log_frame, text="Registro compilazione:", font=("Segoe UI", 10, "bold"))
        log_label.pack(anchor="w")

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            width=70,
            font=("Courier New", 9),
            bg="#ecf0f1",
            fg="#2c3e50",
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, pady=5)

        # ── Button frame ─────────────────────────────────────────────────────
        button_frame = Frame(self.root)
        button_frame.pack(fill="x", padx=15, pady=10)

        self.start_btn = Button(
            button_frame,
            text="▶ Avvia Build",
            command=self.on_start_build,
            font=("Segoe UI", 10, "bold"),
            bg="#27ae60",
            fg="white",
            padx=20,
            pady=5,
        )
        self.start_btn.pack(side="left", padx=5)

        self.zip_check = ttk.Checkbutton(
            button_frame,
            text="Genera Archivio ZIP",
            variable=self.zip_var,
            style="Small.TCheckbutton"
        )
        self.zip_check.pack(side="left", padx=15)

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
            text="Apri Cartella",
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

    def _start_polling(self):
        """Inicia il polling del file di stato."""
        self._anim_tick = 0
        self.poll_start_time = time.time()
        self.root.after(100, self._poll_status)

    def _poll_status(self):
        """Poll periodico del file di stato JSON."""
        # Verifica timeout globale del polling
        elapsed_polling = time.time() - self.poll_start_time
        if self.build_started and elapsed_polling > POLLING_TIMEOUT and not self.should_cancel:
            messagebox.showerror(
                "Timeout",
                f"Build in timeout dopo {POLLING_TIMEOUT}s.\n"
                f"Il processo potrebbe essere bloccato.\n"
                "Chiudere la finestra per terminar il build."
            )
            self.status_label.config(text="✗ TIMEOUT Build", fg="#e74c3c")
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

            # Aggiorna progress bar
            progress = status.get("progress", 0)
            current_timestamp = status.get("timestamp", 0)
            self.progress_var.set(progress)

            # Rilevamento deadlock: progresso fermo per troppo tempo
            if progress != self.last_progress:
                self.last_progress = progress
                self.last_progress_change = time.time()
                self.last_timestamp = current_timestamp
            else:
                # Progresso non cambiato
                time_since_change = time.time() - self.last_progress_change
                if self.build_started and time_since_change > 120 and status.get("success") is None:
                    # Progresso fermo per più di 2 minuti
                    if status.get("error_msg") is None:
                        # Il build manager non ha ancora segnalato errore
                        messagebox.showwarning(
                            "Attenzione",
                            f"Build potrebbe essere bloccato:\n"
                            f"Progresso fermo a {progress}% per {time_since_change:.0f}s.\n\n"
                            f"Prova ad annullare o attendere ancora."
                        )

            # Animazione durante PyInstaller (rimane tra 70-85% per minuti)
            if 70 <= progress < 85 and self.build_started and status.get("success") is None:
                dots = "." * ((self._anim_tick % 6) + 1)
                self._anim_tick += 1
                self.percent_label.config(text=f"{progress}%  PyInstaller{dots}")
            else:
                self._anim_tick = 0
                self.percent_label.config(text=f"{progress}%")

            # Aggiorna status label
            step = status.get("step", "")
            self.status_label.config(text=step)

            # Aggiorna log
            log_lines = status.get("log", [])
            self._update_log(log_lines)

            # Verifica se il build è finito
            if status.get("success") is not None:
                self._on_build_complete(status)
                return

        except (json.JSONDecodeError, IOError):
            pass

        # Continua il polling
        self.root.after(500, self._poll_status)

    def _update_log(self, log_lines):
        """Aggiorna il testo del log."""
        self.log_text.config(state="normal")
        current_text = self.log_text.get("1.0", "end-1c")
        new_lines = "\n".join(log_lines)

        if current_text != new_lines:
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", new_lines)
            self.log_text.see("end")

        self.log_text.config(state="disabled")

    def _on_build_complete(self, status):
        """Chiamato quando il build è completo."""
        success = status.get("success", False)

        if success:
            self.status_label.config(text="✓ Compilazione completata!", fg="#27ae60")
            self.progress_var.set(100)
            self.percent_label.config(text="100%")
            self.cancel_btn.config(state="disabled")
            self.open_folder_btn.config(state="normal")
            self.close_btn.config(state="normal")
            zip_path = status.get("zip_path")
            zip_line = f"\nZIP: {zip_path}" if zip_path else "\n(nessun archivio ZIP creato)"
            messagebox.showinfo("Successo", f"Build completato!{zip_line}")
        else:
            self.status_label.config(text="✗ Errore compilazione", fg="#e74c3c")
            self.cancel_btn.config(state="disabled")
            self.close_btn.config(state="normal")
            error_msg = status.get("error_msg", "Errore sconosciuto")
            messagebox.showerror("Errore", f"Build fallito:\n\n{error_msg}")

    def on_start_build(self):
        """Avvia il build tramite subprocess."""
        if self.build_started:
            messagebox.showwarning("Attenzione", "Build già avviato!")
            return

        self.build_started = True
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        try:
            # Lancia build_manager.py come subprocess
            from engine.utils import get_base_path
            project_root = get_base_path()
            build_manager_script = project_root / "editor" / "build_manager.py"

            # Imposta il PYTHONPATH per includere la cartella del progetto
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)

            # Argomenti base
            import sys
            if getattr(sys, 'frozen', False):
                cmd = [
                    sys.executable,
                    "--build-manager",
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]
            else:
                cmd = [
                    sys.executable,
                    str(build_manager_script),
                    self.game_id,
                    self.version,
                    str(self.build_dir),
                    str(self.status_file),
                ]

            # Aggiunge --no-zip se il checkbox non è selezionato
            if self.zip_var.get() == 0:
                cmd.append("--no-zip")

            self.build_process = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                env=env,
            )
            self.status_label.config(text="Build in corso...", fg="#e67e22")
            self.zip_check.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile avviare build:\n{e}")
            self.start_btn.config(state="normal")
            self.build_started = False

    def on_cancel(self):
        """Annulla la compilazione."""
        if messagebox.askyesno("Conferma", "Annullare la compilazione?"):
            self.should_cancel = True
            self.cancel_btn.config(state="disabled")
            self.status_label.config(text="Annullamento in corso...", fg="#f39c12")

            if self.build_process:
                try:
                    print(f"[Cancel] Terminating process {self.build_process.pid}")
                    self.build_process.terminate()
                    # Attendi 5 secondi, poi kill se necessario
                    try:
                        self.build_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print(f"[Cancel] Force killing process {self.build_process.pid}")
                        self.build_process.kill()
                except Exception as e:
                    print(f"[Cancel] Errore termination: {e}")

            # Aggiorna file di stato per segnalare cancellazione
            try:
                if self.status_file.exists():
                    with open(self.status_file, "r", encoding="utf-8") as f:
                        status = json.load(f)
                    status["canceled"] = True
                    status["error_msg"] = "Build annullato dall'utente"
                    with open(self.status_file, "w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)
            except Exception as e:
                print(f"[Cancel] Errore aggiornamento status: {e}")

    def on_open_folder(self):
        """Apre la cartella di output."""
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

    def on_close(self):
        """Chiude la finestra."""
        if self.should_cancel or self.progress_var.get() == 100:
            self.root.destroy()
        else:
            if messagebox.askyesno("Conferma", "La compilazione è ancora in corso. Chiudere comunque?"):
                self.should_cancel = True
                self.root.destroy()

    def run(self):
        """Avvia la finestra."""
        self.root.mainloop()


def show_build_progress(game_id: str, version: str, build_dir: str, status_file: str):
    """Entry point per lanciare la finestra UI."""
    window = BuildProgressWindow(game_id, version, build_dir, status_file)
    window.run()


if __name__ == "__main__":
    # Esecuzione da riga di comando per testing
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <game_id> <version> <build_dir> <status_file>")
        sys.exit(1)

    game_id = sys.argv[1]
    version = sys.argv[2]
    build_dir = sys.argv[3]
    status_file = sys.argv[4] if len(sys.argv) > 4 else "build_status.json"

    show_build_progress(game_id, version, build_dir, status_file)
