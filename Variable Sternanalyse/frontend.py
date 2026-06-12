import os
import csv
import json
import threading
from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.patches as patches
import matplotlib.patheffects as patheffects
from astropy.io import fits

from backend import AstroBackend

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "vstar_config.json"

class VariableStarApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.backend = AstroBackend()
        self.selection_mode = None 
        self.is_lightcurve_showing = False 
        
        self.show_known_vars = False
        
        self.config = self.load_config()
        
        # --- NEU: Radien an Backend übergeben ---
        self.backend.aperture_r = self.config.get("aperture_r", 6)
        self.backend.annulus_in = self.config.get("annulus_in", 10)
        self.backend.annulus_out = self.config.get("annulus_out", 15)
        # ----------------------------------------
        
        self.title("VStar Analyzer - v2.0")
        self.geometry("1200x900")
        try:
            if os.path.exists("VStar.ico"): self.wm_iconbitmap("VStar.ico")
        except: pass

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main_area()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        # NEU: Standardwerte für Radien ergänzt
        return {"astap_path": r"C:\Program Files\astap\astap.exe", "api_key": "", "solver": "ASTAP", 
                "aperture_r": 6, "annulus_in": 10, "annulus_out": 15}

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_columnconfigure(0, weight=1) 

        self.btn_settings = ctk.CTkButton(self.sidebar_frame, text="⚙ Einstellungen", fg_color="gray30", command=self.open_settings)
        self.btn_settings.grid(row=0, column=0, padx=20, pady=(15, 0), sticky="ew")

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="VStar Analyzer", font=ctk.CTkFont(size=18, weight="bold"))
        self.logo_label.grid(row=1, column=0, padx=20, pady=(10, 10))

        self.btn_load_file = ctk.CTkButton(self.sidebar_frame, text="Einzelne FITS laden", command=self.handle_load_fits)
        self.btn_load_file.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        
        self.btn_load_folder = ctk.CTkButton(self.sidebar_frame, text="Ordner (Serie) laden", command=self.handle_load_folder, fg_color="#2b7b4a", hover_color="#1e5c36")
        self.btn_load_folder.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        self._create_separator(row=4)

        self.lbl_solving = ctk.CTkLabel(self.sidebar_frame, text="Astrometrie", font=ctk.CTkFont(weight="bold"))
        self.lbl_solving.grid(row=5, column=0, padx=20, pady=(5, 5))
        
        self.btn_solve = ctk.CTkButton(self.sidebar_frame, text="Plate-Solve Referenzbild", state="disabled", fg_color="#6b3e9e", hover_color="#532f7a", command=self.handle_solve)
        self.btn_solve.grid(row=6, column=0, padx=20, pady=5, sticky="ew")

        self.btn_find_vars = ctk.CTkButton(self.sidebar_frame, text="🔭 Bekannte Veränderliche anzeigen", state="disabled", fg_color="#008080", hover_color="#006666", command=self.handle_find_variables)
        self.btn_find_vars.grid(row=7, column=0, padx=20, pady=5, sticky="ew")

        self._create_separator(row=8)

        self.lbl_selection = ctk.CTkLabel(self.sidebar_frame, text="Stern-Auswahl", font=ctk.CTkFont(weight="bold"))
        self.lbl_selection.grid(row=9, column=0, padx=20, pady=(5, 5))

        self.btn_target = ctk.CTkButton(self.sidebar_frame, text="1. Zielstern wählen", fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), command=lambda: self.set_selection_mode('target'))
        self.btn_target.grid(row=10, column=0, padx=20, pady=5, sticky="ew")

        self.btn_comp = ctk.CTkButton(self.sidebar_frame, text="2. Vergleichsstern wählen", fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"), command=lambda: self.set_selection_mode('comp'))
        self.btn_comp.grid(row=11, column=0, padx=20, pady=5, sticky="ew")

        self.btn_smart_comp = ctk.CTkButton(self.sidebar_frame, text="⚡ Auto-Vergleichsstern", state="disabled", fg_color="#2c6b96", hover_color="#1a4d70", command=self.handle_smart_comp)
        self.btn_smart_comp.grid(row=12, column=0, padx=20, pady=(5, 5), sticky="ew")

        self._create_separator(row=13)

        # --- NEU: Die Checkbox ---
        self.var_static_tracking = ctk.BooleanVar(value=False)
        self.chk_static = ctk.CTkCheckBox(
            self.sidebar_frame, 
            text="Vor-registriert (Autotracking aus)", 
            variable=self.var_static_tracking,
            text_color="#e67e22" # Kleine farbliche Hervorhebung in Orange
        )
        self.chk_static.grid(row=14, column=0, padx=20, pady=(5, 5), sticky="w")
        # -------------------------

        self.btn_analyze = ctk.CTkButton(self.sidebar_frame, text="Serien-Photometrie starten", state="disabled", command=self.handle_batch_analyze)
        self.btn_analyze.grid(row=15, column=0, padx=20, pady=(10, 5), sticky="ew")

        self.btn_export = ctk.CTkButton(self.sidebar_frame, text="Als CSV speichern", state="disabled", fg_color="gray30", text_color_disabled="gray60", command=self.handle_export_csv)
        self.btn_export.grid(row=16, column=0, padx=20, pady=5, sticky="ew")
        
        self.btn_export_png = ctk.CTkButton(self.sidebar_frame, text="Graph als PNG speichern", state="disabled", fg_color="gray30", text_color_disabled="gray60", command=self.handle_export_png)
        self.btn_export_png.grid(row=17, column=0, padx=20, pady=5, sticky="ew")
        
        self.btn_export_bav = ctk.CTkButton(self.sidebar_frame, text="BAV Export (Format C & Lichtkurve)", state="disabled", fg_color="gray30", text_color_disabled="gray60", command=self.open_bav_export_dialog)
        self.btn_export_bav.grid(row=18, column=0, padx=20, pady=5, sticky="ew")

        self.sidebar_frame.grid_rowconfigure(19, weight=1) 
        self.result_textbox = ctk.CTkTextbox(self.sidebar_frame) 
        self.result_textbox.grid(row=19, column=0, padx=20, pady=10, sticky="nsew")
        self.result_textbox.insert("0.0", "Bereit.\nBitte Bild laden...")

        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="Status: Bereit", text_color="gray")
        self.status_label.grid(row=19, column=0, padx=20, pady=10, sticky="s")

    def _create_separator(self, row):
        sep = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color="gray40")
        sep.grid(row=row, column=0, sticky="ew", padx=20, pady=10)

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=0)
        self.main_frame.grid_columnconfigure(0, weight=1)

        plt.style.use('dark_background')
        self.figure, self.ax = plt.subplots(figsize=(8, 6))
        self.ax.set_title("Kein Bild geladen", color='white')
        self.ax.axis('off')
        self.figure.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.main_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.canvas.mpl_connect('button_press_event', self.on_canvas_click)

        self.toolbar_frame = ctk.CTkFrame(self.main_frame, height=40, corner_radius=0)
        self.toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        self.toolbar.update()

    def open_settings(self):
        if hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return
            
        self.settings_window = ctk.CTkToplevel(self)
        self.settings_window.title("Einstellungen")
        self.settings_window.geometry("600x480") # Leicht vergrößert für den Button
        self.settings_window.transient(self) 
        self.settings_window.grab_set() 

        # --- ASTROMETRIE SETTINGS ---
        ctk.CTkLabel(self.settings_window, text="Bevorzugter Solver:").pack(pady=(20, 5), padx=20, anchor="w")
        solver_var = ctk.StringVar(value=self.config.get("solver", "ASTAP"))
        solver_frame = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        solver_frame.pack(fill="x", padx=20)
        ctk.CTkRadioButton(solver_frame, text="ASTAP (Lokal, Schnell)", variable=solver_var, value="ASTAP").pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(solver_frame, text="Astrometry.net (Online)", variable=solver_var, value="Astrometry.net").pack(side="left")

        ctk.CTkLabel(self.settings_window, text="ASTAP.exe Pfad:").pack(pady=(15, 5), padx=20, anchor="w")
        astap_entry = ctk.CTkEntry(self.settings_window, width=560)
        astap_entry.pack(padx=20)
        astap_entry.insert(0, self.config.get("astap_path", ""))

        ctk.CTkLabel(self.settings_window, text="Astrometry.net API-Key:").pack(pady=(15, 5), padx=20, anchor="w")
        api_entry = ctk.CTkEntry(self.settings_window, width=560, show="*")
        api_entry.pack(padx=20)
        api_entry.insert(0, self.config.get("api_key", ""))
        
        # --- PHOTOMETRIE SETTINGS ---
        ctk.CTkLabel(self.settings_window, text="Photometrie-Radien (Apertur / Annulus In / Annulus Out):").pack(pady=(25, 5), padx=20, anchor="w")
        rad_frame = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        rad_frame.pack(fill="x", padx=20)
        
        ap_entry = ctk.CTkEntry(rad_frame, width=60)
        ap_entry.pack(side="left", padx=(0, 10))
        ap_entry.insert(0, str(self.config.get("aperture_r", 6)))
        
        an_in_entry = ctk.CTkEntry(rad_frame, width=60)
        an_in_entry.pack(side="left", padx=(0, 10))
        an_in_entry.insert(0, str(self.config.get("annulus_in", 10)))
        
        an_out_entry = ctk.CTkEntry(rad_frame, width=60)
        an_out_entry.pack(side="left")
        an_out_entry.insert(0, str(self.config.get("annulus_out", 15)))

        # Hilfsfunktion für den Reset
        def reset_defaults():
            ap_entry.delete(0, "end")
            ap_entry.insert(0, "6")
            an_in_entry.delete(0, "end")
            an_in_entry.insert(0, "10")
            an_out_entry.delete(0, "end")
            an_out_entry.insert(0, "15")
            self.status_label.configure(text="Radien auf Standardwerte zurückgesetzt.", text_color="orange")

        # Der Reset-Button neben den Eingabefeldern
        reset_btn = ctk.CTkButton(rad_frame, text="↺ Standard", width=100, fg_color="#454545", hover_color="#333333", command=reset_defaults)
        reset_btn.pack(side="left", padx=(15, 0))

        def save_and_close():
            self.config["solver"] = solver_var.get()
            self.config["astap_path"] = astap_entry.get()
            self.config["api_key"] = api_entry.get()
            
            try:
                self.config["aperture_r"] = int(ap_entry.get())
                self.config["annulus_in"] = int(an_in_entry.get())
                self.config["annulus_out"] = int(an_out_entry.get())
                
                # Werte ans Backend übergeben
                self.backend.aperture_r = self.config["aperture_r"]
                self.backend.annulus_in = self.config["annulus_in"]
                self.backend.annulus_out = self.config["annulus_out"]
                self.update_plot() 
            except ValueError:
                messagebox.showerror("Fehler", "Bitte nur ganze Zahlen für die Radien eingeben!")
                return
                
            self.save_config()
            self.settings_window.destroy()

        ctk.CTkButton(self.settings_window, text="Speichern", command=save_and_close).pack(pady=30)

    def handle_load_fits(self):
        filepath = filedialog.askopenfilename(title="Wähle eine FITS Datei", filetypes=[("FITS Dateien", "*.fit *.fits")])
        if filepath:
            self.backend.file_list = [filepath]
            self._process_load(self.backend.load_fits_file(filepath))

    def handle_load_folder(self):
        folderpath = filedialog.askdirectory(title="Wähle den Ordner")
        if folderpath:
            self.status_label.configure(text="Suche Dateien...")
            self.update_idletasks()
            self._process_load(self.backend.load_folder(folderpath))

    def _process_load(self, result_tuple):
        success, message = result_tuple
        if success:
            file_count = len(self.backend.file_list)
            wcs_status = "Astrometrie: Aktiv (Header)" if self.backend.wcs and self.backend.wcs.has_celestial else "Astrometrie: Fehlt (Bitte 'Plate-Solve' klicken)"
            
            self.status_label.configure(text=f"Geladen: 1 Referenzbild ({file_count} gesamt)")
            self.result_textbox.delete("0.0", "end")
            self.result_textbox.insert("0.0", f"{file_count} FITS-Dateien in der Warteschlange.\n{wcs_status}\n\nBitte Sterne markieren.")
            self.selection_mode = None
            self._reset_button_colors()
            
            self.btn_solve.configure(state="normal")
            self.btn_find_vars.configure(state="disabled")
            self.btn_analyze.configure(state="disabled")
            self.btn_smart_comp.configure(state="disabled")
            self.btn_export.configure(state="disabled", fg_color="gray30") 
            self.btn_export_png.configure(state="disabled", fg_color="gray30")
            self.btn_export_bav.configure(state="disabled", fg_color="gray30")            
            self.update_plot()
        else:
            self.status_label.configure(text=message, text_color="red")

    def handle_solve(self):
        solver = self.config.get("solver", "ASTAP")
        
        self.btn_solve.configure(
            text="Wird gelöst... (Abbrechen)", 
            fg_color="#c93434", 
            hover_color="#9c2727", 
            command=self.handle_cancel_solve
        )
        self.result_textbox.insert("end", f"\n\nStarte Plate-Solving ({solver})... Bitte warten.\n")
        
        self.is_solving = True
        self.cancel_requested = False 
        self.spinner_index = 0
        self.current_solver_text = f"Löse Bild mit {solver}"
        self._animate_spinner()

        def solve_task():
            astap_path = self.config.get("astap_path", "")
            api_key = self.config.get("api_key", "")
            
            max_attempts = min(5, len(self.backend.file_list))
            if max_attempts == 0:
                self.after(0, self._solve_finished, False, "Keine Bilder geladen.", solver)
                return

            for i in range(max_attempts):
                if self.cancel_requested:
                    return

                if i > 0:
                    filepath = self.backend.file_list[i]
                    self.after(0, lambda idx=i: self.result_textbox.insert("end", f"\nWechsle zu Bild {idx+1} als neues Referenzbild...\n"))
                    self.after(0, self._update_solver_text, f"Löse Bild {i+1} mit {solver}")
                    
                    self.backend.load_fits_file(filepath)
                    self.after(0, self.update_plot) 
                
                success, message = self.backend.run_plate_solve(solver_type=solver, astap_path=astap_path, api_key=api_key)
                
                if self.cancel_requested:
                    return

                if not success and solver == "ASTAP" and api_key:
                    self.after(0, lambda: self.result_textbox.insert("end", f"ASTAP fehlgeschlagen: {message}\nStarte Fallback auf Astrometry.net...\n"))
                    self.after(0, self._update_solver_text, f"Bild {i+1}: Fallback Astrometry.net")
                    
                    success, message = self.backend.run_plate_solve(solver_type="Astrometry.net", astap_path=astap_path, api_key=api_key)
                    solver_used = "Astrometry.net"
                else:
                    solver_used = solver

                if self.cancel_requested:
                    return

                if success:
                    self.after(0, self._solve_finished, True, f"Bild {i+1} erfolgreich gelöst!", solver_used)
                    return
                else:
                    self.after(0, lambda idx=i, err=message: self.result_textbox.insert("end", f"Bild {idx+1} gescheitert: {err}\n"))

            self.after(0, self._solve_finished, False, f"Plate-Solving für die ersten {max_attempts} Bilder fehlgeschlagen. Sind die Bilder in Ordnung?", solver)

        threading.Thread(target=solve_task, daemon=True).start()

    def handle_cancel_solve(self):
        self.cancel_requested = True
        self.result_textbox.insert("end", "\nAbbruch angefordert. Trenne Verbindung...\n")
        self._solve_finished(False, "Vom Benutzer abgebrochen.", "Abbruch")

    def _update_solver_text(self, new_text):
        self.current_solver_text = new_text

    def _animate_spinner(self):
        if self.is_solving and self.status_label.winfo_exists():
            spinner_chars = ['|', '/', '-', '\\']
            char = spinner_chars[self.spinner_index % 4]
            self.status_label.configure(text=f"{self.current_solver_text}... {char}", text_color="orange")
            self.spinner_index += 1
            self.after(150, self._animate_spinner) 

    def _solve_finished(self, success, message, solver_used):
        self.is_solving = False 
        
        self.btn_solve.configure(
            text="Plate-Solve Referenzbild", 
            fg_color="#6b3e9e", 
            hover_color="#532f7a", 
            command=self.handle_solve,
            state="normal"
        )
        
        if self.cancel_requested:
            self.status_label.configure(text="Plate-Solving abgebrochen", text_color="orange")
            self.result_textbox.insert("end", "\n[Abbruch] Der Vorgang wurde erfolgreich gestoppt.\n")
            return

        if success:
            self.status_label.configure(text=f"{solver_used} erfolgreich!", text_color="green")
            self.result_textbox.insert("end", f"[{solver_used}] WCS Matrix erfolgreich erstellt!\nAstrometrie: Aktiv\n\nBitte Sterne markieren.")
            self.btn_find_vars.configure(state="normal")
        else:
            self.status_label.configure(text="Plate-Solving fehlgeschlagen", text_color="red")
            self.result_textbox.insert("end", f"\nFehler beim Plate-Solving: {message}\n")
            messagebox.showerror("Fehler", message)

    def handle_find_variables(self):
        # --- NEU: Toggle-Logik (Ein- und Ausblenden) ---
        if self.show_known_vars:
            self.show_known_vars = False
            self.btn_find_vars.configure(text="🔭 Bekannte Veränderliche anzeigen", fg_color="#008080", hover_color="#006666")
            self.status_label.configure(text="Katalog-Markierungen ausgeblendet.", text_color="white")
            self.update_plot()
            return
        # -----------------------------------------------

        self.status_label.configure(text="Suche alle veränderlichen Sterne im Bildfeld...", text_color="orange")
        self.btn_find_vars.configure(state="disabled")
        self.update_idletasks()

        success, message, variables = self.backend.find_all_variables()

        if success:
            self.show_known_vars = True # <-- Status auf "sichtbar" setzen
            self.btn_find_vars.configure(text="🔭 Bekannte Veränderliche ausblenden", fg_color="#9e3e3e", hover_color="#7a2f2f") # Button wird rötlich
            self.status_label.configure(text=message, text_color="cyan")
            self.result_textbox.insert("end", f"\n\n--- DISCOVERY ---\n{message}")
            self.update_plot() 
        else:
            self.status_label.configure(text="Fehler bei der Suche.", text_color="red")
            self.result_textbox.insert("end", f"\n\n--- DISCOVERY ---\n{message}")

        self.btn_find_vars.configure(state="normal")

    def set_selection_mode(self, mode):
        if self.backend.current_image_data is None: return
        self.selection_mode = mode
        self._reset_button_colors()
        if mode == 'target':
            self.btn_target.configure(fg_color="#1f538d")
            self.status_label.configure(text="Klicke auf den Zielstern...", text_color="white")
        elif mode == 'comp':
            self.btn_comp.configure(fg_color="#1f538d")
            self.status_label.configure(text="Klicke auf den Vergleichsstern...", text_color="white")

    def _reset_button_colors(self):
        self.btn_target.configure(fg_color="transparent")
        self.btn_comp.configure(fg_color="transparent")

    def on_canvas_click(self, event):
        if event.inaxes != self.ax: return
        if self.toolbar.mode != '': return

        x, y = event.xdata, event.ydata

        clicked_var = None
        # --- KORREKTUR: Magnet nur aktiv, wenn Sterne auch eingeblendet sind ---
        if self.show_known_vars and hasattr(self.backend, 'known_variables') and self.backend.known_variables:
            for vx, vy, vname, vtype in self.backend.known_variables:
                if (x - vx)**2 + (y - vy)**2 < 225:
                    clicked_var = (vx, vy, vname, vtype)
                    break
        # ------------------------------------------------------------------------
        
        if clicked_var:
            vx, vy, vname, vtype = clicked_var
            self.backend.target_star_initial = (vx, vy)
            self.backend.target_star_name = vname 
            self.selection_mode = None
            self._reset_button_colors()
            
            self.status_label.configure(text=f"Zielstern '{vname}' ausgewählt.", text_color="green")
            self.result_textbox.insert("end", f"\n\n--- ZIELSTERN (Katalog) ---\nPos: X:{vx:.0f}, Y:{vy:.0f}\nName: {vname} ({vtype})")
            
            if self.backend.wcs and self.backend.wcs.has_celestial:
                self.btn_smart_comp.configure(state="normal")
            
            self.update_plot()
            
            if self.backend.target_star_initial and self.backend.comp_star_initial:
                self.btn_analyze.configure(state="normal")
            return 

        if self.selection_mode is None: return

        if self.selection_mode == 'target':
            self.backend.target_star_initial = (x, y)
            prefix = "ZIEL"
            if self.backend.wcs and self.backend.wcs.has_celestial:
                self.btn_smart_comp.configure(state="normal")
        elif self.selection_mode == 'comp':
            self.backend.comp_star_initial = (x, y)
            prefix = "VERGLEICH"

        self.status_label.configure(text="Frage SIMBAD Datenbank ab...", text_color="orange")
        self.update_idletasks()
        
        coords, simbad_result = self.backend.identify_star(x, y)
        clean_name = simbad_result.split(' (')[0].strip() 
        
        if self.selection_mode == 'target':
            self.backend.target_star_name = clean_name
        elif self.selection_mode == 'comp':
            self.backend.comp_star_name = clean_name
            self.backend.comp_star_mag = "na" 
            
        self.result_textbox.insert("end", f"\n\n--- {prefix}STERN ---\nPos: X:{x:.0f}, Y:{y:.0f}\nRA/DEC: {coords}\nID: {simbad_result}")

        self.selection_mode = None
        self._reset_button_colors()
        self.update_plot()

        if self.backend.target_star_initial and self.backend.comp_star_initial:
            self.btn_analyze.configure(state="normal")
            self.status_label.configure(text="Sterne markiert. Bereit für Photometrie!", text_color="green")
        else:
            self.status_label.configure(text="Stern markiert.", text_color="white")

    def handle_smart_comp(self):
        if not self.backend.target_star_initial: return
        self.status_label.configure(text="Suche perfekten Vergleichsstern in SIMBAD...", text_color="orange")
        self.btn_smart_comp.configure(state="disabled")
        self.update_idletasks()

        tx, ty = self.backend.target_star_initial
        success, coords, message = self.backend.find_smart_comparison_star(tx, ty)

        if success:
            self.backend.comp_star_initial = coords
            self.result_textbox.insert("end", f"\n\n--- AUTO-VERGLEICHSSTERN ---\n{message}")
            self.status_label.configure(text="Perfekter Vergleichsstern gefunden!", text_color="green")
            self.update_plot()
            self.btn_analyze.configure(state="normal")
        else:
            self.status_label.configure(text="Smart-Suche fehlgeschlagen.", text_color="red")
            messagebox.showwarning("Suche fehlgeschlagen", message)
        
        self.btn_smart_comp.configure(state="normal")

    def _live_tracking_preview(self, filepath):
        try:
            with fits.open(filepath) as hdul:
                data = hdul[0].data
            
            self.ax.clear()
            self.toolbar_frame.grid() 
            vmin, vmax = np.percentile(data, 5), np.percentile(data, 99)
            self.ax.imshow(data, cmap='gray_r', origin='lower', vmin=vmin, vmax=vmax)
            self.ax.set_title("Live-Tracking Vorschau...", color='orange')
            self.ax.axis('off')

            if self.backend.target_star_current:
                tx, ty = self.backend.target_star_current
                self.ax.add_patch(patches.Circle((tx, ty), radius=self.backend.aperture_r, edgecolor='red', facecolor='none', lw=2))
            if self.backend.comp_star_current:
                cx, cy = self.backend.comp_star_current
                self.ax.add_patch(patches.Circle((cx, cy), radius=self.backend.aperture_r, edgecolor='green', facecolor='none', lw=2))
            
            self.canvas.draw()
        except Exception: pass 

    def handle_batch_analyze(self):
        # NEU: Übergebe den Zustand der Checkbox an das Backend
        self.backend.use_static_tracking = self.var_static_tracking.get()
        
        self.btn_analyze.configure(state="disabled")
        self.btn_export.configure(state="disabled", fg_color="gray30")
        
        self.backend.target_star_current = self.backend.target_star_initial
        self.backend.comp_star_current = self.backend.comp_star_initial
        
        total_files = len(self.backend.file_list)
        self.result_textbox.insert("end", "\n\nStarte robustes Tracking im Hintergrund...\n")

        def batch_task():
            self.backend.tracking_data.clear() 
            
            for i, filepath in enumerate(self.backend.file_list):
                if i % 5 == 0 or i == total_files - 1:
                    self.after(0, lambda idx=i: self.status_label.configure(text=f"Bearbeite Bild {idx+1} von {total_files}..."))

                self.backend.analyze_single_file(filepath, fallback_index=i)

                if i % 10 == 0 or i == total_files - 1:
                    self.after(0, self._live_tracking_preview, filepath)

            self.after(0, self._open_review_window)

        threading.Thread(target=batch_task, daemon=True).start()

    def _open_review_window(self):
        self.status_label.configure(text="Bitte Tracking im neuen Fenster überprüfen...", text_color="orange")
        self.review_win = ReviewWindow(self, self.backend, self._on_review_complete)

    def _on_review_complete(self):
        self.status_label.configure(text="Berechne Mathematik...", text_color="orange")
        stat_success, stats = self.backend.recalculate_from_tracking_data()
        
        erfolgreich = len(self.backend.results_time_raw)
        total_files = len(self.backend.file_list)
        
        self._finish_batch_analyze(erfolgreich, total_files, stat_success, stats)

    def _finish_batch_analyze(self, erfolgreich, total_files, stat_success, stats):
        tx_start, ty_start = self.backend.target_star_initial
        tx_end, ty_end = self.backend.target_star_current
        drift_px = ((tx_end - tx_start)**2 + (ty_end - ty_start)**2)**0.5

        if stat_success:
            self.result_textbox.insert("end", f"\n\n--- AUSWERTUNG ---\n"
                                              f"Hellster Wert (Max): {stats['max_mag']:.3f} mag\n"
                                              f"Schwächster Wert (Min): {stats['min_mag']:.3f} mag\n"
                                              f"Amplitude: {stats['amplitude']:.3f} mag\n"
                                              f"Dominante Periode: {stats['period']}\n"
                                              f"Tracking-Drift total: {drift_px:.1f} Pixel")
            self.show_results_popup(stats, erfolgreich, total_files, drift_px)
        else:
            self.result_textbox.insert("end", f"\n\nStatistik-Fehler: {stats}")

        self.result_textbox.insert("end", f"\n\nFertig! {erfolgreich}/{total_files} vermessen.")
        self.status_label.configure(text="Analyse komplett!", text_color="green")
        self.btn_analyze.configure(state="normal")
        
        if erfolgreich > 0:
            self.btn_export.configure(state="normal", fg_color="#b08d17", hover_color="#8a6e11") 
            if hasattr(self, 'btn_export_png'):
                self.btn_export_png.configure(state="normal", fg_color="#2b7b4a", hover_color="#1e5c36")
            if hasattr(self, 'btn_export_bav'):
                self.btn_export_bav.configure(state="normal", fg_color="#8e44ad", hover_color="#732d91")
            self.plot_lightcurve()

    def show_results_popup(self, stats, erfolgreich, total_files, drift_px):
        popup = ctk.CTkToplevel(self)
        popup.title("Auswertung Erfolgreich")
        self.update_idletasks() 
        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        main_width = self.winfo_width()
        screen_width = self.winfo_screenwidth()
        popup_width = 350
        popup_x = main_x + main_width + 10
        if popup_x + popup_width > screen_width:
            popup_x = screen_width - popup_width - 20
        popup_y = main_y + 50 
        popup.geometry(f"{popup_width}x400+{popup_x}+{popup_y}")
        popup.attributes("-topmost", True)
        popup.grab_set() 
        
        title = ctk.CTkLabel(popup, text="✨ Photometrie beendet", font=ctk.CTkFont(size=20, weight="bold"), text_color="#2b7b4a")
        title.pack(pady=(20, 15))
        frame = ctk.CTkFrame(popup, fg_color="gray20", corner_radius=10)
        frame.pack(padx=20, fill="both", expand=True)
        ctk.CTkLabel(frame, text=f"Max Helligkeit: {stats['max_mag']:.3f} mag", font=ctk.CTkFont(size=14)).pack(pady=(15, 5))
        ctk.CTkLabel(frame, text=f"Min Helligkeit: {stats['min_mag']:.3f} mag", font=ctk.CTkFont(size=14)).pack(pady=5)
        amp_lbl = ctk.CTkLabel(frame, text=f"Amplitude: {stats['amplitude']:.3f} mag", font=ctk.CTkFont(size=18, weight="bold"), text_color="#e67e22")
        amp_lbl.pack(pady=10)
        ctk.CTkLabel(frame, text=f"Periode: {stats['period']}", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3498db").pack(pady=5)
        ctk.CTkLabel(frame, text=f"Teleskop-Drift: {drift_px:.1f} Pixel", font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(5, 15))
        info = ctk.CTkLabel(popup, text=f"Ausbeute: {erfolgreich} von {total_files} Bildern", font=ctk.CTkFont(size=13))
        info.pack(pady=(15, 10))
        btn = ctk.CTkButton(popup, text="Schließen", command=popup.destroy)
        btn.pack(pady=(0, 20))

    def handle_export_csv(self):
        if not self.backend.plot_times or not self.backend.results_delta_mag: return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Datei", "*.csv")])
        if filepath:
            try:
                with open(filepath, mode='w', newline='') as file:
                    writer = csv.writer(file, delimiter=';')
                    writer.writerow(["Zeit (Minuten)", "Zeit (Raw/JD)", "Delta Magnitude"])
                    for t_plot, t_raw, mag in zip(self.backend.plot_times, self.backend.results_time_raw, self.backend.results_delta_mag):
                        writer.writerow([f"{t_plot:.3f}", f"{t_raw:.6f}", f"{mag:.4f}"])
                self.status_label.configure(text=f"Gespeichert: {os.path.basename(filepath)}", text_color="green")
            except Exception as e: messagebox.showerror("Fehler", str(e))
            
    def handle_export_png(self):
        if not self.backend.results_time_raw: return
        filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Bild", "*.png")])
        if filepath:
            try:
                self.figure.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
                self.status_label.configure(text=f"Gespeichert: {os.path.basename(filepath)}", text_color="green")
            except Exception as e: 
                messagebox.showerror("Fehler", f"Konnte Bild nicht speichern:\n{e}")

    def update_plot(self):
        self.toolbar_frame.grid() 
        if self.is_lightcurve_showing:
            self.is_lightcurve_showing = False
            xlim = None
            ylim = None
        else:
            xlim = self.ax.get_xlim() if self.backend.current_image_data is not None else None
            ylim = self.ax.get_ylim() if self.backend.current_image_data is not None else None

        data = self.backend.current_image_data
        if data is not None:
            self.ax.clear()
            self.figure.patch.set_facecolor('#2b2b2b') 
            self.ax.set_facecolor('black')
            self.ax.set_aspect('equal')
            self.ax.axis('off')
            vmin, vmax = np.percentile(data, 5), np.percentile(data, 99)
            self.ax.imshow(data, cmap='gray_r', origin='lower', vmin=vmin, vmax=vmax)
            self.ax.set_title("Referenzbild (erstes Bild der Serie)", color='white')
            
            # --- KORREKTUR: Nur zeichnen, wenn der Schalter auf 'An' steht ---
            if self.show_known_vars:
                for var_star in self.backend.known_variables:
                    vx, vy, vname, vtype = var_star
                    self.ax.add_patch(patches.Circle((vx, vy), radius=self.backend.aperture_r, edgecolor='#00ffff', facecolor='none', lw=1.5, alpha=0.9))
                    txt = self.ax.text(vx+12, vy+12, vname, color='#00ffff', fontsize=8, weight='bold')
                    txt.set_path_effects([patheffects.withStroke(linewidth=3, foreground='black')])
            # -----------------------------------------------------------------

            if self.backend.target_star_initial:
                x, y = self.backend.target_star_initial
                self.ax.add_patch(patches.Circle((x, y), radius=self.backend.aperture_r, edgecolor='red', facecolor='none', lw=2))
            if self.backend.comp_star_initial:
                x, y = self.backend.comp_star_initial
                self.ax.add_patch(patches.Circle((x, y), radius=self.backend.aperture_r, edgecolor='green', facecolor='none', lw=2))
            
            if xlim != (0.0, 1.0) and ylim != (0.0, 1.0) and xlim is not None:
                self.ax.set_xlim(xlim)
                self.ax.set_ylim(ylim)
            self.canvas.draw()

    def plot_lightcurve(self):
        if not self.backend.results_time_raw: return
        self.is_lightcurve_showing = True 
        self.ax.clear()
        self.ax.set_aspect('auto')
        self.ax.axis('on')
        self.toolbar_frame.grid_remove() 
        self.ax.set_facecolor('white')
        self.figure.patch.set_facecolor('white')
        raw_times = np.array(self.backend.results_time_raw)
        mags = np.array(self.backend.results_delta_mag)
        
        if raw_times[0] > 2400000:
            base_jd = int(raw_times[0])
            self.backend.plot_times = raw_times - base_jd
            xlabel = f"HJD {base_jd} +"
        else:
            self.backend.plot_times = raw_times
            xlabel = "Zeit (Bildnummer)"
        
        x = self.backend.plot_times
        y = mags
        self.ax.plot(x, y, marker='o', markersize=4, linestyle='', color='black', alpha=0.6, label='Messwerte')
        
        if len(x) > 5:
            try:
                p1, p99 = np.percentile(y, 1), np.percentile(y, 99)
                mask = (y >= p1) & (y <= p99)
                z = np.polyfit(x[mask], y[mask], 4)
                p = np.poly1d(z)
                x_trend = np.linspace(min(x), max(x), 100)
                y_trend = p(x_trend)
                self.ax.plot(x_trend, y_trend, "r--", linewidth=1.5, label='Trendlinie (Poly 4)')
            except Exception as e: pass

        self.ax.invert_yaxis()
        if len(y) > 5:
            p1 = np.percentile(y, 1)   
            p99 = np.percentile(y, 99) 
            margin = (p99 - p1) * 0.15 
            self.ax.set_ylim(p99 + margin, p1 - margin)

        self.ax.set_title("Lichtkurve (Instrumentelle Magnitude)", color='black', pad=15, weight='bold')
        self.ax.set_xlabel(xlabel, color='black', weight='bold')
        self.ax.set_ylabel("Δ mag", color='black', weight='bold')
        self.ax.tick_params(colors='black', direction='in')
        for spine in self.ax.spines.values():
            spine.set_edgecolor('black')
            spine.set_linewidth(1)
        self.ax.grid(True, color='gray', linestyle=':', alpha=0.5)
        self.ax.legend(loc="best", facecolor="white", edgecolor="black", labelcolor="black", framealpha=0.9)
        self.figure.tight_layout()
        self.canvas.draw()

    def on_closing(self):
        self.is_solving = False
        self.cancel_requested = True
        plt.close('all')
        self.quit()
        self.destroy()
        import os
        os._exit(0)
        
    def open_bav_export_dialog(self):
        bav_win = ctk.CTkToplevel(self)
        bav_win.title("BAV Export Einstellungen")
        bav_win.geometry("500x700")
        bav_win.attributes("-topmost", True)
        bav_win.grab_set()

        ctk.CTkLabel(bav_win, text="Sternbild (3 Buchstaben, z.B. UMa):").pack(pady=(15, 0), padx=20, anchor="w")
        const_entry = ctk.CTkEntry(bav_win, width=400)
        const_entry.pack(padx=20, pady=(0, 10))
        const_entry.insert(0, "XXX")

        ctk.CTkLabel(bav_win, text="Variabler Stern (Name):").pack(padx=20, anchor="w")
        var_entry = ctk.CTkEntry(bav_win, width=400)
        var_entry.pack(padx=20, pady=(0, 10))
        var_entry.insert(0, self.backend.target_star_name)

        ctk.CTkLabel(bav_win, text="Dein BAV-Beobachterkürzel:").pack(padx=20, anchor="w")
        obs_entry = ctk.CTkEntry(bav_win, width=400)
        obs_entry.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(bav_win, text="Filter (z.B. V, TG, CV, -Ir):").pack(padx=20, anchor="w")
        filter_entry = ctk.CTkEntry(bav_win, width=400)
        filter_entry.pack(padx=20, pady=(0, 10))
        filter_entry.insert(0, "CV")

        ctk.CTkLabel(bav_win, text="Vergleichsstern Name (optional):").pack(padx=20, anchor="w")
        comp_name_entry = ctk.CTkEntry(bav_win, width=400)
        comp_name_entry.pack(padx=20, pady=(0, 10))
        comp_name_entry.insert(0, self.backend.comp_star_name)

        ctk.CTkLabel(bav_win, text="Vergleichsstern Helligkeit in mag (optional):").pack(padx=20, anchor="w")
        comp_mag_entry = ctk.CTkEntry(bav_win, width=400)
        comp_mag_entry.pack(padx=20, pady=(0, 10))
        comp_mag_entry.insert(0, self.backend.comp_star_mag)

        ctk.CTkLabel(bav_win, text="Export-Format Text:").pack(pady=(10, 0), padx=20, anchor="w")
        format_var = ctk.StringVar(value="Format C")
        format_frame = ctk.CTkFrame(bav_win, fg_color="transparent")
        format_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkRadioButton(format_frame, text="Format C", variable=format_var, value="Format C").pack(side="left", padx=(0, 15))
        ctk.CTkRadioButton(format_frame, text="Report-Datei", variable=format_var, value="Report").pack(side="left")

        # Neues Feld für Lichtkurvenblatt und Extremum
        gen_png_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(bav_win, text="Zusätzlich Lichtkurvenblatt (.png) erzeugen", variable=gen_png_var).pack(pady=(15, 5), padx=20, anchor="w")
        
        ext_var = ctk.StringVar(value="min")
        ext_frame = ctk.CTkFrame(bav_win, fg_color="transparent")
        ext_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(ext_frame, text="Markierung im Graph:").pack(side="left", padx=(0,10))
        ctk.CTkRadioButton(ext_frame, text="Minimum", variable=ext_var, value="min").pack(side="left", padx=5)
        ctk.CTkRadioButton(ext_frame, text="Maximum", variable=ext_var, value="max").pack(side="left", padx=5)

        def execute_export():
            v_name = var_entry.get().strip()
            obs = obs_entry.get().strip()
            filt = filter_entry.get().strip()
            c_name = comp_name_entry.get().strip() or "na"
            c_mag = comp_mag_entry.get().strip() or "na"
            const_name = const_entry.get().strip() or "XXX"
            export_type = format_var.get()
            do_png = gen_png_var.get()

            if not obs and (export_type == "Format C" or do_png):
                messagebox.showwarning("Fehlende Daten", "Ein BAV-Kürzel ist zwingend erforderlich!")
                return

            jd_full = self.backend.results_time_raw[0] if self.backend.results_time_raw else 2450000
            jd_short = str(int(jd_full))[2:] 
            
            # Dateinamen-Konvention für Lichtkurvenblatt
            bav_filename_png = f"{const_name}_{v_name.replace(' ', '')}_{jd_short}_{obs}.png"
            heute = datetime.now().strftime("%Y%m%d")

            filepath_txt = filedialog.asksaveasfilename(
                title="Wähle Speicherort für Text-Export",
                defaultextension=".txt", 
                filetypes=[("Text Datei", "*.txt")],
                initialfile=f"{obs}_{heute}_1.txt" if obs else f"BAV_Export_{heute}.txt"
            )
            
            if filepath_txt:
                bav_win.destroy()
                
                # Text-Export
                if export_type == "Format C":
                    success, msg = self.backend.export_bav_format_c(filepath_txt, v_name, obs, filt, c_name, c_mag)
                else:
                    success, msg = self.backend.export_bav_report(filepath_txt, filt)

                if success:
                    export_msg = f"--- BAV EXPORT ---\nDatei erfolgreich gespeichert:\n{filepath_txt}\n"
                    
                    # PNG-Export
                    if do_png:
                        dir_path = os.path.dirname(filepath_txt)
                        filepath_png = os.path.join(dir_path, bav_filename_png)
                        
                        png_success, png_msg = self.backend.export_bav_lightcurve_png(
                            filepath_png, v_name, obs, filt, c_name, c_mag, ext_var.get(), remarks="na"
                        )
                        if png_success:
                            export_msg += f"\nZusätzlich PNG generiert:\n{filepath_png}\n"
                        else:
                            export_msg += f"\nFehler beim PNG Export:\n{png_msg}\n"
                            
                    self.status_label.configure(text=f"BAV Export abgeschlossen", text_color="green")
                    self.result_textbox.insert("end", f"\n\n{export_msg}")
                else:
                    messagebox.showerror("Export Fehler", msg)

        ctk.CTkButton(bav_win, text="Exportieren", command=execute_export, fg_color="#2b7b4a", hover_color="#1e5c36").pack(pady=20)


class ReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, backend, on_complete):
        super().__init__(parent)
        self.backend = backend
        self.on_complete = on_complete
        self.current_idx = 0
        
        self.title("Tracking Review & Korrektur")
        self.geometry("1100x700")
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.grab_set() 
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.sidebar = ctk.CTkFrame(self, width=250)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.sidebar, text="Maus-Werkzeug", font=ctk.CTkFont(weight="bold", size=15)).pack(pady=15)
        self.mode_var = ctk.StringVar(value="Betrachten")
        
        ctk.CTkRadioButton(self.sidebar, text="🔎 Nur Betrachten (Zoom)", variable=self.mode_var, value="Betrachten").pack(pady=8, anchor="w", padx=20)
        ctk.CTkRadioButton(self.sidebar, text="🔴 Zielstern korrigieren", variable=self.mode_var, value="Target").pack(pady=8, anchor="w", padx=20)
        ctk.CTkRadioButton(self.sidebar, text="🟢 Vergleichsstern korrigieren", variable=self.mode_var, value="Comp").pack(pady=8, anchor="w", padx=20)
        
        ctk.CTkLabel(self.sidebar, text="Frame Status", font=ctk.CTkFont(weight="bold", size=15)).pack(pady=(30, 5))
        self.lbl_info = ctk.CTkLabel(self.sidebar, text="", justify="left")
        self.lbl_info.pack(pady=5, padx=10)
        
        ctk.CTkButton(self.sidebar, text="Auswertung abschließen", fg_color="#2b7b4a", hover_color="#1e5c36", command=self.finish).pack(side="bottom", pady=20, padx=20, fill="x")
        
        self.main_area = ctk.CTkFrame(self)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=(0,10), pady=10)
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)
        
        self.figure, self.subplots_ax = plt.subplots(figsize=(8,6))
        self.ax = self.subplots_ax
        self.figure.patch.set_facecolor('#2b2b2b')
        self.ax.set_facecolor('black')
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.main_area)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.canvas.mpl_connect('button_press_event', self.on_click)
        
        self.toolbar_frame = ctk.CTkFrame(self.main_area, height=40)
        self.toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        
        self.slider_frame = ctk.CTkFrame(self.main_area)
        self.slider_frame.grid(row=2, column=0, sticky="ew", pady=5)
        
        self.btn_prev = ctk.CTkButton(self.slider_frame, text="<", width=40, command=lambda: self.set_frame(self.current_idx - 1))
        self.btn_prev.pack(side="left", padx=10)
        
        self.slider = ctk.CTkSlider(self.slider_frame, from_=0, to=len(self.backend.tracking_data)-1, number_of_steps=len(self.backend.tracking_data)-1, command=self.on_slider)
        self.slider.pack(side="left", fill="x", expand=True, padx=10)
        self.slider.set(0)
        
        self.btn_next = ctk.CTkButton(self.slider_frame, text=">", width=40, command=lambda: self.set_frame(self.current_idx + 1))
        self.btn_next.pack(side="left", padx=10)
        
        self.load_frame(0)
        
        self.bind("<Left>", lambda event: self.set_frame(self.current_idx - 1))
        self.bind("<Right>", lambda event: self.set_frame(self.current_idx + 1))

    def on_slider(self, val):
        self.set_frame(int(val))

    def set_frame(self, idx):
        if 0 <= idx < len(self.backend.tracking_data):
            self.current_idx = idx
            self.slider.set(idx)
            self.load_frame(idx)

    def load_frame(self, idx):
        frame = self.backend.tracking_data[idx]
        filepath = frame["filepath"]
        
        try:
            with fits.open(filepath) as hdul:
                data = hdul[0].data
            self.ax.clear()
            vmin, vmax = np.percentile(data, 5), np.percentile(data, 99)
            self.ax.imshow(data, cmap='gray_r', origin='lower', vmin=vmin, vmax=vmax)
            self.ax.set_title(f"Bild {idx+1} / {len(self.backend.tracking_data)}", color='white')
            self.ax.axis('off')
            
            tx, ty = frame["t_pos"]
            cx, cy = frame["c_pos"]
            
            self.ax.add_patch(patches.Circle((tx, ty), radius=self.backend.aperture_r, edgecolor='red', facecolor='none', lw=2))
            self.ax.add_patch(patches.Circle((cx, cy), radius=self.backend.aperture_r, edgecolor='green', facecolor='none', lw=2))
            
            self.canvas.draw()
            
            status_txt = f"Datei:\n{os.path.basename(filepath)}\n\n"
            status_txt += f"Messung gültig: {'Ja' if frame['valid'] else 'Nein (Wolken/Fehler)'}\n"
            status_txt += f"Delta Mag: {frame['delta_mag']:.3f}\n"
            self.lbl_info.configure(text=status_txt)
        except Exception as e:
            self.lbl_info.configure(text=f"Fehler beim Laden:\n{e}")

    def on_click(self, event):
        if event.inaxes != self.ax: return
        if self.toolbar.mode != '': return 
        
        mode = self.mode_var.get()
        if mode == "Betrachten": return
        
        x, y = event.xdata, event.ydata
        
        # --- NEU: Intelligente Serien-Korrektur ---
        if self.backend.use_static_tracking:
            # Wenn wir im statischen Modus sind, korrigieren wir die Master-Koordinaten
            if mode == "Target":
                self.backend.target_star_initial = (x, y)
                self.backend.target_star_current = (x, y)
            elif mode == "Comp":
                self.backend.comp_star_initial = (x, y)
                self.backend.comp_star_current = (x, y)
            
            # Jetzt alle Frames in der Liste mit den neuen Master-Werten neu messen
            for i in range(len(self.backend.tracking_data)):
                frame = self.backend.tracking_data[i]
                self.backend.remeasure_frame(i, self.backend.target_star_initial, self.backend.comp_star_initial)
        else:
            # Klassischer Modus: Nur diesen einen Frame korrigieren
            frame = self.backend.tracking_data[self.current_idx]
            if mode == "Target":
                self.backend.remeasure_frame(self.current_idx, (x, y), frame["c_pos"])
            elif mode == "Comp":
                self.backend.remeasure_frame(self.current_idx, frame["t_pos"], (x, y))
        # ------------------------------------------
            
        self.load_frame(self.current_idx)

    def finish(self):
        self.destroy()
        self.on_complete()