# ==============================================================================
# SMART_METRIC.PY - Metrische Analyse V1.0.0 (GitHub Release)
# ==============================================================================
import tkinter as tk
import customtkinter as ctk
import os
import threading
import shutil
import csv
import subprocess
import sys
import numpy as np
from tkinter import filedialog, messagebox

# Analysis Imports
from astropy.io import fits
import sep
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# Import Logic
import smart_utils as utils

# --- HELPER: KUGELSICHERES ENVIRONMENT FÜR SUBPROZESSE ---
def get_clean_env():
    """ 
    Entfernt alle von PyInstaller gesetzten Python-Umgebungsvariablen 
    und stellt den originalen Windows-PATH wieder her. 
    Verhindert DLL-Konflikte (Error 3221225781) bei externen Programmen wie Siril.
    """
    env = os.environ.copy()
    
    # 1. Alle Python & UI Variablen radikal löschen (inkl. TCL/TK)
    bad_keys = ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "PYTHONWARNINGS", "PYTHONIOENCODING", "TCL_LIBRARY", "TK_LIBRARY"]
    for k in bad_keys:
        env.pop(k, None)
        
    # 2. PATH extrem aggressiv bereinigen (Schutz vor Windows 8.3 Short-Names wie _MEI12~1)
    orig_path = env.get("PYINSTALLER_ORIG_PATH")
    if orig_path:
        env["PATH"] = orig_path
    else:
        paths = env.get("PATH", "").split(os.pathsep)
        clean_paths = []
        for p in paths:
            # Wir filtern ALLES raus, was das PyInstaller-Kürzel (_MEI) enthält (ignoriert Groß-/Kleinschreibung)
            if '_MEI' in p.upper():
                continue
            clean_paths.append(p)
        env["PATH"] = os.pathsep.join(clean_paths)
        
    return env


# --- HILFSKLASSE FÜR TOOLTIPS ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tw, text=self.text, justify='left',
                       background="#2b2b2b", foreground="white", 
                       relief='solid', borderwidth=1,
                       font=("Arial", 10, "normal"))
        lbl.pack(ipadx=6, ipady=3)

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

# --- SIRIL FENSTER ---
class SirilLogWindow(ctk.CTkToplevel):
    def __init__(self, parent, siril_path, work_dir, script_path):
        super().__init__(parent)
        self.title("Siril Prozess Überwachung")
        self.geometry("900x600+100+100")
        self.siril_path = siril_path; self.work_dir = work_dir; self.script_path = script_path
        self.process = None
        if os.path.exists("smartsuite.ico"):
            try: 
                self.wm_iconbitmap("smartsuite.ico")
            except Exception as e: 
                utils.log.debug(f"Konnte Icon für SirilLogWindow nicht laden: {e}")
                
        self.after(100, self.lift); self.after(100, self.focus_force)
        
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        
        self.lbl_info = ctk.CTkLabel(self, text=f"Führe Skript aus: {os.path.basename(script_path)}", font=("Arial", 14, "bold"))
        self.lbl_info.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12), activate_scrollbars=True)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)
        
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=2, column=0, pady=20, sticky="ew")
        self.footer.grid_columnconfigure(0, weight=1); self.footer.grid_columnconfigure(1, weight=1)
        
        self.btn_open = ctk.CTkButton(self.footer, text="📂 Arbeitsverzeichnis öffnen", command=self.open_dir, state="disabled", width=250, fg_color="gray")
        self.btn_open.grid(row=0, column=0, padx=10)
        self.btn_close = ctk.CTkButton(self.footer, text="Abbrechen (Prozess läuft...)", command=self.close_window, fg_color="#c0392b", width=250)
        self.btn_close.grid(row=0, column=1, padx=10)
        
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        cmd = [self.siril_path, "-d", self.work_dir, "-s", self.script_path]
        try:
            kwargs = {}
            if os.name == 'nt': 
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs['startupinfo'] = startupinfo
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            # --- Nutze die neue Environment Helper Funktion ---
            kwargs['env'] = get_clean_env()
            # ------------------------------------------------
            
            utils.log.info(f"Starte Siril Prozess: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd, cwd=self.work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                stdin=subprocess.DEVNULL, # NEU: Verhindert Handle-Konflikte (Crashes) bei Konsolen-Apps in Windows
                text=True, encoding='utf-8', errors='replace', **kwargs
            )
            
            for line in iter(self.process.stdout.readline, ''): 
                self.after(0, lambda l=line.strip(): (self.log_box.insert("end", l+"\n"), self.log_box.see("end")))
            
            rc = self.process.wait()
            if rc == 0:
                utils.log.info("Siril Skript erfolgreich beendet.")
                self.after(0, lambda: (self.log_box.insert("end", "\n--- FERTIG ---\n"), self.btn_close.configure(text="Fertig / Schließen", fg_color="#27ae60", command=self.destroy), self.btn_open.configure(state="normal", fg_color="#2980b9")))
            else:
                utils.log.error(f"Siril Skript mit Fehler beendet. Return Code: {rc}")
                self.after(0, lambda: (self.log_box.insert("end", f"\n--- FEHLER (Code {rc}) ---\n"), self.btn_close.configure(text="Schließen (Fehler)", fg_color="#e67e22")))
        
        except Exception as e:
            err_msg = str(e) 
            utils.log.exception(f"Kritischer Fehler beim Ausführen von Siril: {e}")
            self.after(0, lambda err=err_msg: self.log_box.insert("end", f"CRITICAL: {err}\n"))

    def open_dir(self):
        if not os.path.exists(self.work_dir): return
        if os.name == 'nt': os.startfile(self.work_dir)
        elif sys.platform == 'darwin': subprocess.Popen(['open', self.work_dir])
        else: subprocess.Popen(['xdg-open', self.work_dir])

    def close_window(self):
        if self.process and self.process.poll() is None:
            if messagebox.askyesno("?", "Siril läuft noch. Wirklich abbrechen?"):
                try: 
                    self.process.kill()
                    utils.log.info("Siril Prozess durch User abgebrochen.")
                except Exception as e: 
                    utils.log.error(f"Konnte Siril Prozess nicht abbrechen: {e}")
                self.destroy()
        else: self.destroy()


# --- METRIK HAUPTFENSTER ---
class MetricAnalysisWindow(ctk.CTkToplevel):
    def __init__(self, parent, folder_path):
        super().__init__(parent)
        self.title("Metrische Analyse & Smart Scoring")
        self.geometry("1750x950+50+50")
        self.folder_path = folder_path
        
        self.analysis_results = []
        self.filtered_results = []
        self.is_running = False
        self.stop_req = False
        
        if os.path.exists("smartsuite.ico"):
            try: 
                self.wm_iconbitmap("smartsuite.ico")
            except Exception as e: 
                utils.log.debug(f"Konnte Icon für Metrik-Fenster nicht laden: {e}")
            
        self.after(100, self.lift)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0); self.grid_rowconfigure(2, weight=0); self.grid_rowconfigure(3, weight=0)

        self._build_ui()

    def _build_ui(self):
        # 1. Log UI (Unten)
        self.log_frame = ctk.CTkFrame(self, height=150)
        self.log_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0,10))
        self.lbl_st = ctk.CTkLabel(self.log_frame, text="Bereit...", anchor="w"); self.lbl_st.pack(fill=tk.X, padx=5, pady=2)
        self.prog = ctk.CTkProgressBar(self.log_frame); self.prog.pack(fill=tk.X, padx=5, pady=5); self.prog.set(0)
        self.log_box = ctk.CTkTextbox(self.log_frame, height=100, font=("Consolas", 12)); self.log_box.pack(fill=tk.BOTH, padx=5, pady=5)

        self.siril_path = utils.find_siril_path()
        self.scripts = utils.scan_siril_scripts(lambda t: self.log_box.insert("end", t+"\n"))
        self.py_scripts = utils.scan_siril_python_scripts(lambda t: self.log_box.insert("end", t+"\n"))
        
        self.log_box.insert("end", f">> {len(self.scripts)} SSF-Skripte und {len(self.py_scripts)} Py-Skripte gefunden.\n"); self.log_box.see("end")

        # 2. Graphen (Mitte) - 2x3 LAYOUT
        self.g_frame = ctk.CTkFrame(self); self.g_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        plt.style.use('dark_background')
        self.fig = Figure(figsize=(12, 7), dpi=100)
        
        self.ax_fw = self.fig.add_subplot(231)
        self.ax_sn = self.fig.add_subplot(232)
        self.ax_ec = self.fig.add_subplot(233)
        self.ax_bk = self.fig.add_subplot(234)
        self.ax_st = self.fig.add_subplot(235) 
        self.ax_sc = self.fig.add_subplot(236) 
        
        self.fig.subplots_adjust(hspace=0.4, wspace=0.25)
        self.can = FigureCanvasTkAgg(self.fig, master=self.g_frame); self.can.draw(); self.can.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 3. Tools Frame (Steuerung)
        self.t_frame = ctk.CTkFrame(self, fg_color="#2b2b2b"); self.t_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(self.t_frame, text="Filter:", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=(10, 5))
        self.cmb_filter = ctk.CTkComboBox(self.t_frame, values=["Alle", "Broadband (IR/UV)", "Narrowband (LP/Dual)"], command=self.update_plots, width=170)
        self.cmb_filter.pack(side=tk.LEFT, padx=5); self.cmb_filter.set("Alle")

        self.btn_run = ctk.CTkButton(self.t_frame, text="▶ Start Analyse", width=120, command=self.run, fg_color="#2980b9")
        self.btn_run.pack(side=tk.LEFT, padx=15)
        
        self.btn_stop = ctk.CTkButton(self.t_frame, text="⏹ Stop", width=80, command=self.stop, fg_color="#c0392b", state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_folder = ctk.CTkButton(self.t_frame, text="📂", width=40, command=self.open_current_folder, fg_color="#7f8c8d", hover_color="#95a5a6")
        self.btn_folder.pack(side=tk.LEFT, padx=5)

        # Rechte Seite: Sortierung & KI
        self.s_frame = ctk.CTkFrame(self.t_frame, fg_color="transparent"); self.s_frame.pack(side=tk.RIGHT, padx=10, pady=10)
        
        self.btn_ai = ctk.CTkButton(self.s_frame, text="🤖 KI Prompt", width=90, command=self.generate_ai_prompt, fg_color="#8e44ad", state="disabled")
        self.btn_ai.pack(side=tk.RIGHT, padx=10)
        
        ctk.CTkLabel(self.s_frame, text="Aussortieren:", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        
        self.chk_fw = tk.BooleanVar(); self.chk_ec = tk.BooleanVar(); self.chk_bk = tk.BooleanVar()
        self.chk_st = tk.BooleanVar(); self.chk_sn = tk.BooleanVar(); self.chk_sc = tk.BooleanVar()
        
        def auto_check(var): var.set(True)
        
        score_group = ctk.CTkFrame(self.s_frame, fg_color="#3e1a1a", border_width=1, border_color="#e74c3c", corner_radius=5)
        score_group.pack(side="left", padx=(5, 15), pady=2)
        
        chk_sc_widget = ctk.CTkCheckBox(score_group, text="⭐ Score <", variable=self.chk_sc, width=20, font=("Arial", 12, "bold"), text_color="#ffcc00")
        chk_sc_widget.pack(side="left", padx=(8, 5), pady=4)
        
        self.e_sc = ctk.CTkEntry(score_group, width=40, font=("Arial", 12, "bold"))
        self.e_sc.pack(side="left", padx=(0, 8), pady=4)
        self.e_sc.bind("<KeyRelease>", lambda e: auto_check(self.chk_sc))
        
        crits = [
            ("FWHM >", self.chk_fw, 'e_fw', 40),
            ("SNR <", self.chk_sn, 'e_sn', 40),
            ("Ecc >", self.chk_ec, 'e_ec', 40),
            ("Bkg >", self.chk_bk, 'e_bk', 40),
            ("Stars <", self.chk_st, 'e_st', 40)
        ]
        
        for txt, var, attr, w in crits:
            group = ctk.CTkFrame(self.s_frame, fg_color="transparent")
            group.pack(side="left", padx=5)
            chk = ctk.CTkCheckBox(group, text=txt, variable=var, width=20, font=("Arial", 11))
            chk.pack(side="left", padx=(0, 5))
            ent = ctk.CTkEntry(group, width=w, font=("Arial", 11))
            ent.pack(side="left")
            ent.bind("<KeyRelease>", lambda e, v=var: auto_check(v))
            setattr(self, attr, ent)
            
        self.btn_sort = ctk.CTkButton(self.s_frame, text="🧹 Ausführen", width=90, command=self.sort_files, fg_color="#c0392b", state="disabled")
        self.btn_sort.pack(side=tk.LEFT, padx=15)

        # 4. Bottom Frame (CSV & Siril Tools 2-Zeilig)
        self.bot_frame = ctk.CTkFrame(self, fg_color="#1a1a1a", border_width=1, border_color="#3b8ed0")
        self.bot_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_csv = ctk.CTkButton(self.bot_frame, text="💾 CSV Export", width=120, command=self.export_csv, fg_color="#27ae60", state="disabled")
        self.btn_csv.pack(side=tk.LEFT, padx=15, pady=15)
        
        ctk.CTkFrame(self.bot_frame, width=2, height=60, fg_color="#333333").pack(side=tk.LEFT, padx=15)
        
        siril_container = ctk.CTkFrame(self.bot_frame, fg_color="transparent")
        siril_container.pack(side=tk.LEFT, fill="both", expand=True, padx=10, pady=5)
        
        # Zeile 1: SSF Skripte (Klassisch / Background)
        r1 = ctk.CTkFrame(siril_container, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="🚀 Siril CLI (Hintergrund):", font=("Arial", 11, "bold"), text_color="#3b8ed0", width=160, anchor="w").pack(side=tk.LEFT)
        self.cmb_siril = ctk.CTkComboBox(r1, values=list(self.scripts.keys()), width=300)
        self.cmb_siril.pack(side=tk.LEFT, padx=5)
        l_scr = utils.load_config().get("last_siril_script")
        if l_scr in self.scripts: self.cmb_siril.set(l_scr)
        
        self.btn_siril = ctk.CTkButton(r1, text="Start Skript", command=self.run_siril_gui, fg_color="#8e44ad", width=120)
        self.btn_siril.pack(side=tk.LEFT, padx=10)
        ToolTip(self.btn_siril, "Führt das gewählte .ssf Skript unsichtbar im Hintergrund aus.")
        
        # Zeile 2: Python Skripte & GUI
        r2 = ctk.CTkFrame(siril_container, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="🖥 Siril GUI (Aktiv):", font=("Arial", 11, "bold"), text_color="#2980b9", width=160, anchor="w").pack(side=tk.LEFT)
        
        py_vals = ["(Nur GUI öffnen)"] + list(self.py_scripts.keys())
        
        def on_py_combo_change(choice):
            if choice == "(Nur GUI öffnen)":
                self.btn_siril_app.configure(text="GUI Öffnen")
            else:
                self.btn_siril_app.configure(text="Py-Skript Ausführen")
                
        self.cmb_siril_py = ctk.CTkComboBox(r2, values=py_vals, width=300, command=on_py_combo_change)
        self.cmb_siril_py.pack(side=tk.LEFT, padx=5)
        self.cmb_siril_py.set("(Nur GUI öffnen)")
        
        self.btn_siril_app = ctk.CTkButton(r2, text="GUI Öffnen", command=self.open_siril_app, fg_color="#2980b9", width=140)
        self.btn_siril_app.pack(side=tk.LEFT, padx=10)
        
        ToolTip(self.btn_siril_app, "Startet Siril im aktuellen Verzeichnis.\n- (Nur GUI): Öffnet die normale Programmoberfläche.\n- (Py-Skript): Führt das Skript im schnellen Batch-Modus aus (ohne GUI).")
        
        if not self.siril_path: 
            self.btn_siril.configure(state="disabled", text="Siril fehlt")
            self.btn_siril_app.configure(state="disabled")

    def open_current_folder(self):
        if not self.folder_path or not os.path.exists(self.folder_path): return
        if os.name == 'nt': os.startfile(self.folder_path)
        elif sys.platform == 'darwin': subprocess.Popen(['open', self.folder_path])
        else: subprocess.Popen(['xdg-open', self.folder_path])

    def run_siril_gui(self):
        script_name = self.cmb_siril.get()
        if script_name and script_name in self.scripts:
            utils.save_config("last_siril_script", script_name)
            work_dir = self.folder_path
            if os.path.basename(work_dir).lower() == "lights": work_dir = os.path.dirname(work_dir)
            SirilLogWindow(self, self.siril_path, work_dir, self.scripts[script_name])
            
    def open_siril_app(self):
        if not self.siril_path: return
        
        gui_path = self.siril_path
        if gui_path.lower().endswith("siril-cli.exe"): 
            gui_path = gui_path[:-13] + "siril.exe"
        elif gui_path.lower().endswith("siril-cli"): 
            gui_path = gui_path[:-9] + "siril"
            
        work_dir = self.folder_path
        if os.path.basename(work_dir).lower() == "lights": 
            work_dir = os.path.dirname(work_dir)
            
        selected_py = self.cmb_siril_py.get()
            
        try:
            # --- Nutze die neue Environment Helper Funktion ---
            clean_env = get_clean_env()
            # ------------------------------------------------

            if selected_py and selected_py != "(Nur GUI öffnen)":
                # Temporäre .ssf Datei erstellen
                temp_ssf = os.path.join(work_dir, "_temp_run_py.ssf")
                
                # Vollen Pfad nutzen und Windows-Slashes umwandeln
                full_py_path = self.py_scripts.get(selected_py, selected_py).replace('\\', '/')
                
                with open(temp_ssf, "w", encoding="utf-8") as f:
                    f.write("requires 1.4.0\n")
                    f.write(f"pyscript \"{full_py_path}\"\n")
                
                # --- DER TRICK: Wir nutzen unser schönes Fenster! ---
                SirilLogWindow(self, self.siril_path, work_dir, temp_ssf)
                
                self.log_box.insert("end", f">> ⏳ Starte '{selected_py}' im Überwachungsfenster...\n")
                self.log_box.see("end")
                utils.log.info(f"Siril Py-Skript {selected_py} im Log-Fenster gestartet.")
                
            else:
                if not os.path.exists(gui_path):
                    messagebox.showerror("Fehler", f"Siril GUI nicht gefunden unter:\n{gui_path}")
                    return
                # Normaler GUI Start mit sauberem Environment
                subprocess.Popen([gui_path, "-d", work_dir], cwd=work_dir, env=clean_env)
                self.log_box.insert("end", f">> Siril GUI gestartet (Arbeitsverzeichnis gesetzt).\n")
                self.log_box.see("end")
                utils.log.info(f"Siril GUI manuell gestartet in {work_dir}")
                
        except Exception as e:
            utils.log.error(f"Konnte Siril GUI nicht starten: {e}")
            messagebox.showerror("Fehler", f"Start fehlgeschlagen:\n{e}")

    def run(self):
        if self.is_running: return
        self.is_running=True; self.stop_req=False
        self.btn_run.configure(state="disabled"); self.cmb_filter.configure(state="disabled")
        self.btn_stop.configure(state="normal"); self.log_box.delete("1.0","end")
        threading.Thread(target=self.worker, daemon=True).start()
    
    def stop(self): self.stop_req = True; self.log_box.insert("end", "!!! STOP ...\n"); self.log_box.see("end")

    def worker(self):
        try: 
            files = [f for f in os.listdir(self.folder_path) if f.lower().endswith(('.fit','.fits'))]
        except Exception as e: 
            utils.log.error(f"Fehler beim Lesen des Metrik-Ordners {self.folder_path}: {e}")
            files = []
            
        files.sort(); tot=len(files); self.analysis_results=[] 
        
        try: sep.set_extract_pixstack(20000000)
        except Exception as e: utils.log.debug(f"Konnte sep pixstack nicht setzen: {e}")
        try: sep.set_sub_object_limit(50000)
        except Exception as e: utils.log.debug(f"Konnte sep sub_object_limit nicht setzen: {e}")
        
        for i, f in enumerate(files):
            if self.stop_req: 
                self.after(0, lambda: self.log_box.insert("end", "Abbruch durch User.\n")); break
                
            p = os.path.join(self.folder_path, f)
            try:
                with fits.open(p) as h: hdr=h[0].header; dat=h[0].data
                if len(h)>1 and 'OBJECT' not in hdr: hdr = h[1].header
                if dat is None and len(h)>1: dat=h[1].data
                
                flt = str(hdr.get('FILTER', 'Unknown')).upper()
                dev = str(hdr.get('TELESCOP', 'Unknown'))
                
                if dat is not None:
                    step = 2 if dat.shape[1] > 2500 else 1
                    d_sm = dat[::step, ::step].astype(float)
                    
                    bkg = sep.Background(d_sm)
                    sub = d_sm - bkg
                    min_a = max(3, int(7 / (step*0.5))) 
                    
                    objs = sep.extract(sub, 5.0, err=bkg.globalrms, minarea=min_a)
                    
                    num = len(objs); fw = ec = sn = vi = 0
                    
                    if num > 0:
                        fw = np.median(2 * np.sqrt(np.log(2) * (objs['a']**2 + objs['b']**2))) * step
                        ec = np.median(np.sqrt(1 - (objs['b'] / objs['a'])**2))
                        sn_vals = objs['peak'] / bkg.globalrms
                        sn = np.median(sn_vals)
                        b_img = bkg.back()
                        b_max = np.max(b_img); b_min = np.min(b_img)
                        if b_max > 0: vi = ((b_max - b_min) / b_max) * 100.0
                        
                    else: fw=99.9; ec=1.0; sn=0; vi=0
                    
                    res = {
                        "f":f, "p":p, 
                        "fw":fw, "ec":ec, "bk":float(bkg.globalback), "st":num, 
                        "sn":sn, "vi":vi, "score": 0,
                        "obj":hdr.get('OBJECT',''), "exp":hdr.get('EXPTIME',''), 
                        "fil": flt, "dev": dev 
                    }
                    self.analysis_results.append(res)
                    
                    sub_txt = " (Sub)" if step > 1 else ""
                    msg = f"{i+1}: {flt}{sub_txt} | FWHM:{fw:.1f} | Ecc:{ec:.2f} | Stars:{num} | SNR:{sn:.1f}"
                    self.after(0, lambda m=msg, v=(i+1)/tot: (self.log_box.insert("end", m+"\n"), self.log_box.see("end"), self.prog.set(v), self.lbl_st.configure(text=f"Analysiere: {f}")))
            except Exception as e:
                utils.log.warning(f"Fehler bei metrischer Analyse von Bild '{f}': {e}")
                self.after(0, lambda err=e, fn=f: self.log_box.insert("end", f"Err {fn}: {err}\n"))
        
        if self.analysis_results:
            self.calculate_scores()

        self.after(0, self.finish_scan)

    def calculate_scores(self):
        try:
            fw = np.array([r['fw'] for r in self.analysis_results])
            ec = np.array([r['ec'] for r in self.analysis_results])
            sn = np.array([r['sn'] for r in self.analysis_results])
            bk = np.array([r['bk'] for r in self.analysis_results])
            st = np.array([r['st'] for r in self.analysis_results])

            fw_bad, fw_good = np.percentile(fw, 95), np.percentile(fw, 5)
            ec_bad, ec_good = np.percentile(ec, 95), np.percentile(ec, 5)
            bk_bad, bk_good = np.percentile(bk, 95), np.percentile(bk, 5)
            sn_bad, sn_good = np.percentile(sn, 5), np.percentile(sn, 95)
            st_bad, st_good = np.percentile(st, 5), np.percentile(st, 95)

            fw_bad = max(fw_bad, fw_good + 1.0) 
            ec_bad = max(ec_bad, ec_good + 0.15)
            bk_bad = max(bk_bad, bk_good + 30.0)
            sn_bad = min(sn_bad, sn_good - 5.0)  
            st_bad = min(st_bad, st_good - 10.0) 

            def norm(val, bad, good):
                if bad == good: return 1.0
                return np.clip((val - bad) / (good - bad), 0, 1)

            W_FW, W_SN, W_BK, W_EC, W_ST = 0.35, 0.20, 0.20, 0.15, 0.10

            for r in self.analysis_results:
                s_fw = norm(r['fw'], fw_bad, fw_good)
                s_ec = norm(r['ec'], ec_bad, ec_good)
                s_bk = norm(r['bk'], bk_bad, bk_good)
                s_sn = norm(r['sn'], sn_bad, sn_good)
                s_st = norm(r['st'], st_bad, st_good)

                final_score = (s_fw * W_FW + s_sn * W_SN + s_bk * W_BK + s_ec * W_EC + s_st * W_ST) * 100
                r['score'] = round(final_score, 1)
                
            utils.log.info("Smart Scores mit Mindest-Toleranz berechnet.")

        except Exception as e:
            utils.log.error(f"Fehler bei Score-Berechnung: {e}")

    def finish_scan(self):
        self.is_running=False
        self.btn_run.configure(state="normal"); self.btn_stop.configure(state="disabled"); self.cmb_filter.configure(state="normal")
        self.lbl_st.configure(text="Scan abgeschlossen.")
        if self.analysis_results: 
            self.btn_csv.configure(state="normal"); self.btn_sort.configure(state="normal")
            self.btn_ai.configure(state="normal")
            self.update_plots()

    def update_plots(self, _=None):
        mode = self.cmb_filter.get()
        self.filtered_results = []
        pdata = {"fwhm":[], "ecc":[], "bkg":[], "stars":[], "snr":[], "vig":[], "score":[], "idx":[]}
        nb_keys = ["LP", "DUO", "DB", "NB", "OIII", "HA", "SII", "H-ALPHA"]
        
        for i, r in enumerate(self.analysis_results):
            f_name = r['fil']
            is_narrow = any(k in f_name for k in nb_keys)
            keep = (mode == "Alle") or (mode.startswith("Broadband") and not is_narrow) or (mode.startswith("Narrowband") and is_narrow)
                
            if keep:
                self.filtered_results.append(r)
                if r['st'] > 2: 
                    pdata["fwhm"].append(r['fw']); pdata["ecc"].append(r['ec']); pdata["bkg"].append(r['bk'])
                    pdata["stars"].append(r['st']); pdata["snr"].append(r['sn']); pdata["vig"].append(r['vi'])
                    pdata["score"].append(r.get('score', 0))
                    pdata["idx"].append(i)
        
        if pdata["fwhm"]:
            try:
                self.e_fw.delete(0,'end'); self.e_fw.insert(0, f"{np.median(pdata['fwhm'])*1.2:.2f}")
                self.e_ec.delete(0,'end'); self.e_ec.insert(0, f"{np.median(pdata['ecc'])*1.2:.2f}")
                self.e_bk.delete(0,'end'); self.e_bk.insert(0, f"{np.median(pdata['bkg'])*1.1:.0f}")
                self.e_st.delete(0,'end'); self.e_st.insert(0, f"{np.median(pdata['stars'])*0.8:.0f}")
                self.e_sn.delete(0,'end'); self.e_sn.insert(0, f"{np.median(pdata['snr'])*0.7:.1f}")
                self.e_sc.delete(0,'end'); self.e_sc.insert(0, "40") 
            except Exception as e: 
                utils.log.debug(f"GUI-Update der Median-Werte fehlgeschlagen: {e}")
        
        self.draw_graphs(pdata, mode)

    def draw_graphs(self, data, suffix):
        def dr(ax, y, c, t, is_score=False):
            ax.clear()
            if not y: return
            
            lw = 2 if is_score else 1
            ms = 4 if is_score else 3
            
            ax.plot(data['idx'], y, 'o-', color=c, ms=ms, lw=lw)
            med = np.median(y); sig = np.std(y)
            ax.axhline(med, c='white', ls='--', label=f"Med: {med:.2f}")
            
            if is_score:
                ax.axhline(60, c='#2ecc71', ls='-', alpha=0.8, label="Keep (>60)")
                ax.axhline(40, c='#e74c3c', ls='-', alpha=0.8, label="Trash (<40)")
                title_color = '#ffcc00'
                fontsize = 10
                ax.set_facecolor('#1a0505') 
            else:
                ax.axhline(med+2*sig, c=c, ls=':', alpha=0.5)
                ax.axhline(med-2*sig, c=c, ls=':', alpha=0.5)
                ax.plot([], [], c=c, ls=':', label=f"±2σ: {med-2*sig:.1f}/{med+2*sig:.1f}")
                title_color = 'white'
                fontsize = 9
                ax.set_facecolor('#000000') 
            
            ax.set_title(t, color=title_color, fontsize=fontsize, fontweight='bold')
            ax.legend(facecolor='#333', labelcolor='white', fontsize=6)
            ax.grid(True, alpha=0.2)
            ax.tick_params(colors='white', labelsize=7)
        
        dr(self.ax_fw, data['fwhm'], '#4da6ff', f"FWHM ({suffix})")
        dr(self.ax_sn, data['snr'], '#ff66cc', "SNR")
        dr(self.ax_ec, data['ecc'], '#1abc9c', "Exzentrizität")
        dr(self.ax_bk, data['bkg'], '#00cc66', "Hintergrund")
        dr(self.ax_st, data['stars'], '#aa88ff', "Sterne Anzahl")
        dr(self.ax_sc, data['score'], '#ffcc00', "Smart Score (0-100)", is_score=True) 
        
        self.fig.tight_layout(); self.can.draw()

    def export_csv(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv")
        if f:
            try:
                with open(f, 'w', newline='') as c:
                    w = csv.writer(c, delimiter=';')
                    w.writerow(["Dateiname", "Filter", "Objekt", "Exp", "Score", "FWHM", "Ecc", "Bkg", "Sterne", "SNR"])
                    for r in self.analysis_results: 
                        w.writerow([r['f'], r['fil'], r['obj'], r['exp'], r.get('score', 0), f"{r['fw']:.4f}", f"{r['ec']:.4f}", f"{r['bk']:.2f}", r['st'], f"{r['sn']:.2f}"])
                self.log_box.insert("end", f"CSV gespeichert.\n")
                utils.log.info(f"Metrik-Analyse als CSV exportiert: {f}")
            except Exception as e: 
                utils.log.error(f"Fehler beim Speichern der CSV: {e}")
                messagebox.showerror("Fehler", f"{e}")

    def generate_ai_prompt(self):
        if not self.analysis_results: return
        
        valid_res = [r for r in self.analysis_results if r['st'] > 0]
        if not valid_res: messagebox.showinfo("Info", "Keine gültigen Daten."); return
        
        fwhm_vals = [r['fw'] for r in valid_res]
        ecc_vals = [r['ec'] for r in valid_res]
        snr_vals = [r['sn'] for r in valid_res]
        score_vals = [r.get('score', 0) for r in valid_res]
        
        med_fw = np.median(fwhm_vals); med_ec = np.median(ecc_vals); med_sn = np.median(snr_vals)
        med_sc = np.median(score_vals)
        count = len(self.analysis_results)
        
        try:
            devs = [r.get('dev', 'Unknown') for r in valid_res]
            from collections import Counter
            main_dev = Counter(devs).most_common(1)[0][0]
        except Exception as e: 
            utils.log.debug(f"Konnte häufigstes Teleskop nicht bestimmen: {e}")
            main_dev = "Unbekannt"

        nb_keys = ["LP", "DUO", "DB", "NB", "OIII", "HA", "SII", "H-ALPHA", "UHC"]
        nb_count = sum(1 for r in self.analysis_results if any(k in r['fil'].upper() for k in nb_keys))
        bb_count = count - nb_count
        
        ana_dir = os.path.join(self.folder_path, "_Smart_Analysis")
        try: 
            os.makedirs(ana_dir, exist_ok=True)
        except Exception as e: 
            utils.log.error(f"Konnte Analyse-Ordner nicht erstellen: {e}")
        
        plot_filename = "Smart_Analyse_Graph.png"
        plot_path = os.path.join(ana_dir, plot_filename)
        
        save_success = False
        try:
            self.fig.savefig(plot_path)
            save_success = True
        except Exception as e:
            utils.log.error(f"Fehler beim Speichern der KI-Grafik: {e}")

        prompt = f"""Ich habe {count} Astrofotos analysiert. 
Genutztes Teleskop: {main_dev}

Hier sind die Statistiken:
- Durchschnitt Smart Score: {med_sc:.1f} / 100
- Durchschnitt FWHM: {med_fw:.2f} (Pixel)
- Durchschnitt Exzentrizität: {med_ec:.2f}
- Durchschnitt SNR: {med_sn:.1f}
- Anzahl Broadband (IR/UV): {bb_count}
- Anzahl Narrowband (LP/Dual): {nb_count}

Bitte analysiere diese Werte und hilf mir beim Aussortieren.
1. Ist der FWHM Wert für dieses Teleskop in Ordnung?
2. Deutet die Exzentrizität auf Nachführfehler oder Wind hin?
3. Gibt es Auffälligkeiten beim SNR (ggf. Unterschied BB vs NB)?

Zusätzlich habe ich einen relativen "Smart Score" (0-100) berechnet, der all diese Werte kombiniert.
WICHTIG: Bitte gib mir konkrete Empfehlungen für das Aussortieren:
Reicht es aus, stur nach "Score < ?" auszusortieren, oder sollte ich als Sicherheitsnetz noch harte Cut-Off-Werte für die schlechtesten ~15% definieren für:
- FWHM > ?
- Exzentrizität > ?
- SNR < ?
- Hintergrund (Bkg) > ?
- Sternenanzahl (Stars) < ?

Hier sind 5 zufällige Datenpunkte (CSV Format):
Dateiname;Score;FWHM;Ecc;SNR;Bkg;Stars
"""
        import random
        samples = random.sample(valid_res, min(5, len(valid_res)))
        for s in samples:
            prompt += f"{os.path.basename(s['f'])};{s.get('score',0)};{s['fw']:.2f};{s['ec']:.2f};{s['sn']:.1f};{s['bk']:.0f};{s['st']}\n"
            
        prompt += "\nBitte begründe kurz deine Empfehlung."
        
        self.clipboard_clear()
        self.clipboard_append(prompt)
        
        if save_success:
            try:
                if os.name == 'nt': os.startfile(ana_dir)
                elif sys.platform == 'darwin': subprocess.Popen(['open', ana_dir])
                else: subprocess.Popen(['xdg-open', ana_dir])
            except Exception as e: 
                utils.log.warning(f"Konnte Ordner {ana_dir} nicht öffnen: {e}")
        
        msg = "KI Prompt kopiert!\n(Strg+V im Chat)."
        if save_success:
            msg += f"\n\nOrdner '{os.path.basename(ana_dir)}' geöffnet.\nBitte Grafik '{plot_filename}' in den Chat ziehen."
            
        messagebox.showinfo("Ready for AI", msg)

    def sort_files(self):
        try:
            lims = {
                'fw': float(self.e_fw.get()), 'ec': float(self.e_ec.get()), 'bk': float(self.e_bk.get()), 
                'st': float(self.e_st.get()), 'sn': float(self.e_sn.get()), 
                'sc': float(self.e_sc.get()) 
            }
        except Exception as e: 
            utils.log.warning(f"Zahlenformatfehler bei Grenzwerten: {e}")
            messagebox.showerror("Err", "Zahlenformat!")
            return
        
        tdir = os.path.join(self.folder_path, "_Aussortiert"); os.makedirs(tdir, exist_ok=True)
        cnt=0
        self.log_box.insert("end", f"\n--- Sortiere ---\n")
        
        with open(os.path.join(tdir, "_log.txt"), "a") as l:
            for r in self.filtered_results:
                bad = []
                if self.chk_sc.get() and r.get('score', 100) < lims['sc']: bad.append(f"Score({r.get('score')})")
                if self.chk_fw.get() and r['fw'] > lims['fw']: bad.append("FWHM")
                if self.chk_ec.get() and r['ec'] > lims['ec']: bad.append("Ecc")
                if self.chk_bk.get() and r['bk'] > lims['bk']: bad.append("Bkg")
                if self.chk_st.get() and r['st'] < lims['st']: bad.append("Stars")
                if self.chk_sn.get() and r['sn'] < lims['sn']: bad.append("SNR") 
                
                if bad:
                    try:
                        shutil.move(r['p'], os.path.join(tdir, r['f']))
                        l.write(f"{r['f']} -> {bad}\n"); cnt+=1
                        self.log_box.insert("end", f"Verschoben: {r['f']} -> {bad}\n")
                    except Exception as e: 
                        utils.log.error(f"Fehler beim Verschieben von '{r['f']}': {e}")
                        self.log_box.insert("end", f"Err: {e}\n")
                    
        self.log_box.insert("end", f"--- {cnt} Bilder verschoben ---\n"); self.log_box.see("end")
        self.analysis_results = [r for r in self.analysis_results if not os.path.exists(os.path.join(tdir, r['f']))]
        self.update_plots()