# ==============================================================================
# SMART_GUI.PY - Benutzeroberfläche (V2.5.0)
# ==============================================================================
import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk
import os
import sys
import threading
import shutil
import csv
import re
import webbrowser
import subprocess
from datetime import datetime, timedelta
from tkinter import filedialog, ttk, messagebox
from PIL import Image

# Analysis Imports
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u

import smart_utils as utils
import smart_metric
import module_analyse
import module_calendar
import module_obs_list

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- HELPER: RESSOURCEN PFAD & FOKUS ---
def resource_path(relative_path):
    """ Ermittelt den absoluten Pfad zu Ressourcen, funktioniert für Dev und PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def apply_safe_focus(window, delay=100):
    """ Verhindert Fokus-Crashes bei neu erstellten Fenstern """
    def _focus():
        try:
            if window.winfo_exists():
                window.lift()
                window.focus_force()
        except Exception:
            pass
    window.after(delay, _focus)

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

# --- HILFSKLASSE: LOGGING UI ---
class LogUI:
    def __init__(self, parent, stop_command):
        self.frame = ctk.CTkFrame(parent)
        self.frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.lbl_stat = ctk.CTkLabel(self.frame, text="Bereit.", anchor="w")
        self.lbl_stat.pack(fill="x", padx=10, pady=(5,0))
        self.bar = ctk.CTkProgressBar(self.frame)
        self.bar.pack(fill="x", padx=10, pady=5)
        self.bar.set(0)
        
        self.f_ctrl = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.f_ctrl.pack(fill="x", padx=5, pady=5)
        self.btn_open = ctk.CTkButton(self.f_ctrl, text="Warte...", width=160, state="disabled")
        self.btn_open.pack(side="left", padx=5)
        self.btn_clear = ctk.CTkButton(self.f_ctrl, text="Log leeren", width=100, command=self.clear_log, fg_color="gray")
        self.btn_clear.pack(side="right", padx=5)
        self.btn_stop = ctk.CTkButton(self.f_ctrl, text="STOP", width=80, fg_color="#c0392b", state="disabled", command=stop_command)
        self.btn_stop.pack(side="right", padx=5)

        self.log_box = ctk.CTkTextbox(self.frame, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)

    def clear_log(self):
        self.log_box.configure(state='normal'); self.log_box.delete('1.0', "end"); self.log_box.configure(state='disabled')
    def log(self, text):
        self.log_box.configure(state='normal'); self.log_box.insert("end", ">> " + str(text) + "\n"); self.log_box.see("end"); self.log_box.configure(state='disabled')
        utils.log.info(f"UI-Log: {text}") 
    def set_progress(self, current, total, text):
        if total > 0: self.bar.set(current/total); self.lbl_stat.configure(text=f"{text}: {current}/{total}")
    def reset(self): 
        self.bar.set(0)
        self.lbl_stat.configure(text="Bereit.")
        self.btn_stop.configure(state="disabled")
        self.btn_open.configure(state="disabled", text="Warte...", fg_color="gray")

# --- FENSTER: ABOUT ---
class AboutWindow(ctk.CTkToplevel):
    def __init__(self, parent, version):
        super().__init__(parent)
        self.title("Über SmartSuite")
        self.geometry("450x620") 
        self.resizable(False, False)
        self.current_version = version
        
        apply_safe_focus(self)
        
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(expand=True, fill="both", padx=20, pady=20)

        try:
            img_path = resource_path("smartsuite.png")
            if not os.path.exists(img_path): img_path = resource_path("smartsuite.ico")
            if os.path.exists(img_path):
                img = ctk.CTkImage(light_image=Image.open(img_path), dark_image=Image.open(img_path), size=(180, 180))
                ctk.CTkLabel(self.container, image=img, text="").pack(pady=(10, 20))
            else: raise Exception("No image")
        except Exception as e: 
            utils.log.warning(f"Konnte About-Logo nicht laden: {e}")
            ctk.CTkLabel(self.container, text="🔭", font=("Arial", 60)).pack(pady=20)
        
        ctk.CTkLabel(self.container, text="SmartSuite", font=("Arial", 24, "bold")).pack(pady=(0, 5))
        ctk.CTkLabel(self.container, text=f"Version {self.current_version}", font=("Arial", 16)).pack(pady=(0, 20))
        
        info = "Smart Teleskop\nImport / Archivierung und Analyse\n\nCopyright © 2025-2026 Stefan Raphael\n\nThis program comes with absolute no warranty."
        ctk.CTkLabel(self.container, text=info, justify="center", text_color="gray80").pack(pady=(0, 20))
        
        link_f = ctk.CTkFont(family="Arial", size=12, underline=True)
        lbl_link = ctk.CTkLabel(self.container, text="GNU General License Version 3", text_color="#3b8ed0", font=link_f, cursor="hand2")
        lbl_link.pack(pady=(0, 15))
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open("https://www.gnu.org/licenses/gpl-3.0.html"))

        self.update_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.update_frame.pack(fill="x", pady=10)
        
        self.lbl_update_status = ctk.CTkLabel(self.update_frame, text="", font=("Arial", 12))
        self.lbl_update_status.pack(pady=(0, 5))
        
        self.btn_check_update = ctk.CTkButton(self.update_frame, text="☁  Auf Updates prüfen", fg_color="transparent", border_width=1, text_color="gray90", command=self.check_for_updates)
        self.btn_check_update.pack(pady=5)
        ToolTip(self.btn_check_update, "Sucht online nach einer neuen Version")
        
        self.btn_download = ctk.CTkButton(self.update_frame, text="⬇  Zum Download Ordner", fg_color="green", text_color="white", command=utils.open_update_folder)
        ToolTip(self.btn_download, "Öffnet den Google Drive Ordner")

        ctk.CTkButton(self.container, text="Schließen", width=200, command=self.close_window).pack(side="bottom", pady=10)

    def check_for_updates(self):
        self.lbl_update_status.configure(text="Verbinde...", text_color="yellow")
        self.btn_check_update.configure(state="disabled")
        self.update() 
        
        remote_version = utils.get_remote_version()
        if remote_version:
            clean_remote = remote_version.lower().replace("version", "").replace("v", "").strip()
            clean_local = self.current_version.lower().replace("version", "").replace("v", "").strip()
            
            if clean_remote > clean_local:
                self.lbl_update_status.configure(text=f"Neu: Version {clean_remote} verfügbar!", text_color="green")
                self.btn_check_update.pack_forget() 
                self.btn_download.pack(pady=5) 
            else:
                self.lbl_update_status.configure(text="Du bist auf dem neuesten Stand.", text_color="gray70")
                self.btn_check_update.configure(state="normal")
        else:
            self.lbl_update_status.configure(text="Fehler beim Abruf (Kein Internet?)", text_color="red")
            self.btn_check_update.configure(state="normal")

    def close_window(self):
        self.withdraw()
        self.after(50, self.destroy)

# --- FENSTER: EINSTELLUNGEN ---
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_version):
        super().__init__(parent)
        self.title("Einstellungen"); self.geometry("750x650"); self.version = current_version
        
        apply_safe_focus(self)
        
        c = utils.load_config()
        self.path_siril = tk.StringVar(value=os.path.normpath(c.get("custom_siril_path", utils.find_siril_path())))
        self.path_scripts = tk.StringVar(value=os.path.normpath(c.get("custom_scripts_path", "")))
        
        # --- NEU FÜR ASTROTRACKER ---
        self.path_astap = tk.StringVar(value=os.path.normpath(c.get("astap_path", "")))
        self.path_aladin = tk.StringVar(value=os.path.normpath(c.get("aladin_path", "")))
        self.path_export = tk.StringVar(value=os.path.normpath(c.get("export_path", ""))) # <--- NEU
        
        self.def_lat = tk.StringVar(value=c.get("default_lat", "51.16")) 
        self.def_lon = tk.StringVar(value=c.get("default_lon", "10.45"))
        self.session_gap = tk.StringVar(value=str(c.get("session_gap", "5")))
        
        self.path_siril.trace_add("write", lambda *a: utils.save_config("custom_siril_path", self.path_siril.get()))
        self.path_scripts.trace_add("write", lambda *a: utils.save_config("custom_scripts_path", self.path_scripts.get()))
        self.path_astap.trace_add("write", lambda *a: utils.save_config("astap_path", self.path_astap.get()))
        self.path_aladin.trace_add("write", lambda *a: utils.save_config("aladin_path", self.path_aladin.get()))
        self.path_export.trace_add("write", lambda *a: utils.save_config("export_path", self.path_export.get())) # <--- NEU

        self.def_lat.trace_add("write", lambda *a: utils.save_config("default_lat", self.def_lat.get()))
        self.def_lon.trace_add("write", lambda *a: utils.save_config("default_lon", self.def_lon.get()))

        self.build_ui()

    def build_ui(self):
        ctk.CTkLabel(self, text="Programm Einstellungen", font=("Arial", 18, "bold")).pack(pady=20)
        
        # WICHTIG: Hier wurde "AstroArchive (.exe)" zu "Externe Programme (Ordner)"
        # und der Wert 'False' am Ende wurde zu 'True', damit sich die Ordnerauswahl öffnet!
        configs = [
            ("Siril Pfad:", self.path_siril, False),
            ("Siril Skripte:", self.path_scripts, True),
            ("ASTAP Pfad (.exe):", self.path_astap, False),    
            ("Aladin Pfad (.exe/.jar):", self.path_aladin, False), 
            ("Standard Export-Ordner:", self.path_export, True) 
        ]

        for text, var, is_dir in configs:
            f = ctk.CTkFrame(self); f.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(f, text=text, width=170, anchor="w").pack(side="left", padx=10)
            ctk.CTkEntry(f, textvariable=var).pack(side="left", fill="x", expand=True, padx=5)
            cmd = lambda v=var, d=is_dir: self.select_path(v, d)
            ctk.CTkButton(f, text="...", width=40, command=cmd).pack(side="right", padx=5)

        gf = ctk.CTkFrame(self); gf.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(gf, text="Standard Standort (für Dwarf/Manuell):", font=("Arial", 12, "bold")).pack(pady=5)
        
        sf = ctk.CTkFrame(self)
        sf.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(sf, text="Deep Sky Analyse:", font=("Arial", 12, "bold")).pack(pady=5)
        
        s_row = ctk.CTkFrame(sf, fg_color="transparent")
        s_row.pack(pady=5)
        ctk.CTkLabel(s_row, text="Neue Session beginnen nach Pause von (Minuten):").pack(side="left", padx=5)
        ctk.CTkEntry(s_row, textvariable=self.session_gap, width=60).pack(side="left", padx=5)

        row = ctk.CTkFrame(gf, fg_color="transparent"); row.pack(pady=5)
        ctk.CTkLabel(row, text="Breitengrad (Lat):").pack(side="left", padx=5)
        ctk.CTkEntry(row, textvariable=self.def_lat, width=100).pack(side="left", padx=5)
        ctk.CTkLabel(row, text="Längengrad (Lon):").pack(side="left", padx=5)
        ctk.CTkEntry(row, textvariable=self.def_lon, width=100).pack(side="left", padx=5)
        ctk.CTkLabel(gf, text="Beispiel: Berlin = 52.52 / 13.40 (Dezimal)", text_color="gray", font=("Arial", 10)).pack(pady=2)

        # --- NEU: DATENBANK WARTUNG (ASTROTRACKER) ---
        db_frame = ctk.CTkFrame(self)
        db_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(db_frame, text="Datenbank-Wartung (Astrotracker):", font=("Arial", 12, "bold")).pack(pady=(10, 5), padx=10, anchor="w")
        
        self.btn_update_ast = ctk.CTkButton(db_frame, text="🪨 Helle Asteroiden (Klassiker) neu laden", fg_color="#8e44ad", hover_color="#9b59b6", width=300, command=self.update_asteroids_db)
        self.btn_update_ast.pack(pady=(0, 10), padx=20, anchor="w")
        
        msg = "Hinweis: Änderungen werden automatisch gespeichert."
        ctk.CTkLabel(self, text=msg, text_color="gray", font=("Arial", 11)).pack(pady=10)
        
        btn_f = ctk.CTkFrame(self, fg_color="transparent"); btn_f.pack(pady=10)
        btn_about = ctk.CTkButton(btn_f, text="About / Info & Updates", fg_color="#7f8c8d", command=lambda: AboutWindow(self, self.version))
        btn_about.pack(side="left", padx=10)
        
        ctk.CTkButton(self, text="Schließen", command=self.close_window, fg_color="transparent", border_width=1).pack(pady=10)

    def select_path(self, str_var, is_directory):
        if is_directory:
            p = filedialog.askdirectory(parent=self)
        else:
            p = filedialog.askopenfilename(parent=self, filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        
        apply_safe_focus(self)
        
        if p: 
            str_var.set(os.path.normpath(p))
            if str_var == self.path_tools:
                messagebox.showinfo("Neustart erforderlich", "Pfad gespeichert.\nBitte SmartSuite neu starten!", parent=self)

    def close_window(self):
        self.withdraw()
        self.after(50, self.destroy)
        
    def update_asteroids_db(self):
        self.btn_update_ast.configure(state="disabled", text="⏳ Lade MPC Katalog (ca. 50MB)...")
        
        def worker():
            import requests
            import gzip
            import threading
            
            data_dir = utils.get_data_dir() # <--- Holt den neuen Ordner!
            url = "https://minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz"
            zip_file = os.path.join(data_dir, "MPCORB.DAT.gz")
            txt_file = os.path.join(data_dir, "bright_asteroids.txt")
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            try:
                # 1. Download
                response = requests.get(url, headers=headers, stream=True, timeout=60)
                response.raise_for_status()
                
                with open(zip_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # 2. Entpacken und Filtern
                self.after(0, lambda: self.btn_update_ast.configure(text="⏳ Extrahiere helle Asteroiden..."))

                with gzip.open(zip_file, "rt", encoding="utf-8") as f_in, open(txt_file, "w", encoding="utf-8") as f_out:
                    for i, line in enumerate(f_in):
                        if i < 200: f_out.write(line)
                            
                if os.path.exists(zip_file): os.remove(zip_file)
                    
                self.after(0, lambda: self.btn_update_ast.configure(state="normal", text="🪨 Helle Asteroiden (Klassiker) neu laden"))
                self.after(0, lambda: messagebox.showinfo("Erfolg", f"Datenbank aktualisiert!\n\nDie Datei '{os.path.basename(txt_file)}' ist nun auf dem neuesten Stand."))
                
            except Exception as e:
                self.after(0, lambda: self.btn_update_ast.configure(state="normal", text="🪨 Helle Asteroiden (Klassiker) neu laden"))
                self.after(0, lambda err=str(e): messagebox.showerror("Fehler", f"Download fehlgeschlagen:\n{err}"))

        threading.Thread(target=worker, daemon=True).start()

# --- FENSTER: ORDNER AUSWAHL (MULTI SELECT) ---
class FolderSelectDialog(ctk.CTkToplevel):
    def __init__(self, parent, start_path, callback):
        super().__init__(parent)
        self.title("Ordner auswählen")
        self.geometry("500x600")
        self.callback = callback
        self.result_paths = []
        
        apply_safe_focus(self)

        ctk.CTkLabel(self, text=f"Unterordner wählen in:\n{os.path.basename(start_path)}", font=("Arial", 14, "bold")).pack(pady=10)
        ctk.CTkLabel(self, text=start_path, font=("Arial", 10), text_color="gray").pack(pady=(0, 10))

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(btn_frame, text="Alle auswählen", command=self.select_all, width=100, fg_color="#34495e").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Übernehmen", command=self.confirm, width=100, fg_color="#27ae60").pack(side="right", padx=5)

        self.check_vars = []
        try:
            subfolders = [f.path for f in os.scandir(start_path) if f.is_dir()]
            subfolders.sort()
            
            if not subfolders:
                ctk.CTkLabel(self.scroll, text="Keine Unterordner gefunden!").pack(pady=20)
            
            for path in subfolders:
                folder_name = os.path.basename(path)
                var = tk.BooleanVar(value=False)
                chk = ctk.CTkCheckBox(self.scroll, text=folder_name, variable=var, font=("Consolas", 12))
                chk.pack(anchor="w", pady=2, padx=5)
                self.check_vars.append((path, var, chk))
                
        except Exception as e:
            utils.log.error(f"Fehler beim Lesen der Unterordner in '{start_path}': {e}")
            ctk.CTkLabel(self.scroll, text=f"Fehler beim Lesen:\n{e}").pack()

    def select_all(self):
        all_on = all(v.get() for _, v, _ in self.check_vars)
        for _, v, _ in self.check_vars: v.set(not all_on)

    def confirm(self):
        self.result_paths = [path for path, var, _ in self.check_vars if var.get()]
        self.withdraw()
        if self.result_paths: 
            self.after(50, lambda: self.callback(self.result_paths))
        self.after(100, self.destroy)

# --- FENSTER FÜR MOSAIK ODER BATCH ABFRAGE ---
class SubfolderActionDialog(ctk.CTkToplevel):
    def __init__(self, parent, start_path, callback):
        super().__init__(parent)
        self.title("Ordner-Struktur erkannt")
        self.geometry("450x230")
        self.callback = callback
        
        apply_safe_focus(self)

        ctk.CTkLabel(self, text="Wie sollen die Unterordner verarbeitet werden?", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        ctk.CTkLabel(self, text=f"Ziel: {os.path.basename(start_path)}", text_color="gray").pack(pady=(0, 20))
        
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=20)
        
        btn_batch = ctk.CTkButton(f, text="📂 Einzelne Projekte\n(Batch-Auswahl öffnen)", height=60, command=self.do_batch, fg_color="#2980b9")
        btn_batch.pack(side="left", expand=True, padx=5, fill="x")
        
        btn_mosaic = ctk.CTkButton(f, text="🧩 Mosaik / Panel\n(Alle Dateien zusammenfassen)", height=60, command=self.do_mosaic, fg_color="#8e44ad")
        btn_mosaic.pack(side="right", expand=True, padx=5, fill="x")

    def do_batch(self):
        self.withdraw()
        self.after(50, lambda: self.callback("batch"))
        self.after(100, self.destroy)

    def do_mosaic(self):
        self.withdraw()
        self.after(50, lambda: self.callback("mosaic"))
        self.after(100, self.destroy)

# --- HAUPTANWENDUNG ---
class SmartSuiteApp(ctk.CTk):
    def __init__(self, version_string="2.0.0", start_mode=None, start_path=None): 
        super().__init__()
        self.version = version_string
        self.settings_window = None
        
        self.title(f"SmartSuite v{self.version}")
        self.geometry("1650x900") 
        
        try:
            icon_path = resource_path("smartsuite.ico")
            if os.path.exists(icon_path): self.wm_iconbitmap(icon_path)
        except Exception as e: 
            utils.log.warning(f"Konnte App-Icon nicht setzen: {e}")
        
        # Basis-Variablen bleiben erhalten
        self.src_f = tk.StringVar(); self.dst_f = tk.StringVar()
        self.src_p = tk.StringVar(); self.dst_p = tk.StringVar()
        self.fix_n = tk.BooleanVar()
        
        c = utils.load_config()
        self.src_f.set(c.get("imp_src","")); self.dst_f.set(c.get("imp_dst",""))
        self.src_p.set(c.get("arc_src","")); self.dst_p.set(c.get("arc_dst",""))
        self.fix_n.set(c.get("fix_nina", False))
        # Suchpfad für externe Programme laden
        self.tools_path = c.get("custom_tools_path", c.get("custom_aae_path", ""))
        if os.path.isfile(self.tools_path): self.tools_path = os.path.dirname(self.tools_path)
        
        self.is_running = False; self.stop_req = False

        # =========================================================
        # LAYOUT: SIDEBAR (Links) & HAUPTBEREICH (Rechts)
        # =========================================================
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- 1. SIDEBAR ---
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew") 
        
        # Titel
        ctk.CTkLabel(self.sidebar, text=f"SmartSuite v{self.version}", font=("Arial", 18, "bold")).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # --- INTERNE MODULE ---
        ctk.CTkLabel(self.sidebar, text="Module", text_color="gray").grid(row=1, column=0, sticky="w", padx=20, pady=(10, 5))
        
        btn_imp = ctk.CTkButton(self.sidebar, text="Smart Import", anchor="w", fg_color="transparent", command=lambda: self.switch_view("import"))
        btn_imp.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        btn_arc = ctk.CTkButton(self.sidebar, text="Projekt Archiv", anchor="w", fg_color="transparent", command=lambda: self.switch_view("archive"))
        btn_arc.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
        # --- ANALYSE ---
        ctk.CTkLabel(self.sidebar, text="Analyse", text_color="gray").grid(row=4, column=0, sticky="w", padx=20, pady=(15, 5)) 
        
        btn_ana = ctk.CTkButton(self.sidebar, text="Deep Sky Analyse", anchor="w", fg_color="transparent", command=lambda: self.switch_view("analyse"))
        btn_ana.grid(row=5, column=0, padx=10, pady=5, sticky="ew") 

        # --- PLANUNG ---
        ctk.CTkLabel(self.sidebar, text="Planung", text_color="gray").grid(row=6, column=0, sticky="w", padx=20, pady=(15, 5))
        
        btn_cal = ctk.CTkButton(self.sidebar, text="📅 Astro Kalender", anchor="w", fg_color="transparent", command=lambda: self.switch_view("calendar"))
        btn_cal.grid(row=7, column=0, padx=10, pady=5, sticky="ew")
        
        # --- DER NEUE, INTEGRIERTE ASTROTRACKER ---
        btn_tracker = ctk.CTkButton(self.sidebar, text="☄ Astrotracker", anchor="w", fg_color="transparent", command=lambda: self.switch_view("astrotracker"))
        btn_tracker.grid(row=8, column=0, padx=10, pady=5, sticky="ew")
        
        btn_obs = ctk.CTkButton(self.sidebar, text="📋 Beobachtungsliste", anchor="w", fg_color="transparent", command=lambda: self.switch_view("obslist"))
        btn_obs.grid(row=9, column=0, padx=10, pady=5, sticky="ew")

        
        # --- EXTERNE PROGRAMME ---
        ctk.CTkLabel(self.sidebar, text="Externe Programme", text_color="gray").grid(row=10, column=0, sticky="w", padx=20, pady=(25, 5))
        
        # Astrotracker wurde hier aus der Liste entfernt
        external_tools = [
            ("VStarAnalyzer.exe", "🌟 VStarAnalyzer"),
            ("ShortStacker.exe", "⚡ ShortStacker"),
            ("AstroArchiveExplorer.exe", "🚀 Archive Explorer")
        ]
        
        row_idx = 11
        tools_found = False
        
        for exe_name, btn_label in external_tools:
            # Prüfen, ob das Tool existiert
            if self.get_tool_path(exe_name) is not None:
                tools_found = True
                btn = ctk.CTkButton(self.sidebar, text=btn_label, anchor="w", fg_color="transparent", command=lambda e=exe_name: self.run_local_tool(e))
                btn.grid(row=row_idx, column=0, padx=10, pady=2, sticky="ew")
                row_idx += 1
                
        if not tools_found:
            ctk.CTkLabel(self.sidebar, text="(Keine .exe gefunden)", text_color="gray", font=("Arial", 11)).grid(row=row_idx, column=0, padx=20, pady=2, sticky="w")

        # --- EINSTELLUNGEN (Ganz unten) ---
        # FIX: Die "unsichtbare Feder" auf Zeile 20 setzen, weit weg von den Buttons!
        self.sidebar.grid_rowconfigure(20, weight=1) 

        btn_settings = ctk.CTkButton(self.sidebar, text="⚙ Einstellungen", anchor="w", fg_color="#34495e", command=self.open_settings)
        btn_settings.grid(row=21, column=0, padx=10, pady=(0, 20), sticky="ew")
        ToolTip(btn_settings, "Öffnet die Programm-Einstellungen")

        self.sidebar_buttons = {
            "import": btn_imp, 
            "archive": btn_arc, 
            "analyse": btn_ana,
            "calendar": btn_cal
        }

        # --- 2. HAUPTBEREICH CONTAINER ---
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        # WICHTIG: pady=(60,10) wurde auf pady=10 geändert, da oben jetzt Platz ist!
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # --- 3. FRAMES VORBEREITEN ---
        self.frames = {}
        
        self.frames["import"] = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.build_path_ui(self.frames["import"], "Quelle:", self.src_f, "imp_src")
        self.build_path_ui(self.frames["import"], "Ziel:", self.dst_f, "imp_dst")
        ctk.CTkCheckBox(self.frames["import"], text="N.I.N.A. Header Fix", variable=self.fix_n, command=lambda: utils.save_config("fix_nina", self.fix_n.get())).pack(pady=5)
        ctk.CTkButton(self.frames["import"], text="START", height=40, command=self.do_imp).pack(pady=10)
        self.ui_imp = LogUI(self.frames["import"], self.do_stop)

        self.frames["archive"] = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.build_path_ui(self.frames["archive"], "Quelle:", self.src_p, "arc_src")
        self.build_path_ui(self.frames["archive"], "Ziel:", self.dst_p, "arc_dst")
        f_mode = ctk.CTkFrame(self.frames["archive"], fg_color="transparent"); f_mode.pack(pady=5)
        self.amode = tk.StringVar(value="copy")
        ctk.CTkRadioButton(f_mode, text="Kopieren", variable=self.amode, value="copy").pack(side="left", padx=10)
        ctk.CTkRadioButton(f_mode, text="Verschieben", variable=self.amode, value="move", text_color="#e74c3c").pack(side="left", padx=10)
        ctk.CTkCheckBox(self.frames["archive"], text="N.I.N.A. Header Fix", variable=self.fix_n, command=lambda: utils.save_config("fix_nina", self.fix_n.get())).pack(pady=5)
        ctk.CTkButton(self.frames["archive"], text="START", height=40, command=self.do_arc).pack(pady=10)
        self.ui_arc = LogUI(self.frames["archive"], self.do_stop)

        self.frames["analyse"] = module_analyse.DeepSkyAnalyseFrame(self.main_container)
        
        import module_astrotracker
        
        self.frames["calendar"] = module_calendar.AstroCalendarFrame(self.main_container)
        self.frames["obslist"] = module_obs_list.ObsListFrame(self.main_container) 
        self.frames["astrotracker"] = module_astrotracker.AstroTrackerFrame(self.main_container) # <--- NEU!
        
        self.sidebar_buttons = {
            "import": btn_imp, 
            "archive": btn_arc, 
            "calendar": btn_cal, 
            "obslist": btn_obs,  
            "astrotracker": btn_tracker, # <--- NEU!
            "analyse": btn_ana
        }
        
        # Startansicht laden
        self.switch_view("import")

        if start_mode == "analyze" and start_path and os.path.exists(start_path):
            self.switch_view("analyse")
            self.after(500, lambda: self.frames["analyse"].launch_external_analysis(start_path))
            
        # --- ABFANGEN DES FENSTER-SCHLIESSENS (Handy-Sync Abfrage) ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        # Prüfen ob überhaupt Ziele oder Termine da sind
        has_targets = False
        has_events = False
        if "obslist" in self.frames:
            obs_frame = self.frames["obslist"]
            if hasattr(obs_frame, "last_targets") and obs_frame.last_targets:
                has_targets = True
            if hasattr(obs_frame, "last_events") and obs_frame.last_events:
                has_events = True
                
        # Wenn es Daten gibt, den User fragen, ob er synchronisieren will
        if has_targets or has_events:
            msg_box = messagebox.askyesnocancel(
                "Programm beenden", 
                "Möchtest du vor dem Schließen die Handy-App (Mobile Dashboard) synchronisieren?\n\nJa = Sync & Schließen\nNein = Direkt Schließen\nAbbrechen = Zurück zum Programm",
                icon='question'
            )
            
            if msg_box is True:  # "Ja" geklickt
                if "obslist" in self.frames:
                    # Wir rufen die bereits vorhandene Export-Funktion auf!
                    self.frames["obslist"].export_mobile_app()
                self.destroy()
            elif msg_box is False: # "Nein" geklickt
                self.destroy()
            else: # "Abbrechen" geklickt oder 'X' auf der Dialogbox
                return
        else:
            # Keine Daten in der Liste, einfach still beenden
            self.destroy()
    
    # --- NEUE FUNKTION: Ansicht wechseln ---
    def switch_view(self, view_name):
        # 1. Alle Frames verstecken
        for frame in self.frames.values():
            frame.pack_forget()
            
        # 2. Alle Buttons auf "inaktiv" setzen
        for btn in self.sidebar_buttons.values():
            btn.configure(fg_color="transparent")
            
        # 3. Gewähltes Frame anzeigen und Button hervorheben
        self.frames[view_name].pack(fill="both", expand=True)
        self.sidebar_buttons[view_name].configure(fg_color="#1f538d") # Blau hervorheben
        
        # 4. NEU: Falls das Modul eine Refresh-Funktion hat (wie die Beobachtungsliste), rufe sie auf!
        if hasattr(self.frames[view_name], "refresh_ui"):
            self.frames[view_name].refresh_ui()

    def open_settings(self):
        if self.settings_window is None or not self.settings_window.winfo_exists(): self.settings_window = SettingsWindow(self, self.version)
        else: self.settings_window.focus()
    def build_path_ui(self, p, t, v, k):
        f = ctk.CTkFrame(p); f.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(f, text=t, width=100).pack(side="left", padx=5)
        ctk.CTkEntry(f, textvariable=v).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(f, text="...", width=40, command=lambda: self.sel(v, k)).pack(side="right", padx=5)

    def sel(self, v, k):
        d = filedialog.askdirectory(parent=self)
        if not d: return
        d = os.path.normpath(d)
        
        def set_path_val(path_list):
            final_val = ";".join(path_list)
            v.set(final_val)
            utils.save_config(k, v.get())

        if "dst" in k.lower():
            set_path_val([d])
            return

        is_project_already = False
        try:
            sub_dirs = [f.name.lower() for f in os.scandir(d) if f.is_dir()]
            if any(x in sub_dirs for x in ["lights", "light", "process", "results", "result"]):
                is_project_already = True
            
            if not is_project_already:
                files = [f.name.lower() for f in os.scandir(d) if f.is_file()]
                if any(x.endswith((".fit", ".fits")) for x in files):
                    is_project_already = True
        except Exception as e: 
            utils.log.debug(f"Projekterkennung fehlgeschlagen für '{d}': {e}")

        if is_project_already:
            set_path_val([d])
            return

        try: has_subfolders = any(os.scandir(d))
        except Exception as e: 
            utils.log.debug(f"Fehler bei Prüfung auf Unterordner in '{d}': {e}")
            has_subfolders = False

        if has_subfolders:
            def handle_action(action):
                if action == "batch":
                    FolderSelectDialog(self, d, set_path_val)
                elif action == "mosaic":
                    set_path_val([f"MOSAIC|{d}"])
                
            SubfolderActionDialog(self, d, handle_action)
            return 
        
        set_path_val([d])

    def do_stop(self): self.stop_req = True
    def do_imp(self):
        s, d = self.src_f.get(), self.dst_f.get()
        if s and d: self.start_worker(self.ui_imp, self.w_imp, s, d)
    def do_arc(self):
        s, d = self.src_p.get(), self.dst_p.get()
        if s and d: self.start_worker(self.ui_arc, self.w_arc, s, d)
        
    def start_worker(self, ui, func, *args):
        if not self.is_running:
            self.is_running = True; self.stop_req = False
            ui.reset()
            ui.btn_stop.configure(state="normal")
            threading.Thread(target=func, args=args, daemon=True).start()

    def get_tool_path(self, exe_name):
        """ Sucht nach externen Programmen im selben Ordner wie die SmartSuite """
        # 1. Im Ordner suchen, in dem die SmartSuite liegt
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        p = os.path.join(base_dir, exe_name)
        if os.path.exists(p): return p
        
        # 2. Zum Schluss im aktuellen Arbeitsverzeichnis (Working Dir) suchen
        p = os.path.join(os.getcwd(), exe_name)
        if os.path.exists(p): return p
        
        return None # Nicht gefunden

    def run_local_tool(self, exe_name):
        """ Startet das gefundene Tool """
        exe_path = self.get_tool_path(exe_name)
        
        if exe_path and os.path.exists(exe_path):
            try: 
                # Arbeitsverzeichnis (cwd) auf den Ordner der .exe setzen, damit config.json etc. gefunden werden
                subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            except Exception as e: 
                utils.log.error(f"Konnte {exe_name} nicht starten: {e}")
                messagebox.showerror("Fehler", f"Konnte {exe_name} nicht starten:\n{e}")
        else: 
            messagebox.showerror("Fehler", f"Datei '{exe_name}' nicht gefunden.\n\nBitte in den Einstellungen den korrekten Ordner angeben.")
        
    # --- MULTI-FOLDER IMPORT WORKER ---
    def w_imp(self, s_input, d):
        ui = self.ui_imp
        source_paths = [p.strip() for p in s_input.split(';') if p.strip()]
        total_folders = len(source_paths)
        if total_folders == 0: self.is_running=False; return

        total_copied = 0
        
        for idx, s in enumerate(source_paths):
            if self.stop_req: break
            
            is_mosaic = False
            if s.startswith("MOSAIC|"):
                is_mosaic = True
                s = s.replace("MOSAIC|", "") 
                
            is_sub_folder = s.lower().endswith("_sub")

            raw_files = []
            try:
                if is_mosaic:
                    for r, _, f in os.walk(s):
                        for x in f: raw_files.append(os.path.join(r, x))
                else:
                    for x in os.listdir(s): raw_files.append(os.path.join(s, x))
            except Exception as e:
                utils.log.error(f"Err beim Scannen von '{s}': {e}")
                ui.log(f"Err beim Scannen von '{s}': {e}")
                continue

            fit_candidates = [f for f in raw_files if f.lower().endswith(('.fit', '.fits'))]
            if not fit_candidates: 
                ui.log(f"Überspringe '{os.path.basename(s)}': Keine FITS-Datei für Header-Info gefunden.")
                continue

            t, c, dev = None, None, None
            for cand in fit_candidates:
                t, c, dev = utils.analyze_header(cand)
                if t: break 
            
            if not t:
                ui.log(f"FEHLER: Konnte KEINEN lesbaren Header in '{os.path.basename(s)}' finden.")
                continue

            files_to_copy = []
            is_seestar = "Seestar" in str(dev)
            
            if is_mosaic:
                target_dir = os.path.join(d, c, f"{t}_{dev}", "lights")
                for f in raw_files:
                    fname = os.path.basename(f).lower()
                    if fname.endswith(('.fit', '.fits')) and not fname.startswith(("stack", "failed", ".")):
                        files_to_copy.append(f)
                        
            elif is_seestar and not is_sub_folder:
                target_dir = os.path.join(d, c, f"{t}_{dev}") 
                for f in raw_files:
                    fname = os.path.basename(f).lower()
                    if fname.startswith("."): continue
                    if fname.endswith(('.jpg', '.jpeg')) and "_thn" not in fname:
                        files_to_copy.append(f)
                    elif fname.endswith(('.fit', '.fits')):
                        files_to_copy.append(f)
            else:
                target_dir = os.path.join(d, c, f"{t}_{dev}", "lights") 
                for f in raw_files:
                    fname = os.path.basename(f).lower()
                    if fname.endswith(('.fit', '.fits')) and not fname.startswith(("stack", "failed", ".")):
                        files_to_copy.append(f)

            if not files_to_copy:
                ui.log(f"Überspringe '{os.path.basename(s)}': Nach dem Filtern keine relevanten Dateien übrig.")
                continue

            ui.log(f"--- Import ({idx+1}/{total_folders}) ---")
            ui.log(f"Quelle: {os.path.basename(s)}")
            
            # --- NEU: Detailliertes Reporting für Teleskop & Routinen ---
            ui.log(f"Teleskop erkannt: {dev} (Target: {t})")
            
            if is_mosaic:
                ui.log("Modus: Mosaik-Routing (Zusammenfassung aller Sub-Ordner)")
            elif is_seestar and not is_sub_folder:
                ui.log("Modus: Seestar Hauptordner (Inkl. JPGs und Stacks)")
            else:
                ui.log("Modus: Strenger Astro-Filter (Nur FITS Rohdaten)")
                
            if self.fix_n.get():
                ui.log("Zusatz: N.I.N.A. Header Fix wird auf FITS angewendet")
            # -----------------------------------------------------------
                
            ui.log(f"Ziel: {target_dir}")
            
            os.makedirs(target_dir, exist_ok=True)
            
            cnt = 0
            for i, f in enumerate(files_to_copy):
                if self.stop_req: break
                dest = os.path.join(target_dir, os.path.basename(f))
                try:
                    shutil.copy2(f, dest); cnt += 1; total_copied += 1
                    if self.fix_n.get() and f.lower().endswith(('.fit', '.fits')): 
                        utils.apply_nina_fix(dest)
                    self.after(0, lambda c_=i+1, tot=len(files_to_copy), f_idx=idx+1: ui.set_progress(c_, tot, f"Importiere Ordner {f_idx}/{total_folders}"))
                except Exception as e: 
                    utils.log.exception(f"Kritischer Fehler beim Kopieren von '{f}' nach '{dest}': {e}")
            
            ui.log(f"> {cnt} Dateien gespeichert.")

        self.is_running = False
        final_msg = f"FERTIG: {total_copied} Dateien aus {total_folders} Ordnern importiert."
        final_open_dir = os.path.join(d, c, f"{t}_{dev}") if 't' in locals() else d
        self.after(0, lambda: (ui.log(final_msg), ui.btn_stop.configure(state="disabled"), ui.btn_open.configure(state="normal", text="Letztes Ziel öffnen", command=lambda: os.startfile(final_open_dir) if os.path.exists(final_open_dir) else None)))

    # --- MULTI-FOLDER ARCHIVE WORKER ---
    def w_arc(self, s_input, d):
        ui = self.ui_arc
        source_paths = [p.strip() for p in s_input.split(';') if p.strip()]
        total_folders = len(source_paths)
        total_processed = 0

        for idx, s in enumerate(source_paths):
            if self.stop_req: break
            
            all_files = []
            fits_sample = None
            
            for r, _, f in os.walk(s):
                 for x in f:
                     if x.startswith("."): continue
                     full_p = os.path.join(r, x)
                     all_files.append(full_p)
                     if not fits_sample and x.lower().endswith(('.fit', '.fits')):
                         fits_sample = full_p
            
            if not all_files: ui.log(f"Ordner '{os.path.basename(s)}' ist leer."); continue
            if not fits_sample: ui.log(f"Keine FITS-Datei in '{os.path.basename(s)}' gefunden (Ziel unbekannt)."); continue

            t, c, dev = utils.analyze_header(fits_sample)
            if not t: ui.log(f"Header Fehler in '{os.path.basename(s)}'."); continue

            action = "Verschiebe" if self.amode.get() == "move" else "Kopiere"
            
            ui.log(f"--- Starte Archivierung ({idx+1}/{total_folders}) ---")
            ui.log(f"Quelle: {s}") 
            
            # --- NEU: Detailliertes Reporting auch bei Archivierung ---
            ui.log(f"Teleskop erkannt: {dev} (Target: {t})")
            ui.log(f"Aktion: {action} alle Dateien")
            if self.fix_n.get():
                ui.log("Zusatz: N.I.N.A. Header Fix wird auf FITS angewendet")
            # -----------------------------------------------------------
                
            tdir = os.path.join(d, c, f"{t}_{dev}")
            ui.log(f"Ziel Basis: {tdir}") 
            
            cnt = 0
            
            for i, src in enumerate(all_files):
                if self.stop_req: break
                
                rel_path = os.path.relpath(src, s)
                dest = os.path.join(tdir, rel_path)
                
                try:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if self.amode.get() == "move": shutil.move(src, dest)
                    else: shutil.copy2(src, dest)
                    
                    cnt += 1; total_processed += 1
                    
                    if self.fix_n.get() and src.lower().endswith(('.fit', '.fits')): 
                        utils.apply_nina_fix(dest)
                        
                    self.after(0, lambda c_=i+1, tot=len(all_files), f_idx=idx+1: ui.set_progress(c_, tot, f"Archiviere Ordner {f_idx}/{total_folders}"))
                except Exception as e: 
                    utils.log.exception(f"Kritischer Fehler bei Datei-Operation ({action}) für '{src}': {e}")
            
            ui.log(f"--- Archivierung Fertig ---")
            ui.log(f"Es wurden {cnt} Dateien verarbeitet.\n")

        self.is_running = False
        self.after(0, lambda: (ui.log(f"GESAMT-STATUS: {total_processed} Dateien verarbeitet."), ui.btn_stop.configure(state="disabled")))