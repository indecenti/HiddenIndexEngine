import sys
import os
import shutil
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

def get_base_path() -> Path:
    return Path(__file__).resolve().parent

class EditorBuilderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HiddenEngine - Editor Packager")
        self.root.geometry("650x500")
        self.root.resizable(True, True)
        self.base_path = get_base_path()
        self._build_thread = None

        self._create_widgets()

    def _create_widgets(self):
        # Header
        header = tk.Frame(self.root, bg="#2c3e50", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="Compilazione HiddenEngine Editor", 
            font=("Segoe UI", 14, "bold"), fg="#ecf0f1", bg="#2c3e50"
        ).pack(pady=10)

        # Status & Progress
        status_frame = tk.Frame(self.root)
        status_frame.pack(fill="x", padx=15, pady=10)
        
        self.status_lbl = tk.Label(status_frame, text="Pronto per pacchettizzare l'Editor.", font=("Segoe UI", 10))
        self.status_lbl.pack(anchor="w")

        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=600)
        self.progress.pack(fill="x", pady=5)

        # Log Text
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        tk.Label(log_frame, text="Registro operazioni:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.log_txt = scrolledtext.ScrolledText(log_frame, height=12, font=("Courier New", 9), bg="#ecf0f1")
        self.log_txt.pack(fill="both", expand=True)
        self.log_txt.config(state="disabled")

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=15, pady=15)

        self.btn_build = tk.Button(btn_frame, text="▶ Avvia Compilazione Editor", font=("Segoe UI", 10, "bold"), 
                                   bg="#27ae60", fg="white", padx=15, command=self.start_build)
        self.btn_build.pack(side="left")

        self.btn_open = tk.Button(btn_frame, text="Apri Cartella Output", font=("Segoe UI", 10), 
                                  bg="#3498db", fg="white", padx=10, state="disabled", command=self.open_output)
        self.btn_open.pack(side="left", padx=10)

        tk.Button(btn_frame, text="Chiudi", font=("Segoe UI", 10), bg="#95a5a6", fg="white", 
                  padx=10, command=self.root.destroy).pack(side="right")

    def log(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_txt.config(state="normal")
        self.log_txt.insert("end", message + "\n")
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")

    def set_status(self, text, color="black"):
        self.root.after(0, lambda: self.status_lbl.config(text=text, fg=color))

    def start_build(self):
        if self._build_thread and self._build_thread.is_alive():
            return
        
        self.btn_build.config(state="disabled")
        self.btn_open.config(state="disabled")
        self.progress.start(10)
        self.log_txt.config(state="normal")
        self.log_txt.delete("1.0", "end")
        self.log_txt.config(state="disabled")

        self._build_thread = threading.Thread(target=self._build_process, daemon=True)
        self._build_thread.start()

    def _build_process(self):
        try:
            self.set_status("Fase 1: Esecuzione PyInstaller (potrebbe richiedere minuti)...", "blue")
            self.log("Inizializzazione PyInstaller per run_editor.py...")
            
            entry_point = self.base_path / "run_editor.py"
            if not entry_point.exists():
                raise FileNotFoundError("run_editor.py non trovato nella root del progetto.")

            # PyInstaller command
            cmd = [
                "pyinstaller",
                str(entry_point),
                "-y",              # Sovrascrive dist senza chiedere
                "-D",              # Directory mode
                "-w",              # Senza console cmd
                "--name=HiddenEditor",
                "--clean",
                "--collect-all=jsonschema",
                "--collect-all=jsonschema_specifications",
                "--collect-all=rpds",
                "--hidden-import=cv2",
                "--hidden-import=numpy",
                "--hidden-import=scipy.ndimage",
            ]

            # Esclusioni pesanti
            exclusions = [
                "torch", "torchvision", "torchaudio", "onnxruntime", 
                "sklearn", "matplotlib", "pandas", "pyarrow", 
                "transformers", "tokenizers", "llvmlite", "numba", 
                "lxml", "IPython", "notebook", "jupyter"
            ]
            for ex in exclusions:
                if f"--exclude-module={ex}" not in cmd:
                    cmd.append(f"--exclude-module={ex}")
                    
            # Aggiunta dinamica di tutti i minigiochi noti
            mg_dir = self.base_path / "engine" / "minigames"
            if mg_dir.exists():
                for sub in mg_dir.iterdir():
                    if sub.is_dir() and sub.name != "__pycache__":
                        mg_id = sub.name
                        cmd.append(f"--hidden-import=engine.minigames.{mg_id}.{mg_id}_game")
                        
            # Aggiungiamo icona se presente
            icon_path = self.base_path / "editor" / "assets" / "icon.ico"
            if icon_path.exists():
                cmd.append(f"--icon={icon_path}")

            self.log(f"Esecuzione comando: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd, cwd=str(self.base_path),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log(line)

            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"PyInstaller terminato con codice errore {process.returncode}")

            self.set_status("Fase 2: Copia degli asset e configurazioni esterne...", "blue")
            self.log("\n--- POST BUILD: Copia file esterni ---")
            
            dist_dir = self.base_path / "dist" / "HiddenEditor"
            if not dist_dir.exists():
                raise FileNotFoundError(f"Cartella di output non trovata: {dist_dir}")

            # Crea struttura esterna per l'editor
            engine_dest = dist_dir / "engine"
            if engine_dest.exists():
                shutil.rmtree(engine_dest)
                
            # Dobbiamo copiare l'INTERO sorgente dell'engine e main.py!
            # L'editor ha bisogno del sorgente puro per passarlo a PyInstaller quando compila un gioco.
            self.log("Copia cartella engine (sorgenti inclusi)...")
            shutil.copytree(
                self.base_path / "engine", engine_dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
            
            main_src = self.base_path / "main.py"
            if main_src.exists():
                shutil.copy2(main_src, dist_dir / "main.py")
                self.log("Copia main.py...")

            # Crea cartelle vuote per l'ambiente di lavoro
            (dist_dir / "games").mkdir(exist_ok=True)
            (dist_dir / "saves").mkdir(exist_ok=True)
            
            # Copia config.ini
            config_src = self.base_path / "config.ini"
            if config_src.exists():
                shutil.copy2(config_src, dist_dir / "config.ini")
                self.log("Copiato config.ini")

            self.log("Post-build completato con successo.")
            self.set_status("✓ Compilazione Editor Completata!", "green")
            
            self.root.after(0, lambda: self.btn_open.config(state="normal"))
            messagebox.showinfo("Successo", "HiddenEditor è stato pacchettizzato correttamente in dist/HiddenEditor/")

        except Exception as e:
            self.log(f"\nERRORE FATALE: {str(e)}")
            self.set_status("✗ Errore durante la compilazione", "red")
            messagebox.showerror("Errore", str(e))
        finally:
            self.root.after(0, self._stop_progress)

    def _stop_progress(self):
        self.progress.stop()
        self.btn_build.config(state="normal")

    def open_output(self):
        folder = self.base_path / "dist" / "HiddenEditor"
        if folder.exists():
            os.startfile(str(folder))

if __name__ == "__main__":
    root = tk.Tk()
    app = EditorBuilderApp(root)
    root.mainloop()
