# ==============================================================================
# SMART_METRIC.PY - Metrische Analyse & Pro-Diagnose
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
from PIL import Image

# Analysis Imports
from astropy.io import fits
from astropy.visualization import ZScaleInterval
import sep
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from scipy.spatial import KDTree

# Import Logic
import smart_utils as utils

# --- HELPER: KUGELSICHERES ENVIRONMENT FÜR SUBPROZESSE ---
def get_clean_env():
    env = os.environ.copy()
    bad_keys = ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "PYTHONWARNINGS", "PYTHONIOENCODING", "TCL_LIBRARY", "TK_LIBRARY"]
    for k in bad_keys:
        env.pop(k, None)
    orig_path = env.get("PYINSTALLER_ORIG_PATH")
    if orig_path:
        env["PATH"] = orig_path
    else:
        paths = env.get("PATH", "").split(os.pathsep)
        clean_paths = []
        for p in paths:
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


# --- FITS BLINKER (MINI-VIEWER) ---
class FitsBlinkerWindow(ctk.CTkToplevel):
    def __init__(self, parent, start_index):
        super().__init__(parent)
        self.parent_app = parent
        self.current_idx = start_index
        self.load_counter = 0 
        
        self.title("FITS Blinker")
        self.geometry("850x950")
        self.attributes("-topmost", True)
        
        # Navigation
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", pady=(10, 5), padx=20)
        
        self.btn_prev = ctk.CTkButton(nav_frame, text="< Zurück", width=80, fg_color="#34495e", command=self.go_prev)
        self.btn_prev.pack(side="left")
        
        self.lbl_info = ctk.CTkLabel(nav_frame, text="", font=("Arial", 14, "bold"))
        self.lbl_info.pack(side="left", expand=True)
        
        self.btn_next = ctk.CTkButton(nav_frame, text="Vor >", width=80, fg_color="#34495e", command=self.go_next)
        self.btn_next.pack(side="right")
        
        # Bild
        self.img_lbl = ctk.CTkLabel(self, text="Lade FITS...", font=("Arial", 14))
        self.img_lbl.pack(expand=True, fill="both", padx=10, pady=5)
        
        # Warnungen (Wolken / Satelliten)
        self.lbl_warn = ctk.CTkLabel(self, text="", font=("Arial", 14, "bold"), text_color="#e74c3c")
        self.lbl_warn.pack(pady=(0, 5))
        
        # Aktion-Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", pady=5)
        
        btn_keep = ctk.CTkButton(btn_frame, text="✅ Schließen", height=40, fg_color="#27ae60", hover_color="#2ecc71", command=self.destroy)
        btn_keep.pack(side="left", expand=True, padx=(20, 5))
        
        # --- NEU: Ordner öffnen Button ---
        btn_explorer = ctk.CTkButton(btn_frame, text="📂 Im Ordner zeigen", height=40, fg_color="#34495e", hover_color="#2c3e50", command=self.show_in_explorer)
        btn_explorer.pack(side="left", expand=True, padx=5)
        
        btn_trash = ctk.CTkButton(btn_frame, text="🗑️ Bild aussortieren", height=40, fg_color="#c0392b", hover_color="#e74c3c", command=self.exclude_image)
        btn_trash.pack(side="right", expand=True, padx=(5, 20))
        
        # Hotkeys
        self.bind("<Left>", lambda e: self.go_prev())
        self.bind("<Right>", lambda e: self.go_next())
        
        self.load_frame()
        
    def set_index(self, new_index):
        self.current_idx = new_index
        self.load_frame()

    def go_prev(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.load_frame()

    def go_next(self):
        if self.current_idx < len(self.parent_app.filtered_results) - 1:
            self.current_idx += 1
            self.load_frame()

    def load_frame(self):
        if not self.parent_app.filtered_results:
            self.destroy()
            return
            
        if self.current_idx >= len(self.parent_app.filtered_results):
            self.current_idx = len(self.parent_app.filtered_results) - 1
        if self.current_idx < 0:
            self.current_idx = 0

        res = self.parent_app.filtered_results[self.current_idx]
        
        self.parent_app.set_highlight(res['idx'])
        
        self.title(f"FITS Blinker: {res['f']}")
        self.lbl_info.configure(text=f"Frame {self.current_idx+1}/{len(self.parent_app.filtered_results)} | Score: {res['score']} | FWHM: {res['fw']:.2f}")
        
        warn_text = ""
        if res.get('is_cloud'): warn_text += "☁️ Dichte Wolken erkannt! "
        if res.get('has_trail'): warn_text += "🛰️ Flugzeug/Satellit erkannt!"
        self.lbl_warn.configure(text=warn_text)
        
        self.img_lbl.configure(text="Lade Bild...", image="")
        
        self.load_counter += 1
        threading.Thread(target=self._thread_load, args=(res['p'], self.load_counter), daemon=True).start()
        
    def _thread_load(self, path, counter):
        try:
            with fits.open(path) as hdul:
                data = hdul[0].data if hdul[0].data is not None else hdul[1].data
                
            zscale = ZScaleInterval()
            try:
                vmin, vmax = zscale.get_limits(data)
            except:
                vmin, vmax = np.min(data), np.max(data)
                
            data_norm = np.clip((data - vmin) / (vmax - vmin), 0, 1)
            data_8bit = (data_norm * 255).astype(np.uint8)
            img = Image.fromarray(data_8bit)
            
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            
            if self.load_counter == counter:
                self.after(0, lambda: self.img_lbl.configure(image=photo, text=""))
                self.img_lbl.image = photo 
        except Exception as e:
            if self.load_counter == counter:
                self.after(0, lambda: self.img_lbl.configure(text=f"Fehler beim Laden:\n{e}"))

    def show_in_explorer(self):
        if not self.parent_app.filtered_results: return
        res = self.parent_app.filtered_results[self.current_idx]
        file_path = os.path.normpath(res['p'])
        
        if not os.path.exists(file_path):
            messagebox.showerror("Fehler", "Datei nicht gefunden!")
            return
            
        try:
            if os.name == 'nt': # Windows
                subprocess.Popen(f'explorer /select,"{file_path}"')
            elif sys.platform == 'darwin': # macOS
                subprocess.Popen(['open', '-R', file_path])
            else: # Linux
                subprocess.Popen(['xdg-open', os.path.dirname(file_path)])
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Ordner nicht öffnen:\n{e}")

    def exclude_image(self):
        folder_path = self.parent_app.folder_path
        tdir = os.path.join(folder_path, "_Aussortiert")
        os.makedirs(tdir, exist_ok=True)
        
        res = self.parent_app.filtered_results[self.current_idx]
        src = res['p']
        filename = res['f']
        dst = os.path.join(tdir, filename)
        
        try:
            shutil.move(src, dst)
            self.parent_app.log_box.insert("end", f">> Manuell aussortiert (Blinker): {filename}\n")
            self.parent_app.log_box.see("end")
            
            self.parent_app.analysis_results = [r for r in self.parent_app.analysis_results if r['f'] != filename]
            
            self.parent_app.selected_frame_idx = None
            self.parent_app.update_plots()
            
            self.load_frame()
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Bild nicht verschieben:\n{e}")


# --- SIRIL FENSTER ---
class SirilLogWindow(ctk.CTkToplevel):
    def __init__(self, parent, siril_path, work_dir, script_path):
        super().__init__(parent)
        self.title("Siril Prozess Überwachung")
        self.geometry("900x600+100+100")
        self.siril_path = siril_path; self.work_dir = work_dir; self.script_path = script_path
        self.process = None
        if os.path.exists("smartsuite.ico"):
            try: self.wm_iconbitmap("smartsuite.ico")
            except: pass
                
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
            kwargs['env'] = get_clean_env()
            
            self.process = subprocess.Popen(
                cmd, cwd=self.work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                stdin=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', **kwargs
            )
            for line in iter(self.process.stdout.readline, ''): 
                self.after(0, lambda l=line.strip(): (self.log_box.insert("end", l+"\n"), self.log_box.see("end")))
            
            rc = self.process.wait()
            if rc == 0:
                self.after(0, lambda: (self.log_box.insert("end", "\n--- FERTIG ---\n"), self.btn_close.configure(text="Fertig / Schließen", fg_color="#27ae60", command=self.destroy), self.btn_open.configure(state="normal", fg_color="#2980b9")))
            else:
                self.after(0, lambda: (self.log_box.insert("end", f"\n--- FEHLER (Code {rc}) ---\n"), self.btn_close.configure(text="Schließen (Fehler)", fg_color="#e67e22")))
        
        except Exception as e:
            self.after(0, lambda err=str(e): self.log_box.insert("end", f"CRITICAL: {err}\n"))

    def open_dir(self):
        if not os.path.exists(self.work_dir): return
        if os.name == 'nt': os.startfile(self.work_dir)
        elif sys.platform == 'darwin': subprocess.Popen(['open', self.work_dir])
        else: subprocess.Popen(['xdg-open', self.work_dir])

    def close_window(self):
        if self.process and self.process.poll() is None:
            if messagebox.askyesno("?", "Siril läuft noch. Wirklich abbrechen?"):
                try: self.process.kill()
                except: pass
                self.destroy()
        else: self.destroy()


# --- METRIK HAUPTFENSTER ---
class MetricAnalysisWindow(ctk.CTkToplevel):
    def __init__(self, parent, folder_path):
        super().__init__(parent)
        self.title("Metrische Analyse & Smart Scoring")
        self.geometry("1800x1000+50+50")
        self.folder_path = folder_path
        
        self.analysis_results = []
        self.filtered_results = []
        
        # --- UI State Variablen ---
        self.is_running = False
        self.stop_req = False
        self.selected_frame_idx = None  
        self.current_pdata = None       
        self.current_mode = None
        self.blinker_window = None      
        
        if os.path.exists("smartsuite.ico"):
            try: self.wm_iconbitmap("smartsuite.ico")
            except: pass
            
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

        # 2. Graphen (Mitte) - Tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.tab_metrics = self.tabs.add("Standard Metriken")
        self.tab_pro = self.tabs.add("Pro-Analyse (Tilt & Drift)")
        
        plt.style.use('dark_background')
        
        # TAB 1: STANDARD METRIKEN
        self.fig = Figure(figsize=(12, 6), dpi=100)
        self.ax_fw = self.fig.add_subplot(231)
        self.ax_sn = self.fig.add_subplot(232)
        self.ax_ec = self.fig.add_subplot(233)
        self.ax_bk = self.fig.add_subplot(234)
        self.ax_st = self.fig.add_subplot(235) 
        self.ax_sc = self.fig.add_subplot(236) 
        self.fig.subplots_adjust(hspace=0.4, wspace=0.25)
        
        self.can = FigureCanvasTkAgg(self.fig, master=self.tab_metrics)
        self.can.draw()
        self.can.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.can.mpl_connect('button_press_event', self.on_plot_click)

        # TAB 2: PRO ANALYSE (TILT & DRIFT)
        self.fig_pro = Figure(figsize=(12, 6), dpi=100)
        self.ax_drift = self.fig_pro.add_subplot(121)
        self.ax_tilt = self.fig_pro.add_subplot(122)
        self.fig_pro.subplots_adjust(wspace=0.3)
        
        self.can_pro = FigureCanvasTkAgg(self.fig_pro, master=self.tab_pro)
        self.can_pro.draw()
        self.can_pro.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.can_pro.mpl_connect('button_press_event', self.on_drift_plot_click)

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
            
        # --- Mindest-Treffer Schwellenwert ---
        ctk.CTkLabel(self.s_frame, text="Nötige Treffer:", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=(10, 2))
        self.cmb_min_hits = ctk.CTkComboBox(self.s_frame, values=["1", "2", "3", "4", "5", "6"], width=60)
        self.cmb_min_hits.pack(side=tk.LEFT, padx=(0, 10))
        self.cmb_min_hits.set("1")
        ToolTip(self.cmb_min_hits, "Wie viele der aktivierten Filter-Bedingungen müssen pro Bild GERISSEN werden, damit es in den Papierkorb fliegt?")
            
        self.btn_sort = ctk.CTkButton(self.s_frame, text="🧹 Ausführen", width=90, command=self.sort_files, fg_color="#c0392b", state="disabled")
        self.btn_sort.pack(side=tk.LEFT, padx=15)

        # 4. Bottom Frame (CSV & Siril Tools)
        self.bot_frame = ctk.CTkFrame(self, fg_color="#1a1a1a", border_width=1, border_color="#3b8ed0")
        self.bot_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_csv = ctk.CTkButton(self.bot_frame, text="💾 CSV Export", width=120, command=self.export_csv, fg_color="#27ae60", state="disabled")
        self.btn_csv.pack(side=tk.LEFT, padx=15, pady=15)
        
        ctk.CTkFrame(self.bot_frame, width=2, height=60, fg_color="#333333").pack(side=tk.LEFT, padx=15)
        
        siril_container = ctk.CTkFrame(self.bot_frame, fg_color="transparent")
        siril_container.pack(side=tk.LEFT, fill="both", expand=True, padx=10, pady=5)
        
        r1 = ctk.CTkFrame(siril_container, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="🚀 Siril CLI (Hintergrund):", font=("Arial", 11, "bold"), text_color="#3b8ed0", width=160, anchor="w").pack(side=tk.LEFT)
        self.cmb_siril = ctk.CTkComboBox(r1, values=list(self.scripts.keys()), width=300)
        self.cmb_siril.pack(side=tk.LEFT, padx=5)
        l_scr = utils.load_config().get("last_siril_script")
        if l_scr in self.scripts: self.cmb_siril.set(l_scr)
        
        self.btn_siril = ctk.CTkButton(r1, text="Start Skript", command=self.run_siril_gui, fg_color="#8e44ad", width=120)
        self.btn_siril.pack(side=tk.LEFT, padx=10)
        
        r2 = ctk.CTkFrame(siril_container, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="🖥 Siril GUI (Aktiv):", font=("Arial", 11, "bold"), text_color="#2980b9", width=160, anchor="w").pack(side=tk.LEFT)
        
        py_vals = ["(Nur GUI öffnen)"] + list(self.py_scripts.keys())
        def on_py_combo_change(choice):
            if choice == "(Nur GUI öffnen)": self.btn_siril_app.configure(text="GUI Öffnen")
            else: self.btn_siril_app.configure(text="Py-Skript Ausführen")
                
        self.cmb_siril_py = ctk.CTkComboBox(r2, values=py_vals, width=300, command=on_py_combo_change)
        self.cmb_siril_py.pack(side=tk.LEFT, padx=5)
        self.cmb_siril_py.set("(Nur GUI öffnen)")
        
        self.btn_siril_app = ctk.CTkButton(r2, text="GUI Öffnen", command=self.open_siril_app, fg_color="#2980b9", width=140)
        self.btn_siril_app.pack(side=tk.LEFT, padx=10)
        
        if not self.siril_path: 
            self.btn_siril.configure(state="disabled", text="Siril fehlt")
            self.btn_siril_app.configure(state="disabled")

    # --- CROSS-HIGHLIGHT LOGIK ---
    def set_highlight(self, frame_idx):
        self.selected_frame_idx = frame_idx
        if self.current_pdata:
            self.draw_standard_graphs(self.current_pdata, self.current_mode)
            self.draw_pro_graphs()

    def on_plot_click(self, event):
        if event.xdata is None or not self.filtered_results: return
        try:
            target_idx = int(round(event.xdata))
            all_indices = [r['idx'] for r in self.filtered_results]
            closest_local_i = np.argmin(np.abs(np.array(all_indices) - target_idx))
            
            if self.blinker_window is None or not self.blinker_window.winfo_exists():
                self.blinker_window = FitsBlinkerWindow(self, closest_local_i)
            else:
                self.blinker_window.set_index(closest_local_i)
                self.blinker_window.focus()
        except Exception as e:
            utils.log.debug(f"Klick-Event ignoriert: {e}")

    def on_drift_plot_click(self, event):
        if event.xdata is None or event.ydata is None or not self.filtered_results: return
        if event.inaxes != self.ax_drift: return
        try:
            dx_vals = np.array([r['dx'] for r in self.filtered_results])
            dy_vals = np.array([r['dy'] for r in self.filtered_results])
            dists = (dx_vals - event.xdata)**2 + (dy_vals - event.ydata)**2
            closest_local_i = np.argmin(dists)
            
            if self.blinker_window is None or not self.blinker_window.winfo_exists():
                self.blinker_window = FitsBlinkerWindow(self, closest_local_i)
            else:
                self.blinker_window.set_index(closest_local_i)
                self.blinker_window.focus()
        except Exception as e:
            utils.log.debug(f"Klick-Event Drift ignoriert: {e}")

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
        if gui_path.lower().endswith("siril-cli.exe"): gui_path = gui_path[:-13] + "siril.exe"
        elif gui_path.lower().endswith("siril-cli"): gui_path = gui_path[:-9] + "siril"
        work_dir = self.folder_path
        if os.path.basename(work_dir).lower() == "lights": work_dir = os.path.dirname(work_dir)
        selected_py = self.cmb_siril_py.get()
        try:
            clean_env = get_clean_env()
            if selected_py and selected_py != "(Nur GUI öffnen)":
                temp_ssf = os.path.join(work_dir, "_temp_run_py.ssf")
                full_py_path = self.py_scripts.get(selected_py, selected_py).replace('\\', '/')
                with open(temp_ssf, "w", encoding="utf-8") as f:
                    f.write("requires 1.4.0\n")
                    f.write(f"pyscript \"{full_py_path}\"\n")
                SirilLogWindow(self, self.siril_path, work_dir, temp_ssf)
                self.log_box.insert("end", f">> ⏳ Starte '{selected_py}'...\n")
            else:
                subprocess.Popen([gui_path, "-d", work_dir], cwd=work_dir, env=clean_env)
        except Exception as e:
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
            utils.log.error(f"Fehler: {e}")
            files = []
            
        files.sort(); tot=len(files); self.analysis_results=[] 
        
        try: sep.set_extract_pixstack(20000000)
        except: pass
        try: sep.set_sub_object_limit(50000)
        except: pass
        
        prev_coords = None
        cum_dx = 0.0
        cum_dy = 0.0
        recent_st = []  
        
        log_buffer = ""
        
        for i, f in enumerate(files):
            if self.stop_req: 
                self.after(0, lambda: self.log_box.insert("end", "Abbruch durch User.\n")); break
                
            p = os.path.join(self.folder_path, f)
            try:
                with fits.open(p, memmap=False, ignore_missing_end=True) as h: 
                    hdr = h[0].header.copy() 
                    raw_dat = h[0].data if h[0].data is not None else (h[1].data if len(h)>1 else None)
                    
                    if len(h) > 1 and 'OBJECT' not in hdr: 
                        hdr = h[1].header.copy()
                    
                    if raw_dat is not None:
                        dat = raw_dat.copy() 
                    else:
                        dat = None
                
                flt = str(hdr.get('FILTER', 'Unknown')).upper()
                dev = str(hdr.get('TELESCOP', 'Unknown'))
                
                if dat is not None:
                    img_h, img_w = dat.shape
                    step = 2 if max(img_w, img_h) > 2500 else 1
                    
                    # --- DER ANTI-C-CRASH FIX ---
                    # 1. Zwinge die Daten in ein C-lesbares Float32 Array
                    d_sm = dat[::step, ::step].astype(np.float32)
                    d_sm = np.ascontiguousarray(d_sm)
                    d_sm = np.nan_to_num(d_sm)
                    
                    img_min = np.min(d_sm)
                    img_max = np.max(d_sm)
                    
                    if (img_max - img_min) < 1e-4:
                        raise ValueError("Bild hat keinen Kontrast (komplett flach/schwarz)")
                    
                    bkg = sep.Background(d_sm)
                    
                    # 2. Die Notbremse: Das Rauschen MUSS mindestens 0.05% des Bildkontrasts betragen.
                    # Wenn bkg.globalrms nahe 0 ist, würde SEP Millionen Objekte finden und das UI einfrieren!
                    min_allowed_rms = (img_max - img_min) * 0.0005
                    safe_rms = max(bkg.globalrms, min_allowed_rms)
                    
                    sub = d_sm - bkg
                    min_a = max(3, int(7 / (step*0.5))) 
                    
                    # Wir nutzen safe_rms anstatt bkg.globalrms
                    objs = sep.extract(sub, 5.0, err=safe_rms, minarea=min_a)
                    # ----------------------------
                    
                    num = len(objs); fw = ec = sn = vi = 0
                    dx = cum_dx; dy = cum_dy
                    tilt_3x3 = np.full(9, np.nan)
                    has_trail = False
                    is_cloud = False
                    is_noisy = False
                    
                    if num > 5000:
                        is_noisy = True
                        is_cloud = True 
                        num = 0         
                        
                    recent_st.append(num)
                    if len(recent_st) > 15: recent_st.pop(0)
                    if len(recent_st) >= 5:
                        roll_st = np.median(recent_st[:-1])
                        if (roll_st > 30 and num < (roll_st * 0.5)) or is_noisy: 
                            is_cloud = True
                            
                    if num > 0:
                        fw = np.median(2 * np.sqrt(np.log(2) * (objs['a']**2 + objs['b']**2))) * step
                        ec = np.median(np.sqrt(1 - (objs['b'] / objs['a'])**2))
                        sn_vals = objs['peak'] / safe_rms
                        sn = np.median(sn_vals)
                        b_img = bkg.back()
                        b_max = np.max(b_img); b_min = np.min(b_img)
                        if b_max > 0: vi = ((b_max - b_min) / b_max) * 100.0
                        
                        elongation = objs['a'] / np.maximum(objs['b'], 0.5)
                        trail_mask = (elongation > 10.0) & (objs['a'] * step > 100)
                        if np.sum(trail_mask) >= 1:
                            has_trail = True
                        
                        ox = objs['x'] * step
                        oy = objs['y'] * step
                        for sx in range(3):
                            for sy in range(3):
                                mask = (ox >= sx * (img_w/3)) & (ox < (sx+1) * (img_w/3)) & \
                                       (oy >= sy * (img_h/3)) & (oy < (sy+1) * (img_h/3))
                                sector_objs = objs[mask]
                                if len(sector_objs) >= 3: 
                                    fw_sec = np.median(2 * np.sqrt(np.log(2) * (sector_objs['a']**2 + sector_objs['b']**2))) * step
                                    tilt_3x3[sy*3 + sx] = fw_sec
                                    
                        sorted_objs = np.sort(objs, order='flux')[::-1]
                        top_stars = sorted_objs[:40] 
                        current_coords = np.column_stack((top_stars['x'], top_stars['y']))
                        
                        if i == 0 or prev_coords is None:
                            prev_coords = current_coords
                        else:
                            tree = KDTree(prev_coords)
                            dists, indices = tree.query(current_coords)
                            good_matches = dists < (50 / step) 
                            
                            if np.any(good_matches):
                                matched_curr = current_coords[good_matches]
                                matched_prev = prev_coords[indices[good_matches]]
                                dx_arr = (matched_curr[:, 0] - matched_prev[:, 0]) * step
                                dy_arr = (matched_curr[:, 1] - matched_prev[:, 1]) * step
                                
                                frame_dx = np.median(dx_arr)
                                frame_dy = np.median(dy_arr)
                                cum_dx += frame_dx
                                cum_dy += frame_dy
                                
                            prev_coords = current_coords
                            dx = cum_dx
                            dy = cum_dy
                            
                    else: fw=99.9; ec=1.0; sn=0; vi=0
                    
                    res = {
                        "idx": i, "f":f, "p":p, 
                        "fw":fw, "ec":ec, "bk":float(bkg.globalback), "st":num, 
                        "sn":sn, "vi":vi, "score": 0, "dx": dx, "dy": dy, "tilt": tilt_3x3,
                        "obj":hdr.get('OBJECT',''), "exp":hdr.get('EXPTIME',''), 
                        "fil": flt, "dev": dev, "is_cloud": is_cloud, "has_trail": has_trail
                    }
                    self.analysis_results.append(res)
                    
                    icons = ""
                    if has_trail: icons += "🛰️ "
                    if is_cloud: icons += "☁️ "
                    if is_noisy: icons += "💥 "
                    
                    sub_txt = " (Sub)" if step > 1 else ""
                    msg = f"{i+1}: {flt}{sub_txt} {icons}| FWHM:{fw:.1f} | Ecc:{ec:.2f} | SNR:{sn:.1f} | Stars:{num} | Drift X:{dx:.0f} Y:{dy:.0f}"
                    log_buffer += msg + "\n"
                    
                    # Alle 10 Bilder das GUI updaten (hält das Programm flüssig!)
                    if i % 10 == 0 or i == tot - 1:
                        def update_gui(b_txt, curr_i, filename):
                            if not self.stop_req:
                                self.log_box.insert("end", b_txt)
                                self.log_box.see("end")
                                self.prog.set((curr_i + 1) / tot)
                                self.lbl_st.configure(text=f"Analysiere: {filename}")
                        
                        self.after(0, lambda b=log_buffer, c=i, fn=f: update_gui(b, c, fn))
                        log_buffer = ""
                    
                    del dat, d_sm, sub, bkg, objs
                    import gc
                    if i % 20 == 0: gc.collect()
                    
            except Exception as e:
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
                
                base_score = (s_fw * W_FW + s_sn * W_SN + s_bk * W_BK + s_ec * W_EC + s_st * W_ST) * 100
                
                # Harte Strafen für Problembilder (zieht den Graph tief nach unten!)
                if r.get('is_cloud'): base_score = min(base_score, 30.0)
                if r.get('has_trail'): base_score = max(0.0, base_score - 20.0)
                
                r['score'] = round(base_score, 1)
                
        except Exception as e: utils.log.error(f"Score-Berechnung: {e}")

    def finish_scan(self):
        self.is_running=False
        self.btn_run.configure(state="normal"); self.btn_stop.configure(state="disabled"); self.cmb_filter.configure(state="normal")
        self.lbl_st.configure(text="Scan abgeschlossen. (Tipp: Klicke in die Graphen, um das Bild zu öffnen!)")
        if self.analysis_results: 
            self.btn_csv.configure(state="normal"); self.btn_sort.configure(state="normal")
            self.btn_ai.configure(state="normal")
            self.update_plots()

    def update_plots(self, _=None):
        mode = self.cmb_filter.get()
        self.filtered_results = []
        pdata = {"fwhm":[], "ecc":[], "bkg":[], "stars":[], "snr":[], "vig":[], "score":[], "idx":[]}
        nb_keys = ["LP", "DUO", "DB", "NB", "OIII", "HA", "SII", "H-ALPHA"]
        
        for r in self.analysis_results:
            is_narrow = any(k in r['fil'] for k in nb_keys)
            keep = (mode == "Alle") or (mode.startswith("Broadband") and not is_narrow) or (mode.startswith("Narrowband") and is_narrow)
                
            if keep:
                self.filtered_results.append(r)
                if r['st'] > 2: 
                    pdata["fwhm"].append(r['fw']); pdata["ecc"].append(r['ec']); pdata["bkg"].append(r['bk'])
                    pdata["stars"].append(r['st']); pdata["snr"].append(r['sn']); pdata["vig"].append(r['vi'])
                    pdata["score"].append(r.get('score', 0))
                    pdata["idx"].append(r['idx'])
        
        if pdata["fwhm"]:
            try:
                self.e_fw.delete(0,'end'); self.e_fw.insert(0, f"{np.median(pdata['fwhm'])*1.2:.2f}")
                self.e_ec.delete(0,'end'); self.e_ec.insert(0, f"{np.median(pdata['ecc'])*1.2:.2f}")
                self.e_bk.delete(0,'end'); self.e_bk.insert(0, f"{np.median(pdata['bkg'])*1.1:.0f}")
                self.e_st.delete(0,'end'); self.e_st.insert(0, f"{np.median(pdata['stars'])*0.8:.0f}")
                self.e_sn.delete(0,'end'); self.e_sn.insert(0, f"{np.median(pdata['snr'])*0.7:.1f}")
                self.e_sc.delete(0,'end'); self.e_sc.insert(0, "40") 
            except: pass
        
        self.current_pdata = pdata
        self.current_mode = mode
        
        self.draw_standard_graphs(pdata, mode)
        self.draw_pro_graphs()

    def draw_standard_graphs(self, data, suffix):
        def dr(ax, y, c, t, is_score=False):
            ax.clear()
            if not y: return
            lw = 2 if is_score else 1
            ms = 4 if is_score else 3
            
            # Basis-Daten zeichnen
            ax.plot(data['idx'], y, 'o-', color=c, ms=ms, lw=lw, picker=True)
            med = np.median(y); sig = np.std(y)
            ax.axhline(med, c='white', ls='--', label=f"Med: {med:.2f}")
            
            # --- HIGHLIGHT: ROTER PUNKT ---
            if self.selected_frame_idx is not None and self.selected_frame_idx in data['idx']:
                local_i = data['idx'].index(self.selected_frame_idx)
                ax.plot(data['idx'][local_i], y[local_i], 'ro', markersize=7, markeredgecolor='white', zorder=10)
            
            if is_score:
                ax.axhline(60, c='#2ecc71', ls='-', alpha=0.8, label="Keep (>60)")
                ax.axhline(40, c='#e74c3c', ls='-', alpha=0.8, label="Trash (<40)")
                ax.set_facecolor('#1a0505') 
            else:
                ax.axhline(med+2*sig, c=c, ls=':', alpha=0.5)
                ax.axhline(med-2*sig, c=c, ls=':', alpha=0.5)
                ax.plot([], [], c=c, ls=':', label=f"±2σ: {med-2*sig:.1f}/{med+2*sig:.1f}")
                ax.set_facecolor('#000000') 
            
            ax.set_title(t, color='#ffcc00' if is_score else 'white', fontsize=10 if is_score else 9, fontweight='bold')
            ax.legend(facecolor='#333', labelcolor='white', fontsize=6)
            ax.grid(True, alpha=0.2)
            ax.tick_params(colors='white', labelsize=7)
        
        dr(self.ax_fw, data['fwhm'], '#4da6ff', f"FWHM (px) ({suffix})")
        dr(self.ax_sn, data['snr'], '#ff66cc', "SNR")
        dr(self.ax_ec, data['ecc'], '#1abc9c', "Exzentrizität")
        dr(self.ax_bk, data['bkg'], '#00cc66', "Hintergrund")
        dr(self.ax_st, data['stars'], '#aa88ff', "Sterne Anzahl")
        dr(self.ax_sc, data['score'], '#ffcc00', "Smart Score (0-100)", is_score=True) 
        
        self.fig.tight_layout(); self.can.draw()

    def draw_pro_graphs(self):
        self.ax_drift.clear()
        self.ax_tilt.clear()
        
        if not self.filtered_results: return
        
        # --- DRIFT / DITHER SCATTERPLOT ---
        dx_vals = [r['dx'] for r in self.filtered_results]
        dy_vals = [r['dy'] for r in self.filtered_results]
        
        self.ax_drift.plot(dx_vals, dy_vals, 'o-', color='#3498db', alpha=0.5, markersize=3)
        self.ax_drift.plot(dx_vals[0], dy_vals[0], 'go', markersize=8, label="Start (1. Bild)")
        self.ax_drift.plot(dx_vals[-1], dy_vals[-1], 'ro', markersize=8, label="Ende (Letztes Bild)")
        
        # --- HIGHLIGHT: ROTER PUNKT IM DRIFT ---
        if self.selected_frame_idx is not None:
            for r in self.filtered_results:
                if r['idx'] == self.selected_frame_idx:
                    self.ax_drift.plot(r['dx'], r['dy'], 'ro', markersize=10, markeredgecolor='white', zorder=10)
                    break
        
        self.ax_drift.set_title("Dither & Nachführungs-Drift", color='white', fontweight='bold')
        self.ax_drift.set_xlabel("Pixel Drift X", color='gray')
        self.ax_drift.set_ylabel("Pixel Drift Y", color='gray')
        self.ax_drift.axhline(0, color='gray', linestyle='--', alpha=0.5)
        self.ax_drift.axvline(0, color='gray', linestyle='--', alpha=0.5)
        self.ax_drift.grid(True, alpha=0.2)
        self.ax_drift.tick_params(colors='white')
        self.ax_drift.legend(facecolor='#333', labelcolor='white')
        self.ax_drift.set_facecolor('#0a0a0a')
        
        # --- 3x3 TILT INSPECTOR (HEATMAP) ---
        tilt_arrays = [r['tilt'] for r in self.filtered_results if not np.all(np.isnan(r['tilt']))]
        if tilt_arrays:
            avg_tilt = np.nanmedian(np.array(tilt_arrays), axis=0).reshape((3, 3))
            cax = self.ax_tilt.imshow(avg_tilt, cmap='RdYlGn_r', interpolation='nearest', origin='upper')
            self.ax_tilt.set_title("Optischer Tilt & Backfocus (Ø FWHM)", color='white', fontweight='bold')
            self.ax_tilt.set_xticks([])
            self.ax_tilt.set_yticks([])
            
            for i in range(3):
                for j in range(3):
                    val = avg_tilt[i, j]
                    if not np.isnan(val):
                        self.ax_tilt.text(j, i, f"{val:.2f}", ha="center", va="center", color="white", fontweight='bold', fontsize=12)
        else:
            self.ax_tilt.set_title("Optischer Tilt (Zu wenig Sterne für 3x3)", color='gray')
            self.ax_tilt.axis('off')
            
        self.fig_pro.tight_layout(); self.can_pro.draw()

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
            except Exception as e: 
                messagebox.showerror("Fehler", f"{e}")

    def generate_ai_prompt(self):
        if not self.analysis_results: return
        valid_res = [r for r in self.analysis_results if r['st'] > 0]
        if not valid_res: return
        
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
        except: main_dev = "Unbekannt"

        nb_keys = ["LP", "DUO", "DB", "NB", "OIII", "HA", "SII", "H-ALPHA", "UHC"]
        nb_count = sum(1 for r in self.analysis_results if any(k in r['fil'].upper() for k in nb_keys))
        bb_count = count - nb_count
        
        ana_dir = os.path.join(self.folder_path, "_Smart_Analysis")
        try: os.makedirs(ana_dir, exist_ok=True)
        except: pass
        
        try:
            self.fig.savefig(os.path.join(ana_dir, "Smart_Metriken.png"))
            self.fig_pro.savefig(os.path.join(ana_dir, "Smart_Pro_Analyse.png"))
            save_success = True
        except: save_success = False

        prompt = f"""Ich habe {count} Astrofotos analysiert. 
Genutztes Teleskop: {main_dev}

Statistiken:
- Durchschnitt Smart Score: {med_sc:.1f} / 100
- Durchschnitt FWHM: {med_fw:.2f} (Pixel)
- Durchschnitt Exzentrizität: {med_ec:.2f}
- Durchschnitt SNR: {med_sn:.1f}
- Anzahl Broadband: {bb_count} / Narrowband: {nb_count}

Bitte analysiere diese Werte und hilf mir beim Aussortieren.
1. Ist der FWHM Wert in Ordnung?
2. Deutet die Exzentrizität auf Nachführfehler hin?
3. Welche harten Cut-Off-Werte würdest du für FWHM, Exzentrizität, SNR, und Hintergrund (Bkg) ansetzen, um die schlechtesten 15% auszusortieren?

Hier sind 5 zufällige Datenpunkte (CSV):
Dateiname;Score;FWHM;Ecc;SNR;Bkg;Stars
"""
        import random
        samples = random.sample(valid_res, min(5, len(valid_res)))
        for s in samples:
            prompt += f"{os.path.basename(s['f'])};{s.get('score',0)};{s['fw']:.2f};{s['ec']:.2f};{s['sn']:.1f};{s['bk']:.0f};{s['st']}\n"
            
        self.clipboard_clear(); self.clipboard_append(prompt)
        
        if save_success:
            try:
                if os.name == 'nt': os.startfile(ana_dir)
                elif sys.platform == 'darwin': subprocess.Popen(['open', ana_dir])
                else: subprocess.Popen(['xdg-open', ana_dir])
            except: pass
        
        msg = "KI Prompt kopiert!\n(Strg+V im Chat)."
        if save_success: msg += f"\n\nOrdner geöffnet.\nBitte beide Grafiken in den Chat ziehen."
        messagebox.showinfo("Ready for AI", msg)

    def sort_files(self):
        try:
            lims = {
                'fw': float(self.e_fw.get()), 'ec': float(self.e_ec.get()), 'bk': float(self.e_bk.get()), 
                'st': float(self.e_st.get()), 'sn': float(self.e_sn.get()), 
                'sc': float(self.e_sc.get()) 
            }
            min_hits = int(self.cmb_min_hits.get())
        except: 
            messagebox.showerror("Err", "Zahlenformat!"); return
        
        tdir = os.path.join(self.folder_path, "_Aussortiert"); os.makedirs(tdir, exist_ok=True)
        cnt=0
        self.log_box.insert("end", f"\n--- Sortiere (Mind. {min_hits} Treffer nötig) ---\n")
        
        with open(os.path.join(tdir, "_log.txt"), "a") as l:
            for r in self.filtered_results:
                bad = []
                if self.chk_sc.get() and r.get('score', 100) < lims['sc']: bad.append(f"Score({r.get('score')})")
                if self.chk_fw.get() and r['fw'] > lims['fw']: bad.append("FWHM")
                if self.chk_ec.get() and r['ec'] > lims['ec']: bad.append("Ecc")
                if self.chk_bk.get() and r['bk'] > lims['bk']: bad.append("Bkg")
                if self.chk_st.get() and r['st'] < lims['st']: bad.append("Stars")
                if self.chk_sn.get() and r['sn'] < lims['sn']: bad.append("SNR") 
                
                # --- Prüfen, ob die Mindest-Trefferzahl erreicht wurde ---
                if len(bad) >= min_hits:
                    try:
                        shutil.move(r['p'], os.path.join(tdir, r['f']))
                        l.write(f"{r['f']} -> {bad}\n"); cnt+=1
                    except Exception as e: self.log_box.insert("end", f"Err: {e}\n")
                    
        self.log_box.insert("end", f"--- {cnt} Bilder verschoben ---\n"); self.log_box.see("end")
        self.analysis_results = [r for r in self.analysis_results if not os.path.exists(os.path.join(tdir, r['f']))]
        self.selected_frame_idx = None
        self.update_plots()