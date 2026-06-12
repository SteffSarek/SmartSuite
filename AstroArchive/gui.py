import customtkinter as ctk
from tkinter import filedialog, Menu, messagebox
from PIL import Image, ImageTk, UnidentifiedImageError
from gui_popups import ImageViewerWindow, ConstellationSelectionDialog, MissingObjectsWindow, AboutWindow, ReportSelectionDialog, SettingsWindow
import os
from datetime import datetime
import re
import threading 
from version import VERSION
import subprocess 
import webbrowser

# --- WIMS FEATURE IMPORTS ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
# ----------------------------

# --- MODULE IMPORTS ---
from gui_popups import ImageViewerWindow, ConstellationSelectionDialog, MissingObjectsWindow, AboutWindow, ReportSelectionDialog
from gui_catalog import CatalogOverviewWindow 
from gui_map import SkyMapWindow               
from gui_stats import StatsWindow 
from constants import OBJ_TYPE_COLORS 
# ----------------------

class AstroApp(ctk.CTk):
    def __init__(self, logic_controller):
        super().__init__()
        self.logic = logic_controller

        self.title(f"AstroArchive Explorer V{VERSION}") 
        self.geometry("1500x1000") 
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.current_image_obj = None 
        self.current_parent_constellation = None
        self.current_detail_name = None 
        self.current_image_list = []
        self.current_img_index = 0

        # --- Speicher für offene Fenster ---
        self.win_catalog = None        
        self.active_catalog_name = ""  
        self.win_about = None          
        self.win_missing = None        
        self.win_const_select = None
        self.win_map = None 
        self.win_stats = None 
        # -----------------------------------

        # --- Timer & Koordinaten für Live-Update merken ---
        self.live_update_timer = None
        self.current_ra = None
        self.current_dec = None
        # --------------------------------------------------

        self._init_sidebar()
        self._init_main_area()
        
        if self.logic.base_folder:
            self.refresh_library()

        # --- NEU: LIVE-LOG FENSTER (Unten rechts) ---
        self.log_frame = ctk.CTkFrame(self, height=120)
        self.log_frame.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 20))
        self.log_frame.pack_propagate(False) # Hält den Frame auf exakt 120px Höhe
        
        self.log_textbox = ctk.CTkTextbox(self.log_frame, font=ctk.CTkFont(family="Consolas", size=12), text_color="#2ecc71", fg_color="#1e1e1e")
        self.log_textbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_textbox.configure(state="disabled")
        
        self.add_log_message("System bereit. AstroArchive Log gestartet.")
        # --------------------------------------------

    def on_closing(self):
        if messagebox.askyesno("AstroArchive Beenden", "Möchtest du das Programm wirklich beenden?"):
            self.destroy()

    def _init_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="AstroArchive", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # --- HAUPTFUNKTIONEN ---
        self.btn_settings = ctk.CTkButton(self.sidebar, text="📂 Archiv-Ordner", command=self.select_folder)
        self.btn_settings.grid(row=1, column=0, padx=20, pady=10)

        self.btn_scan = ctk.CTkButton(self.sidebar, text="🔄 Index aktualisieren", command=self.refresh_library)
        self.btn_scan.grid(row=2, column=0, padx=20, pady=10)
        
        # --- BEOBACHTUNGSLISTE & WIMS ---
        todo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        todo_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_todo = ctk.CTkButton(todo_frame, text="🔭 Beobachtungsliste", fg_color="#8B008B", hover_color="#6A006A", command=self.open_todo_list)
        self.btn_todo.pack(fill="x", pady=(0, 2))

        self.btn_wims = ctk.CTkButton(todo_frame, text="📥 WIMS Import", fg_color="transparent", border_width=1, text_color="#f39c12", height=24, command=self.open_wims_import)
        self.btn_wims.pack(fill="x")

        # --- STERNKARTE & ATLAS ---
        maps_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        maps_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_map = ctk.CTkButton(maps_frame, text="🗺 Sternkarte", fg_color="#2980b9", hover_color="#3498db", command=self.open_skymap)
        self.btn_map.pack(fill="x", pady=(0, 2))
        
        self.btn_atlas = ctk.CTkButton(maps_frame, text="🌍 Mein Himmelsatlas", fg_color="transparent", border_width=1, text_color="#3498db", command=self.generate_and_open_atlas)
        self.btn_atlas.pack(fill="x")

        # --- EXTRAS ---
        tools_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        tools_frame.grid(row=5, column=0, padx=20, pady=10)
        
        self.btn_stats = ctk.CTkButton(tools_frame, text="📈 Statistik", width=75, fg_color="#27ae60", hover_color="#2ecc71", command=self.open_stats)
        self.btn_stats.grid(row=0, column=0, padx=2, pady=2)

        self.btn_pdf = ctk.CTkButton(tools_frame, text="📄 Report", width=75, fg_color="#7f8c8d", hover_color="#95a5a6", command=self.export_pdf)
        self.btn_pdf.grid(row=0, column=1, padx=2, pady=2)
        
        self.btn_mobile = ctk.CTkButton(tools_frame, text="📱 Handy Sync", width=154, fg_color="#e67e22", hover_color="#d35400", command=self.export_mobile_app)
        self.btn_mobile.grid(row=1, column=0, columnspan=2, padx=2, pady=2)

        self.cat_label = ctk.CTkLabel(self.sidebar, text="Katalog-Übersicht", text_color="gray")
        self.cat_label.grid(row=6, column=0, padx=20, pady=(20, 5))
        
        # --- BUTTONS FÜR KATALOGE ---
        self.btn_all_objects = ctk.CTkButton(self.sidebar, text="📚 Gesamter Katalog", fg_color="transparent", border_width=1, 
                                         command=lambda: self.open_catalog_window("Alle"))
        self.btn_all_objects.grid(row=7, column=0, padx=20, pady=5)
        
        self.btn_all_ngc = ctk.CTkButton(self.sidebar, text="Alle NGC", fg_color="transparent", border_width=1, 
                                         command=lambda: self.open_catalog_window("NGC"))
        self.btn_all_ngc.grid(row=8, column=0, padx=20, pady=5)
        
        self.btn_all_messier = ctk.CTkButton(self.sidebar, text="Alle Messier", fg_color="transparent", border_width=1,
                                             command=lambda: self.open_catalog_window("Messier"))
        self.btn_all_messier.grid(row=9, column=0, padx=20, pady=5)
        
        self.btn_all_caldwell = ctk.CTkButton(self.sidebar, text="Alle Caldwell", fg_color="transparent", border_width=1,
                                              command=lambda: self.open_catalog_window("Caldwell"))
        self.btn_all_caldwell.grid(row=10, column=0, padx=20, pady=5)
        
        self.btn_constellations = ctk.CTkButton(self.sidebar, text="Nach Sternbild", fg_color="transparent", border_width=1,
                                                command=self.open_constellation_selector)
        self.btn_constellations.grid(row=11, column=0, padx=20, pady=5)

        # STATISTIK UNTEN
        self.stats_label = ctk.CTkLabel(self.sidebar, text="Dein Fortschritt", font=ctk.CTkFont(weight="bold"))
        self.stats_label.grid(row=12, column=0, pady=(30, 5))
        
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stats_frame.grid(row=13, column=0, padx=20, sticky="ew")
        
        self.m_stats_lbl = ctk.CTkLabel(self.stats_frame, text="Messier: 0/110", font=ctk.CTkFont(size=11), cursor="hand2")
        self.m_stats_lbl.pack(anchor="w")
        self.m_stats_lbl.bind("<Button-1>", lambda e: self.show_missing_objects("Messier"))
        
        self.m_progress = ctk.CTkProgressBar(self.stats_frame, height=10, cursor="hand2")
        self.m_progress.set(0)
        self.m_progress.pack(fill="x", pady=(0, 10))
        self.m_progress.bind("<Button-1>", lambda e: self.show_missing_objects("Messier"))
        
        self.c_stats_lbl = ctk.CTkLabel(self.stats_frame, text="Caldwell: 0/109", font=ctk.CTkFont(size=11), cursor="hand2")
        self.c_stats_lbl.pack(anchor="w")
        self.c_stats_lbl.bind("<Button-1>", lambda e: self.show_missing_objects("Caldwell"))
        
        self.c_progress = ctk.CTkProgressBar(self.stats_frame, height=10, cursor="hand2")
        self.c_progress.set(0)
        self.c_progress.pack(fill="x")
        self.c_progress.bind("<Button-1>", lambda e: self.show_missing_objects("Caldwell"))

        self.status_label = ctk.CTkLabel(self.sidebar, text="Bereit", text_color="gray", wraplength=180)
        self.status_label.grid(row=14, column=0, padx=20, pady=(20, 10))

        bottom_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom_frame.grid(row=15, column=0, padx=20, pady=(10, 20), sticky="s")
        
        self.btn_app_settings = ctk.CTkButton(bottom_frame, text="⚙ Einstellungen", fg_color="#34495e", hover_color="#2c3e50", command=self.open_app_settings)
        self.btn_app_settings.pack(pady=(0, 10))

        # --- NEU: DATENBANK EDITOR ---
        self.btn_db_editor = ctk.CTkButton(bottom_frame, text="✏️ Datenbank bearbeiten", fg_color="transparent", border_width=1, text_color="#f1c40f", command=self.open_catalog_editor)
        self.btn_db_editor.pack(pady=(0, 10))
        # -----------------------------
        
        self.btn_about = ctk.CTkButton(bottom_frame, text="ℹ  Über AstroArchive", fg_color="transparent", border_width=1, text_color="gray80", command=self.open_about)
        self.btn_about.pack()
        
        self.sidebar.grid_rowconfigure(14, weight=1) 

    def _init_main_area(self):
        self.main_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        self.search_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.search_frame.pack(fill="x", pady=(0, 10))

        self.filter_var = ctk.StringVar(value="Alle")
        self.filter_menu = ctk.CTkOptionMenu(self.search_frame, values=["Alle", "Sternbild", "Messier", "NGC", "Caldwell"], variable=self.filter_var, width=100)
        self.filter_menu.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Suche (z.B. Cygnus, M31, M*, NGC?)")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", self.perform_search)

        self.btn_search = ctk.CTkButton(self.search_frame, text="Go", width=50, command=self.perform_search_btn)
        self.btn_search.pack(side="left", padx=(10, 20))

        self.check_seestar_var = ctk.BooleanVar(value=True)
        self.check_dwarf_var = ctk.BooleanVar(value=True)
        self.check_s30_var = ctk.BooleanVar(value=True)
        
        self.chk_seestar = ctk.CTkCheckBox(self.search_frame, text="Seestar S50", variable=self.check_seestar_var, width=80, onvalue=True, offvalue=False)
        self.chk_seestar.pack(side="left", padx=5)
        self.chk_s30 = ctk.CTkCheckBox(self.search_frame, text="S30 Pro", variable=self.check_s30_var, width=80, onvalue=True, offvalue=False)
        self.chk_s30.pack(side="left", padx=5)
        self.chk_dwarf = ctk.CTkCheckBox(self.search_frame, text="Dwarf 3", variable=self.check_dwarf_var, width=80, onvalue=True, offvalue=False)
        self.chk_dwarf.pack(side="left", padx=5)

        self.list_label = ctk.CTkLabel(self.main_frame, text="Gefundene Objekte / Ordnerinhalt:", anchor="w")
        self.list_label.pack(fill="x", pady=(10, 0))
        
        self.scroll_list = ctk.CTkScrollableFrame(self.main_frame, height=60) 
        self.scroll_list.pack(fill="x", pady=(0, 5))

        self.detail_frame = ctk.CTkFrame(self.main_frame)
        self.detail_frame.pack(fill="both", expand=True, pady=10)

        self.nav_bar = ctk.CTkFrame(self.detail_frame, fg_color="transparent", height=30)
        self.nav_bar.pack(fill="x", pady=(5,0), padx=5)
        self.btn_back = ctk.CTkButton(self.nav_bar, text="⬆ Zum Ordner", width=100, fg_color="gray", command=self.go_back_to_parent)

        self.obj_name_label = ctk.CTkLabel(self.detail_frame, text="---", font=ctk.CTkFont(size=24, weight="bold"), wraplength=1000, justify="center")
        self.obj_name_label.pack(pady=(5, 10), fill="x")

        self.coords_frame = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        self.coords_frame.pack(pady=5)
        self.coords_label = ctk.CTkLabel(self.coords_frame, text="RA: --- | DEC: ---", font=ctk.CTkFont(family="Consolas", size=14))
        self.coords_label.pack(side="left", padx=(0, 10))
        
        self.btn_copy = ctk.CTkButton(self.coords_frame, text="📋", width=30, command=self.copy_coordinates, state="disabled")
        self.btn_copy.pack(side="left", padx=(0, 5))

        self.btn_refresh_coords = ctk.CTkButton(self.coords_frame, text="🔄", width=30, fg_color="#D35400", hover_color="#A04000", command=self.refresh_coordinates, state="disabled")
        self.btn_refresh_coords.pack(side="left")
        
        self.obs_time_label = ctk.CTkLabel(self.coords_frame, text="", text_color="#2ecc71", font=ctk.CTkFont(size=13, weight="bold"))
        self.obs_time_label.pack(side="left", padx=(25, 0))

        # --- NEU: Warnlabel für den Mond ---
        self.moon_warning_label = ctk.CTkLabel(self.coords_frame, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.moon_warning_label.pack(side="left", padx=(20, 0))
        # -----------------------------------

        self.status_indicator = ctk.CTkLabel(self.detail_frame, text="", text_color="gray")
        self.status_indicator.pack(pady=5)

        self.action_frame = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=20, pady=5)
        
        self.path_entry = ctk.CTkEntry(self.action_frame)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.btn_open_folder = ctk.CTkButton(self.action_frame, text="📂", width=40, state="disabled")
        self.btn_open_folder.pack(side="left", padx=2)
        
        self.btn_wiki = ctk.CTkButton(self.action_frame, text="Wiki", width=60, state="disabled", fg_color="#3B8ED0")
        self.btn_wiki.pack(side="left", padx=2)
        
        self.btn_skyview = ctk.CTkButton(self.action_frame, text="SkyView", width=70, state="disabled", fg_color="#2C5F2D")
        self.btn_skyview.pack(side="left", padx=2)
        
        self.btn_aladin = ctk.CTkButton(self.action_frame, text="Aladin", width=70, state="disabled", fg_color="#8B0000") 
        self.btn_aladin.pack(side="left", padx=2)
        # --- NEU: Rechtsklick für lokales Solve ---
        self.btn_aladin.bind("<Button-3>", self.show_aladin_context)

        self.btn_smartsuite = ctk.CTkButton(self.action_frame, text="📊 SmartSuite", width=100, fg_color="#8E44AD", hover_color="#6C3483", state="disabled", command=self.launch_smartsuite)
        self.btn_smartsuite.pack(side="left", padx=10)
        self.btn_smartsuite.bind("<Button-3>", self.show_smartsuite_context)

        self.content_area = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True, padx=20, pady=10)

        # LINKS: Bild Container
        self.image_container = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.image_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.image_label = ctk.CTkLabel(self.image_container, text="")
        self.image_label.pack(expand=True, side="top") 

        self.img_nav_frame = ctk.CTkFrame(self.image_container, fg_color="transparent", height=30)
        
        self.btn_prev_img = ctk.CTkButton(self.img_nav_frame, text="◀", width=40, command=self.show_prev_image)
        self.btn_prev_img.pack(side="left")
        
        self.lbl_img_count = ctk.CTkLabel(self.img_nav_frame, text="0 / 0", font=ctk.CTkFont(size=12))
        self.lbl_img_count.pack(side="left", expand=True)
        
        self.btn_next_img = ctk.CTkButton(self.img_nav_frame, text="▶", width=40, command=self.show_next_image)
        self.btn_next_img.pack(side="right")

        # RECHTS: Notizen & ToDo & TAGS
        self.note_frame = ctk.CTkFrame(self.content_area, width=300, corner_radius=10)
        self.note_frame.pack(side="right", fill="y", padx=(10, 0)) 
        
        # 1. Objekt Typ
        self.type_frame = ctk.CTkFrame(self.note_frame, fg_color="transparent")
        self.type_frame.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(self.type_frame, text="Objekt-Typ:", font=ctk.CTkFont(size=12)).pack(side="left")
        
        self.type_var = ctk.StringVar(value="Auto")
        self.type_menu = ctk.CTkOptionMenu(
            self.type_frame, 
            values=["Auto", "Galaxy", "Nebula", "Cluster", "Comet", "Other"],
            variable=self.type_var,
            width=110,
            command=self.change_object_type
        )
        self.type_menu.pack(side="right")
        
        self.lbl_current_type = ctk.CTkLabel(self.note_frame, text="Erkannt: ---", font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_current_type.pack(fill="x", padx=10, pady=(0, 5))

        # 2. Checkbox
        self.todo_var = ctk.BooleanVar(value=False)
        self.chk_todo = ctk.CTkCheckBox(self.note_frame, text="🔭 Auf Beobachtungsliste", variable=self.todo_var, command=self.toggle_todo_status)
        self.chk_todo.pack(fill="x", padx=10, pady=(5, 10))

        # 3. TAGGING BEREICH
        ctk.CTkLabel(self.note_frame, text="Tags:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(5, 0))
        
        self.tag_input_frame = ctk.CTkFrame(self.note_frame, fg_color="transparent")
        self.tag_input_frame.pack(fill="x", padx=10, pady=(2, 5))
        
        self.tag_entry = ctk.CTkEntry(self.tag_input_frame, placeholder_text="Neuer Tag...", height=28)
        self.tag_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.tag_entry.bind("<Return>", lambda e: self.add_current_tag())
        
        self.btn_add_tag = ctk.CTkButton(self.tag_input_frame, text="+", width=30, height=28, command=self.add_current_tag)
        self.btn_add_tag.pack(side="right")
        
        self.tags_scroll = ctk.CTkScrollableFrame(self.note_frame, height=120, fg_color="#2b2b2b") 
        self.tags_scroll.pack(fill="x", padx=10, pady=(0, 10))
        self.tags_scroll.grid_columnconfigure(0, weight=1)
        self.tags_scroll.grid_columnconfigure(1, weight=1)

        # 4. NOTIZEN
        self.lbl_notes = ctk.CTkLabel(self.note_frame, text="Notizen:", anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_notes.pack(fill="x", padx=10, pady=(5, 2))
        
        self.notes_textbox = ctk.CTkTextbox(self.note_frame, wrap="word", height=150)
        self.notes_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.btn_save_note = ctk.CTkButton(self.note_frame, text="💾 Speichern", command=self.save_current_note, state="disabled")
        self.btn_save_note.pack(fill="x", padx=10, pady=(5, 10))

        # --- NEU: Plot Container ganz unten in der Detailansicht ---
        self.plot_container = ctk.CTkFrame(self.detail_frame, height=180, fg_color="transparent")
        self.plot_container.pack(fill="x", padx=20, pady=(10, 20))

        self.fig = Figure(figsize=(8, 1.8), dpi=100, facecolor='#2b2b2b')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#2b2b2b')
        for spine in self.ax.spines.values(): spine.set_color('gray')

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_container)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # -----------------------------------------------------------

    def add_log_message(self, message):
        """Schreibt eine Nachricht mit Zeitstempel in das Log-Fenster."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", log_entry)
        self.log_textbox.see("end") 
        self.log_textbox.configure(state="disabled")
        self.update_idletasks()

    def open_stats(self):
        if self.win_stats is not None and self.win_stats.winfo_exists():
            self.win_stats.lift()
            self.win_stats.focus()
            return
        self.win_stats = StatsWindow(self, self.logic)

    # --- ALADIN LOKAL WORKFLOW (Hauptfenster) ---
    def show_aladin_context(self, event):
        if not self.current_detail_name or self.btn_aladin.cget("state") == "disabled": return
        menu = Menu(self, tearoff=0)
        menu.add_command(label="🚀 Bild lokal solven (ASTAP -> Aladin Desktop)", command=self.run_local_aladin_workflow)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()
        
    def run_local_aladin_workflow(self):
        start_dir = self.path_entry.get() if self.path_entry.get() else self.logic.base_folder
        
        # --- FIX: Erlaube JPG und PNG im Dateidialog ---
        file_path = filedialog.askopenfilename(initialdir=start_dir, title="Bild auswählen", filetypes=[("Bilder", "*.fits *.fit *.fts *.jpg *.jpeg *.png"), ("Alle Dateien", "*.*")])
        if not file_path: return
        
        def status_cb(msg, is_ok):
            # Nutzt die direkte Funktionsübergabe ohne lambda (100% sicher bei Threads!)
            color = "green" if is_ok else "red"
            self.after(0, self.status_indicator.configure, {"text": msg, "text_color": color})
            self.after(0, self.add_log_message, msg)
            
        self.status_indicator.configure(text="ASTAP läuft...", text_color="yellow")
        self.add_log_message(f"Starte Workflow für: {os.path.basename(file_path)}")
        self.update()
        self.logic.run_local_solve_and_aladin(file_path, self.coords_label.cget("text"), status_cb)
    
    def export_pdf(self):
        const_list = self.logic.get_available_constellations()
        ReportSelectionDialog(self, const_list, self._perform_export_callback)
        
    def _perform_export_callback(self, mode, value, is_gallery=False, date_start=None, date_end=None):
        default_name = f"AstroReport_{mode}.html"
        if is_gallery:
            default_name = f"AstroGallery_{mode}.html"
        if mode == "Sternbild" and value:
            clean_val = re.sub(r'\W+', '', value) 
            default_name = f"AstroReport_{clean_val}.html"
            
        default_dir = self.logic.get_export_path()
        if not default_dir or not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
            
        path = filedialog.asksaveasfilename(initialdir=default_dir, defaultextension=".html", initialfile=default_name, filetypes=[("HTML Report", "*.html")])
        if path:
            self.status_indicator.configure(text="Erstelle Report...", text_color="yellow")
            self.update() 
            success = self.logic.generate_html_report(path, filter_mode=mode, filter_value=value, as_gallery=is_gallery, date_start=date_start, date_end=date_end)
            if success:
                self.logic.open_url(path)
                try:
                    folder = os.path.dirname(path)
                    self.logic.open_system_folder(folder)
                except: pass
                self.status_indicator.configure(text=f"Report ({mode}) erstellt!", text_color="green")
            else:
                self.status_indicator.configure(text="Fehler beim Export.", text_color="red")

    def export_mobile_app(self):
        default_dir = self.logic.get_export_path()
        path = ""
        
        if default_dir and os.path.isdir(default_dir):
            path = os.path.join(default_dir, "Astro_Mobile.html")
        else:
            path = filedialog.asksaveasfilename(defaultextension=".html", initialfile="Astro_Mobile.html", filetypes=[("HTML App", "*.html")])
            
        if path:
            self.status_indicator.configure(text="Generiere App...", text_color="yellow")
            self.update() 
            
            def run_export():
                success, msg = self.logic.export_mobile(path)
                self.after(0, lambda: self._on_mobile_export_finished(success, msg, path))
                
            threading.Thread(target=run_export, daemon=True).start()

    def _on_mobile_export_finished(self, success, msg, path):
        if success:
            self.status_indicator.configure(text="📱 Handy-Sync fertig!", text_color="green")
            if not self.logic.get_export_path():
                self.logic.open_system_folder(os.path.dirname(path))
        else:
            self.status_indicator.configure(text=msg, text_color="red")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.logic.save_config(folder)
            self.refresh_library()

    def refresh_library(self):
        self.status_label.configure(text="Indiziere Bibliothek... Bitte warten (läuft im Hintergrund).", text_color="yellow")
        self.btn_scan.configure(state="disabled")
        self.status_indicator.configure(text="Scan läuft...", text_color="yellow")
        self.update() 

        def run_scan_thread():
            msg = self.logic.scan_library()
            self.after(0, lambda: self._on_library_scan_finished(msg))

        threading.Thread(target=run_scan_thread, daemon=True).start()

    def _on_library_scan_finished(self, msg):
        self.status_label.configure(text=msg, text_color="gray")
        self.status_indicator.configure(text="Scan fertig.", text_color="green")
        self.btn_scan.configure(state="normal")
        self.update_stats_display()
        if self.current_detail_name:
            self.update_display(self.logic.get_object_data(self.current_detail_name))

    def _focus_or_close_catalog(self, new_catalog_name):
        if self.win_catalog is not None and self.win_catalog.winfo_exists():
            if self.active_catalog_name == new_catalog_name:
                self.win_catalog.lift()
                self.win_catalog.focus()
                return False 
            else:
                self.win_catalog.destroy()
                return True 
        return True 

    def open_todo_list(self):
        name = "Beobachtungsliste"
        if not self._focus_or_close_catalog(name): return 
        self.status_indicator.configure(text="Lade Beobachtungsliste...", text_color="yellow")
        self.update()
        objects = self.logic.get_todo_objects()
        if not objects:
            self.status_indicator.configure(text="Beobachtungsliste ist leer.", text_color="orange")
        else:
            self.status_indicator.configure(text="Beobachtungsliste geladen.", text_color="green")
        self.active_catalog_name = name
        self.win_catalog = CatalogOverviewWindow(self, name, objects, self.logic, self.load_specific_object)

    def open_catalog_window(self, catalog_name):
        if not self._focus_or_close_catalog(catalog_name): return
        self.status_indicator.configure(text="Erstelle Tabelle...", text_color="yellow")
        self.update()
        objects = self.logic.get_catalog_objects(catalog_name)
        self.status_indicator.configure(text=f"Tabelle für {catalog_name} geladen.", text_color="green")
        if not objects and catalog_name != "NGC" and catalog_name != "Alle":
            self.status_indicator.configure(text=f"Keine Objekte für {catalog_name} gefunden.", text_color="orange")
        self.active_catalog_name = catalog_name
        self.win_catalog = CatalogOverviewWindow(self, catalog_name, objects, self.logic, self.load_specific_object)

    def open_constellation_selector(self):
        if self.win_const_select is not None and self.win_const_select.winfo_exists():
            self.win_const_select.lift()
            self.win_const_select.focus()
            return
        const_list = self.logic.get_available_constellations()
        if not const_list:
            self.status_indicator.configure(text="Keine Sternbilder gefunden.", text_color="orange")
            return
        self.win_const_select = ConstellationSelectionDialog(self, const_list, self.open_constellation_table)

    def open_constellation_table(self, const_name):
        if not self._focus_or_close_catalog(const_name): return
        self.status_indicator.configure(text=f"Lade Sternbild {const_name}...", text_color="yellow")
        self.update()
        objects = self.logic.get_constellation_objects(const_name)
        if not objects:
            self.status_indicator.configure(text=f"Fehler: Keine Objekte in {const_name}", text_color="red")
            return
        self.status_indicator.configure(text=f"Sternbild {const_name} geladen.", text_color="green")
        self.active_catalog_name = const_name
        self.win_catalog = CatalogOverviewWindow(self, const_name, objects, self.logic, self.load_specific_object)

    def open_skymap(self):
        if self.win_map is not None and self.win_map.winfo_exists():
            self.win_map.lift()
            self.win_map.focus()
            return
        self.win_map = SkyMapWindow(self, self.logic, self.load_specific_object)
        
    def generate_and_open_atlas(self):
        self.status_indicator.configure(text="Erstelle interaktiven Atlas...", text_color="yellow")
        self.add_log_message("Sammle Bilddaten für den Himmelsatlas...")
        self.update()
        
        def on_atlas_ready(success, msg):
            color = "green" if success else "red"
            self.after(0, self.status_indicator.configure, {"text": f"{'✅' if success else '❌'} {msg}", "text_color": color})
            self.after(0, self.add_log_message, msg)
                
        # Das eigentliche Bauen des Atlas verlagern wir in einen Thread, damit das Programm nicht einfriert
        import threading
        threading.Thread(target=lambda: self.logic.create_aladin_lite_atlas(on_atlas_ready), daemon=True).start()

    def show_missing_objects(self, catalog_name):
        if self.win_missing is not None and self.win_missing.winfo_exists():
            self.win_missing.destroy()
        missing = self.logic.get_missing_objects(catalog_name)
        self.win_missing = MissingObjectsWindow(self, catalog_name, missing)

    def open_about(self):
        if self.win_about is not None and self.win_about.winfo_exists():
            self.win_about.lift()
            self.win_about.focus()
            return
        self.win_about = AboutWindow(self)
        
    def open_app_settings(self):
        if getattr(self, "win_settings", None) is not None and self.win_settings.winfo_exists():
            self.win_settings.lift()
            self.win_settings.focus()
            return
            
        def on_settings_saved():
            self.status_indicator.configure(text="Einstellungen gespeichert!", text_color="green")
            if self.current_detail_name:
                self._execute_search(self.current_detail_name, exact_match=True)

        self.win_settings = SettingsWindow(self, self.logic, on_save_callback=on_settings_saved)
        
    def open_catalog_editor(self):
        from gui_popups import CatalogEditorWindow
        if getattr(self, "win_editor", None) is not None and self.win_editor.winfo_exists():
            self.win_editor.lift()
            self.win_editor.focus()
            return
        self.win_editor = CatalogEditorWindow(self, self.logic)

    def toggle_todo_status(self):
        if not self.current_detail_name: return
        status = self.todo_var.get()
        self.logic.set_todo_status(self.current_detail_name, status)

    def update_stats_display(self):
        stats = self.logic.get_library_stats()
        m = stats["messier"]
        self.m_stats_lbl.configure(text=f"Messier: {m['count']}/{m['total']} ({int(m['pct']*100)}%)")
        self.m_progress.set(m['pct'])
        c = stats["caldwell"]
        self.c_stats_lbl.configure(text=f"Caldwell: {c['count']}/{c['total']} ({int(c['pct']*100)}%)")
        self.c_progress.set(c['pct'])

    def perform_search_btn(self):
        self.perform_search(None)

    def perform_search(self, event):
        query = self.search_entry.get()
        if not query: return
        self._execute_search(query)

    def load_specific_object(self, query):
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, query)
        self._execute_search(query, exact_match=True)
        try:
            self.deiconify() 
            self.lift() 
            self.focus_force() 
        except: pass

    def go_back_to_parent(self):
        if self.current_parent_constellation:
            self.filter_var.set("Alle") 
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, self.current_parent_constellation)
            self._execute_search(self.current_parent_constellation)
   
    def _execute_search(self, query, exact_match=False):
        filter_mode = self.filter_var.get()
        show_seestar = self.check_seestar_var.get()
        show_dwarf = self.check_dwarf_var.get()
        show_s30 = self.check_s30_var.get()
        if not isinstance(show_seestar, bool): show_seestar = True if str(show_seestar) in ["1", "True", "on"] else False
        if not isinstance(show_dwarf, bool): show_dwarf = True if str(show_dwarf) in ["1", "True", "on"] else False
        if not isinstance(show_s30, bool): show_s30 = True if str(show_s30) in ["1", "True", "on"] else False

        self.status_indicator.configure(text="Suche läuft...", text_color="yellow")
        self.btn_search.configure(state="disabled")
        self.update()
        
        def run_search_in_thread():
            data = self.logic.get_object_data(query, filter_mode, show_seestar, show_dwarf, show_s30, exact_match)
            self.after(0, lambda: self._on_search_finished(data))

        threading.Thread(target=run_search_in_thread, daemon=True).start()

    def _on_search_finished(self, data):
        self.btn_search.configure(state="normal")
        self.update_display(data)

    def change_object_type(self, choice):
        if not self.current_detail_name: return
        self.logic.set_object_type(self.current_detail_name, choice)
        self.status_indicator.configure(text=f"Typ auf '{choice}' gesetzt!", text_color="green")
        actual_type = self.logic.determine_object_type(self.current_detail_name)
        self.lbl_current_type.configure(text=f"Aktuell: {actual_type}")

    def copy_coordinates(self):
        coords = self.coords_label.cget("text")
        if coords and "---" not in coords:
            self.clipboard_clear()
            self.clipboard_append(coords)
            self.status_indicator.configure(text="✅ Koordinaten kopiert!", text_color="green")

    def refresh_coordinates(self):
        if not self.current_detail_name: return
        success = self.logic.delete_from_cache(self.current_detail_name)
        self.btn_refresh_coords.configure(state="disabled")
        self.coords_label.configure(text="Lade neu...")
        self.status_indicator.configure(text="Cache gelöscht. Frage online ab...", text_color="yellow")
        self.update()
        self.after(500, lambda: self._execute_search(self.current_detail_name, exact_match=True))

    def save_current_note(self):
        if not self.current_detail_name: return
        text = self.notes_textbox.get("1.0", "end-1c")
        success = self.logic.save_note(self.current_detail_name, text)
        if success:
            self.status_indicator.configure(text="Notiz gespeichert!", text_color="green")
        else:
            self.status_indicator.configure(text="Fehler beim Speichern der Notiz.", text_color="red")

    def update_live_altitude(self):
        if self.current_ra is not None and self.current_dec is not None:
            best_time = self.logic.get_best_observation_time(self.current_ra, self.current_dec)
            self.obs_time_label.configure(text=f"🔭 {best_time}")
            self.live_update_timer = self.after(60000, self.update_live_altitude)

    def update_display(self, data):
        self.obj_name_label.configure(text=data["name"])
        self.current_detail_name = data["name"] 
        self.current_internal_id = data.get("internal_id")
        saved_type = self.logic.get_saved_type(data["name"])
        self.type_var.set(saved_type)
        actual_type = self.logic.determine_object_type(data["name"])
        self.lbl_current_type.configure(text=f"Aktuell: {actual_type}")
        self.coords_label.configure(text=data["coords"])
        
        if self.live_update_timer is not None:
            self.after_cancel(self.live_update_timer)
            self.live_update_timer = None

        if data.get("ra_decimal") is not None and data.get("dec_decimal") is not None:
            self.current_ra = data["ra_decimal"]
            self.current_dec = data["dec_decimal"]
            
            # 1. Timer triggern
            self.update_live_altitude()

            # 2. Mond-Info abfragen und Label setzen
            sep, phase = self.logic.get_moon_info(self.current_ra, self.current_dec)
            if sep is not None:
                if sep < 20: 
                    self.moon_warning_label.configure(text=f"⚠️ Mond stört! (Distanz: {int(sep)}°, Phase: {int(phase)}%)", text_color="#e74c3c")
                elif sep < 40: 
                    self.moon_warning_label.configure(text=f"🌙 Mond in der Nähe (Distanz: {int(sep)}°, Phase: {int(phase)}%)", text_color="#f39c12")
                else:
                    self.moon_warning_label.configure(text=f"🌑 Mond OK (Distanz: {int(sep)}°)", text_color="gray")
            
            # 3. Graph zeichnen
            self.update_altitude_plot(self.current_ra, self.current_dec)
        else:
            self.current_ra = None
            self.current_dec = None
            self.obs_time_label.configure(text="")
            self.moon_warning_label.configure(text="")
            self.ax.clear()
            self.ax.set_facecolor('#2b2b2b')
            self.canvas.draw()
        
        self.path_entry.delete(0, "end")
        
        if "---" not in data["coords"]: 
            self.btn_copy.configure(state="normal")
            self.btn_refresh_coords.configure(state="normal")
        else: 
            self.btn_copy.configure(state="disabled")
            self.btn_refresh_coords.configure(state="disabled")
        
        if data["wiki_url"]: self.btn_wiki.configure(state="normal", command=lambda: self.logic.open_url(data["wiki_url"]))
        else: self.btn_wiki.configure(state="disabled")
        
        if data.get("ra_decimal") is not None and data.get("dec_decimal") is not None:
            self.btn_skyview.configure(state="normal", command=lambda: self.logic.open_legacy_survey(data["ra_decimal"], data["dec_decimal"]))
            self.btn_aladin.configure(state="normal", command=lambda: self.logic.open_aladin(data["ra_decimal"], data["dec_decimal"]))
        else:
            self.btn_skyview.configure(state="disabled")
            self.btn_aladin.configure(state="disabled")
            
        if data["found_locally"] and not data["is_constellation"]:
            self.btn_smartsuite.configure(state="normal") 
        else:
            self.btn_smartsuite.configure(state="disabled")    

        if data["parent_constellation"] and not data["is_constellation"]:
            self.current_parent_constellation = data["parent_constellation"]
            self.btn_back.pack(side="left", padx=10) 
        else:
            self.current_parent_constellation = None
            self.btn_back.pack_forget() 

        self.notes_textbox.delete("1.0", "end")
        if data.get("user_note"):
            self.notes_textbox.insert("1.0", data["user_note"])
        
        self.todo_var.set(data.get("todo_status", False))
        
        self.refresh_tags_display()

        if data["name"] == "---" or data["is_constellation"]:
             self.notes_textbox.configure(state="disabled")
             self.btn_save_note.configure(state="disabled")
             self.chk_todo.configure(state="disabled")
             self.type_menu.configure(state="disabled") 
             
             self.tag_entry.configure(state="disabled")
             self.btn_add_tag.configure(state="disabled")
        else:
             self.notes_textbox.configure(state="normal")
             self.btn_save_note.configure(state="normal")
             self.chk_todo.configure(state="normal")
             self.type_menu.configure(state="normal")
             
             self.tag_entry.configure(state="normal")
             self.btn_add_tag.configure(state="normal")

        self.current_image_list = data.get("images", []) 
        self.current_img_index = 0
        if not data["found_locally"] and not data["is_constellation"]:
            self.current_image_list = []

        self.display_current_image() 

        if data["found_locally"] and not data["is_constellation"]:
            self.status_indicator.configure(text=f"✅ {data.get('status_text', 'Gefunden')}", text_color="green")
            self.path_entry.insert(0, data["path"])
            self.btn_open_folder.configure(state="normal", command=lambda: self.logic.open_system_folder(data["path"]))
            self._populate_scroll_list(data.get("constellation_content", []))
        elif data["is_constellation"]:
            self.status_indicator.configure(text=data.get("status_text", "Auswahl getroffen"), text_color="#3B8ED0")
            self.path_entry.insert(0, data["path"] if data["path"] else "---")
            if data["path"]:
                self.btn_open_folder.configure(state="normal", command=lambda: self.logic.open_system_folder(data["path"]))
            else:
                self.btn_open_folder.configure(state="disabled")
            self._populate_scroll_list(data["constellation_content"])
        else:
             self.status_indicator.configure(text=data.get("status_text", "Nicht gefunden"), text_color="orange")
             self.btn_open_folder.configure(state="disabled")
             self._populate_scroll_list([]) 

    def display_current_image(self):
        self.img_nav_frame.pack_forget()
        if self.image_label:
            try: self.image_label.destroy()
            except: pass
        self.image_label = None
        self.current_image_obj = None

        self.image_label = ctk.CTkLabel(self.image_container, text="")
        
        self.image_label.pack(expand=True, side="top") 

        if not self.current_image_list:
            self.image_label.configure(
                text="[Kein Bild]\n(Objekt noch nicht im Archiv)", 
                image=None, 
                width=600, height=400,
                fg_color="#1a1a1a",
                corner_radius=10
            )
            self.image_label.unbind("<Button-1>")
            self.image_label.configure(cursor="")
            return

        self.img_nav_frame.pack(fill="x", pady=5, side="bottom")
        img_path = self.current_image_list[self.current_img_index]
        try:
            pil_img = Image.open(img_path)
            pil_img.thumbnail((600, 400)) 
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            self.image_label.configure(text="", image=ctk_img)
            self.current_image_obj = ctk_img 
            self.image_label.configure(cursor="hand2")
            self.image_label.bind("<Button-1>", lambda e: self.open_large_view())
        except (UnidentifiedImageError, Exception) as e:
            error_msg = f"Vorschau nicht möglich\n({os.path.basename(img_path)})"
            self.image_label.configure(text=error_msg, image=None)
            self.current_image_obj = None

        self.lbl_img_count.configure(text=f"{self.current_img_index + 1} / {len(self.current_image_list)}")
        if self.current_img_index > 0: self.btn_prev_img.configure(state="normal")
        else: self.btn_prev_img.configure(state="disabled")
        if self.current_img_index < len(self.current_image_list) - 1: self.btn_next_img.configure(state="normal")
        else: self.btn_next_img.configure(state="disabled")

    def show_next_image(self):
        if self.current_img_index < len(self.current_image_list) - 1:
            self.current_img_index += 1
            self.display_current_image()

    def show_prev_image(self):
        if self.current_img_index > 0:
            self.current_img_index -= 1
            self.display_current_image()

    def open_large_view(self):
        if not self.current_image_list: return
        ImageViewerWindow(self, self.current_image_list, self.current_img_index, self.current_detail_name)
            
    def show_smartsuite_context(self, event):
        menu = Menu(self, tearoff=0)
        menu.add_command(label="Pfad zu SmartSuite.exe ändern", command=self.change_smartsuite_path)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def change_smartsuite_path(self):
        exe_path = filedialog.askopenfilename(title="Wähle deine SmartSuite.exe (oder smart_main.py)", filetypes=[("SmartSuite", "*.exe *.py")])
        if exe_path:
            self.logic.set_smartsuite_path(exe_path)
            self.status_indicator.configure(text="Pfad gespeichert!", text_color="green")

    def launch_smartsuite(self):
        base_path = self.path_entry.get() 
        if not base_path or not os.path.isdir(base_path):
            self.status_indicator.configure(text="❌ Ungültiger Pfad im Textfeld!", text_color="red")
            return
        lights_path = os.path.join(base_path, "lights")
        final_path = lights_path if os.path.exists(lights_path) else base_path
        exe_path = self.logic.get_smartsuite_path()
        if not exe_path or not os.path.exists(exe_path):
            exe_path = filedialog.askopenfilename(title="Wähle deine SmartSuite.exe (oder smart_main.py)", filetypes=[("SmartSuite", "*.exe *.py")])
            if exe_path: self.logic.set_smartsuite_path(exe_path)
            else: return 
        try:
            if exe_path.endswith(".py"): subprocess.Popen(["python", exe_path, "--analyze", final_path], cwd=os.path.dirname(exe_path))
            else: subprocess.Popen([exe_path, "--analyze", final_path], cwd=os.path.dirname(exe_path))
            self.status_indicator.configure(text=f"SmartSuite gestartet... ({'Lights-Ordner' if final_path == lights_path else 'Hauptordner'})", text_color="#8E44AD")
        except Exception as e: self.status_indicator.configure(text=f"Fehler beim Start: {e}", text_color="red")        
            
    def _populate_scroll_list(self, items):
        for widget in self.scroll_list.winfo_children(): widget.destroy()
        if not items: return
        for item_name in items:
            btn = ctk.CTkButton(self.scroll_list, text=item_name, fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"), anchor="w", command=lambda x=item_name: self._on_list_item_click(x))
            btn.pack(fill="x", pady=2)

    def _on_list_item_click(self, display_name):
        self._execute_search(display_name, exact_match=True)

    def add_current_tag(self):
        if not self.current_detail_name: return
        new_tag = self.tag_entry.get().strip()
        if new_tag:
            success = self.logic.add_tag(self.current_detail_name, new_tag)
            if success:
                self.tag_entry.delete(0, "end")
                self.refresh_tags_display()
            else:
                self.status_indicator.configure(text="Tag konnte nicht gespeichert werden.", text_color="red")

    def remove_tag_by_name(self, tag_name):
        if not self.current_detail_name: return
        self.logic.remove_tag(self.current_detail_name, tag_name)
        self.refresh_tags_display()

    def search_for_tag(self, tag_text):
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, tag_text)
        self.perform_search_btn()

    def refresh_tags_display(self):
        for widget in self.tags_scroll.winfo_children():
            widget.destroy()
            
        search_key = getattr(self, "current_internal_id", None) or self.current_detail_name
        tags_data = self.logic.get_tags(search_key)
        
        if isinstance(tags_data, list):
             auto_tags = []
             manual_tags = tags_data
        else:
             auto_tags = tags_data.get("auto", [])
             manual_tags = tags_data.get("manual", [])
        
        all_tags = []
        
        for t in auto_tags:
            all_tags.append({
                "text": f"★ {t}", 
                "fg": "#1a5276", 
                "hover": "#154360", 
                "cmd": lambda x=t: self.search_for_tag(x), 
                "state": "normal",
                "cursor": "hand2" 
            })
            
        for t in manual_tags:
            all_tags.append({
                "text": f"{t} ✖", 
                "fg": "#34495e", 
                "hover": "#c0392b", 
                "cmd": lambda x=t: self.remove_tag_by_name(x), 
                "state": "normal",
                "cursor": "hand2"
            })

        if not all_tags:
            ctk.CTkLabel(self.tags_scroll, text="Keine Tags", text_color="gray", font=ctk.CTkFont(size=11)).grid(row=0, column=0, columnspan=2, pady=5)
            return

        for i, tag_def in enumerate(all_tags):
            btn = ctk.CTkButton(
                self.tags_scroll, 
                text=tag_def["text"], 
                font=ctk.CTkFont(size=11),
                height=24,
                fg_color=tag_def["fg"], 
                hover_color=tag_def["hover"],
                state=tag_def["state"],
                cursor=tag_def.get("cursor", "arrow"), 
                command=tag_def["cmd"]
            )
            
            r = i // 2
            c = i % 2
            
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="ew")

    # --- NEU FÜR WIMS: Plot-Update Methode ---
    def update_altitude_plot(self, ra, dec):
        times, alts = self.logic.get_altitude_curve(ra, dec)
        self.ax.clear()
        self.ax.set_facecolor('#2b2b2b')
        
        if len(times) == 0:
            self.canvas.draw()
            return

        # Kurve zeichnen
        self.ax.plot(times, alts, color='#3498db', linewidth=2)
        
        # Bereich über dem Horizont (0°) blau einfärben
        fill_condition = [a > 0 for a in alts]
        self.ax.fill_between(times, alts, 0, where=fill_condition, color='#3498db', alpha=0.3)

        # Horizont-Linie (Rot gestrichelt)
        self.ax.axhline(0, color='#e74c3c', linestyle='--', linewidth=1)

        # Styling der Achsen
        # --- NEU: Lokale Zeitzone (inkl. Sommerzeit) auf die X-Achse zwingen ---
        local_tz = datetime.now().astimezone().tzinfo
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
        self.ax.tick_params(axis='x', colors='gray', labelsize=9)
        self.ax.tick_params(axis='y', colors='gray', labelsize=9)
        self.ax.set_ylim(-10, 90)
        self.ax.set_ylabel("Höhe (°)", color='gray', fontsize=9)

        self.fig.tight_layout()
        self.canvas.draw()
        
    # --- WIMS IMPORT HANDLER ---
    def open_wims_import(self):
        filepath = filedialog.askopenfilename(title="WIMS CSV auswählen", filetypes=[("CSV Dateien", "*.csv")])
        if not filepath: return
        
        self.status_indicator.configure(text="Lese WIMS Datei...", text_color="yellow")
        self.update()
        
        wims_objects = self.logic.parse_wims_csv(filepath)
        
        if not wims_objects:
            self.status_indicator.configure(text="❌ Fehler beim Lesen der CSV (oder Datei leer).", text_color="red")
            return
            
        from gui_popups import WimsImportWindow
        WimsImportWindow(self, wims_objects, self._on_wims_import_confirmed)
        
    def _on_wims_import_confirmed(self, selected_keys):
        if not selected_keys: return
        count = self.logic.import_wims_objects(selected_keys)
        self.status_indicator.configure(text=f"✅ {count} Objekte in Todo-Liste importiert!", text_color="green")
        
        # Todo-Liste nach dem Import direkt automatisch öffnen
        self.open_todo_list()