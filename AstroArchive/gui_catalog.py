import customtkinter as ctk
from PIL import Image
import os
import re
import threading
import time
import math
from datetime import datetime
from gui_popups import ImageViewerWindow 
from tkinter import ttk, messagebox

# --- Astropy Warnungs-Spam stummschalten ---
import warnings
warnings.filterwarnings("ignore")

try:
    from astropy.logger import log
    log.setLevel('ERROR') # Zwingt Astropy, nur noch echte Fehler zu melden
except ImportError:
    pass
# -------------------------------------------

class CatalogOverviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, catalog_name, data_list, logic, on_click_command=None):
        super().__init__(parent)
        self.logic = logic
        self.data_list = data_list
        self.filtered_data = list(data_list) 
        self.catalog_name = catalog_name
        self.on_click_command = on_click_command 
        
        self.image_cache = {}
        self.is_loading = False
        self.current_load_index = 0
        self.load_job = None
        self.is_destroyed = False 
        
        # --- PAGINIERUNG ---
        self.current_page = 1
        self.items_per_page = 50
        
        self.title(f"Katalog-Übersicht: {catalog_name}")
        self.geometry("1600x900") 
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.sort_column = "sort_key"
        self.sort_reverse = False
        if not hasattr(self.logic, 'sort_settings'):
            self.logic.sort_settings = {}
        saved_sort = self.logic.sort_settings.get(self.catalog_name)
        self.save_sort_var = ctk.BooleanVar(value=False)
        
        if saved_sort:
            self.sort_column = saved_sort.get("col", "sort_key")
            self.sort_reverse = saved_sort.get("rev", False)
            self.save_sort_var.set(True)

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # --- TOP FRAME (DEIN EXAKTES ORIGINAL-LAYOUT) ---
        self.top_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.top_frame.pack(fill="x", pady=(0, 15))
        
        self.lbl_title = ctk.CTkLabel(self.top_frame, text=f"Objekte im '{catalog_name}'", font=ctk.CTkFont(size=22, weight="bold"))
        self.lbl_title.pack(side="left", padx=(10, 15))
        
        self.lbl_loading = ctk.CTkLabel(self.top_frame, text="Berechne Live-Daten...", text_color="orange", font=ctk.CTkFont(size=12))
        self.lbl_loading.pack(side="left", padx=20)

        self.chk_save = ctk.CTkCheckBox(self.top_frame, text="Sortierung merken", variable=self.save_sort_var, command=self.toggle_sort_save)
        self.chk_save.pack(side="right", padx=(10, 0))

        self.btn_slideshow = ctk.CTkButton(self.top_frame, text="▶  Katalog Slideshow", 
                                           fg_color="#8E44AD", hover_color="#6C3483", width=160,
                                           command=self.start_global_slideshow)
        self.btn_slideshow.pack(side="right", padx=(10, 10))

        self.btn_reload = ctk.CTkButton(self.top_frame, text="🔄 Neu laden", width=100, 
                                        fg_color="#F39C12", hover_color="#D68910", command=self.reload_data)
        self.btn_reload.pack(side="right", padx=(10, 10))

        self.filter_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.filter_frame.pack(side="right", padx=(20, 10))
        
        ctk.CTkLabel(self.filter_frame, text="Zeitraum:").pack(side="left", padx=(0, 5))
        self.entry_start = ctk.CTkEntry(self.filter_frame, width=90, placeholder_text="01.01.2025")
        self.entry_start.pack(side="left", padx=2)
        ctk.CTkLabel(self.filter_frame, text="-").pack(side="left")
        self.entry_end = ctk.CTkEntry(self.filter_frame, width=90, placeholder_text="31.12.2026")
        self.entry_end.pack(side="left", padx=2)
        ctk.CTkButton(self.filter_frame, text="Filter", width=50, command=self.filter_by_date).pack(side="left", padx=5)

        # NEU: Filter-Zeile 2 (Suchen, Fehlende, Sternbild)
        self.filter_row_2 = ctk.CTkFrame(self.main_container, fg_color="transparent", height=40)
        self.filter_row_2.pack(fill="x", pady=(0, 10))

        self.chk_missing_var = ctk.BooleanVar(value=False)
        self.chk_missing = ctk.CTkCheckBox(self.filter_row_2, text="Nur Fehlende", variable=self.chk_missing_var, command=self._apply_filters)
        self.chk_missing.pack(side="left", padx=10)

        self.const_var = ctk.StringVar(value="Alle Sternbilder")
        self.combo_const = ctk.CTkOptionMenu(self.filter_row_2, variable=self.const_var, command=self._apply_filters_event, width=150)
        self.combo_const.pack(side="left", padx=10)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        self.entry_search = ctk.CTkEntry(self.filter_row_2, placeholder_text="Suchen...", width=250, textvariable=self.search_var)
        self.entry_search.pack(side="right", padx=10)

        # --- SEITEN-STEUERUNG UNTEN ---
        self.pagination_frame = ctk.CTkFrame(self.main_container, fg_color="transparent", height=40)
        self.pagination_frame.pack(fill="x", side="bottom", pady=(10, 0))

        self.btn_prev_page = ctk.CTkButton(self.pagination_frame, text="◀ Vorherige Seite", width=120, command=self.prev_page)
        self.btn_prev_page.pack(side="left", padx=20)

        self.lbl_page_info = ctk.CTkLabel(self.pagination_frame, text="Seite 1 / 1", font=ctk.CTkFont(weight="bold", size=14))
        self.lbl_page_info.pack(side="left", expand=True)

        self.btn_next_page = ctk.CTkButton(self.pagination_frame, text="Nächste Seite ▶", width=120, command=self.next_page)
        self.btn_next_page.pack(side="right", padx=20)

        # --- TABELLEN HEADER ---
        self.table_header = ctk.CTkFrame(self.main_container, fg_color="#1F6AA5", height=35, corner_radius=0)
        self.table_header.pack(fill="x")
        
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=0, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True)

        # 13 Spalten
        self.col_weights = {0: 1, 1: 1, 2: 3, 3: 2, 4: 2, 5: 1, 6: 2, 7: 2, 8: 1, 9: 2, 10: 1, 11: 1, 12: 1}
        for col, weight in self.col_weights.items():
            self.table_header.grid_columnconfigure(col, weight=weight, uniform="group1")
            self.scroll_frame.grid_columnconfigure(col, weight=weight, uniform="group1")
        self.table_header.grid_columnconfigure(13, weight=0, minsize=20) 

        self._create_header_btn("Stat", "found", 0)
        self._create_header_btn("Bild", "image", 1) 
        self._create_header_btn("Objekt", "sort_key", 2, anchor="w")
        self._create_header_btn("Sternbild", "constellation", 3, anchor="w")
        self._create_header_btn("Transit", "time_to_transit", 4, anchor="w") 
        self._create_header_btn("Score", "score", 5)
        self._create_header_btn("Typ", "type", 6, anchor="w") 
        self._create_header_btn("Teleskop", "telescope", 7, anchor="w")
        self._create_header_btn("Fits", "fits_count", 8)
        self._create_header_btn("Datum", "raw_date", 9)
        self._create_header_btn("Notiz", "", 10, state="disabled")
        self._create_header_btn("Aktion", "", 11, state="disabled")
        self._create_header_btn("Aladin", "", 12, state="disabled") 

        # Starte Berechnung
        threading.Thread(target=self._run_initialization, daemon=True).start()

    def _create_header_btn(self, text, sort_col, col_idx, state="normal", anchor="center"):
        if anchor == "w": text = "  " + text
        btn = ctk.CTkButton(
            self.table_header, text=text, font=ctk.CTkFont(weight="bold", size=13),
            fg_color="transparent", hover_color="#144870", corner_radius=0,
            anchor=anchor, state=state, command=lambda: self.sort_data(sort_col)
        )
        btn.grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=0)

    # --- SEITEN NAVIGATION ---
    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.populate_table()

    def next_page(self):
        max_page = max(1, (len(self.filtered_data) - 1) // self.items_per_page + 1)
        if self.current_page < max_page:
            self.current_page += 1
            self.populate_table()

    # --- VEKTOR BERECHNUNG ---
    def _run_initialization(self):
        if self.is_destroyed: return
        ra_list, dec_list, valid_indices = [], [], []
        
        for i, item in enumerate(self.data_list):
            if self.is_destroyed: return
            internal = item.get("internal_id")
            if "constellation" not in item or item["constellation"] == "---":
                if internal and internal in self.logic.index:
                    parent_id = self.logic.index[internal].get("parent")
                    if parent_id: item["constellation"] = self.logic.constellation_names.get(parent_id, parent_id.title())
            
            ra, dec = None, None
            if internal and internal in self.logic.index:
                fits = self.logic.index[internal].get("fits_sample")
                if fits:
                    try:
                        from utils import read_fits_coords
                        _, r, d, ok = read_fits_coords(fits)
                        if ok: ra, dec = r, d
                    except: pass
            
            if ra is None:
                clean = self.logic._get_clean_key(item.get("name", ""))
                keys = [item.get("name", ""), clean]
                if internal: keys.extend([internal, self.logic._get_clean_key(internal)])
                keys.extend(self.logic._get_all_aliases(item.get("name", "")))
                for k in keys:
                    if k in self.logic.coord_cache:
                        ra = self.logic.coord_cache[k]["ra"]
                        dec = self.logic.coord_cache[k]["dec"]
                        break
            
            if ra is not None and dec is not None:
                # --- FIX: Sternbild live berechnen, falls es noch fehlt ---
                if item.get("constellation", "---") == "---":
                    try:
                        from astropy.coordinates import SkyCoord, get_constellation
                        import astropy.units as u
                        c = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
                        full_latin = get_constellation(c, short_name=False)
                        item["constellation"] = self.logic.constellation_names.get(full_latin.lower(), full_latin)
                    except: pass
                # ---------------------------------------------------------
                
                ra_list.append(ra); dec_list.append(dec); valid_indices.append(i)
            else:
                item["score"] = 0; item["time_to_transit"] = "---"

        if valid_indices:
            try:
                from astropy.time import Time
                from astropy.coordinates import EarthLocation, SkyCoord, get_body
                import astropy.units as u
                lat, lon = self.logic.get_location()
                loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
                now = Time.now()
                lst = now.sidereal_time('apparent', longitude=loc.lon).hour
                
                moon = get_body("moon", now)
                sun = get_body("sun", now)
                moon_phase = (1 - math.cos(math.radians(sun.separation(moon).deg))) / 2 * 100
                coords = SkyCoord(ra=ra_list*u.deg, dec=dec_list*u.deg)
                moon_seps = coords.separation(moon).deg
                
                for idx, ra, dec, m_sep in zip(valid_indices, ra_list, dec_list, moon_seps):
                    item = self.data_list[idx]
                    if hasattr(ra, 'item'): ra = ra.item()
                    if hasattr(dec, 'item'): dec = dec.item()
                    if hasattr(m_sep, 'item'): m_sep = m_sep.item()

                    max_alt = 90 - abs(lat - dec)
                    alt_score = max(0, min(50, (max_alt - 15) / 65 * 50))
                    dist_factor = max(0, (90 - m_sep) / 90)
                    penalty = (moon_phase / 100) * dist_factor * 50
                    
                    item["score"] = int(round(alt_score + (50 - penalty)))
                    item["time_to_transit"] = float(((ra / 15.0) - lst) % 24)
            except: pass

        if not self.is_destroyed:
            self.after(0, self.update_dropdowns)
            self.after(50, lambda: self.sort_data(self.sort_column, flip=False)) # Initiale Sortierung

    def update_dropdowns(self):
        if self.is_destroyed: return
        consts = set(i.get("constellation", "---") for i in self.data_list if i.get("constellation") not in [None, "---"])
        const_list = ["Alle Sternbilder"] + sorted(list(consts))
        self.combo_const.configure(values=const_list)

    def _apply_filters_event(self, choice=None): self._apply_filters()

    def _apply_filters(self, *args):
        q = self.search_var.get().lower()
        only_missing = self.chk_missing_var.get()
        selected_const = self.const_var.get()

        filtered = []
        for item in self.data_list:
            if q and q not in item["name"].lower() and q not in item.get("internal_id", "").lower(): continue
            if only_missing and item.get("found", False): continue
            if selected_const != "Alle Sternbilder" and item.get("constellation", "---") != selected_const: continue
            filtered.append(item)

        self.filtered_data = filtered
        self.sort_data(self.sort_column, apply_filter=False) 
        
        self.current_page = 1 
        self.populate_table()

    def on_close(self):
        self.is_destroyed = True 
        if self.load_job: self.after_cancel(self.load_job)
        self.destroy()

    def toggle_sort_save(self):
        if self.save_sort_var.get(): self.logic.save_sort_state(self.catalog_name, self.sort_column, self.sort_reverse)
        else:
            if self.catalog_name in self.logic.sort_settings:
                del self.logic.sort_settings[self.catalog_name]
                self.logic.save_config(self.logic.base_folder)

    def reload_data(self):
        self.lbl_loading.configure(text="Aktualisiere...", text_color="yellow")
        self.btn_reload.configure(state="disabled")
        self.update()
        cache_key = "todo" if self.catalog_name == "Beobachtungsliste" else (self.catalog_name if self.catalog_name in ["Messier", "Caldwell", "NGC", "Alle"] else f"const_{self.catalog_name}")
        if cache_key in self.logic.list_cache: del self.logic.list_cache[cache_key]

        if self.catalog_name == "Beobachtungsliste": self.data_list = self.logic.get_todo_objects()
        elif self.catalog_name in ["Messier", "Caldwell", "NGC", "Alle"]: self.data_list = self.logic.get_catalog_objects(self.catalog_name)
        else: self.data_list = self.logic.get_constellation_objects(self.catalog_name)

        threading.Thread(target=self._run_initialization, daemon=True).start()
        self.btn_reload.configure(state="normal")

    def filter_by_date(self):
        start_str = self.entry_start.get().strip()
        end_str = self.entry_end.get().strip()
        if not start_str and not end_str:
            self._apply_filters()
            return

        self.filtered_data = [item for item in self.data_list if self.logic.is_date_in_range(item.get("date"), start_str, end_str)]
        self.sort_data(self.sort_column, apply_filter=False)
        self.current_page = 1
        self.populate_table()

    def start_global_slideshow(self):
        images = [item["image"] for item in self.filtered_data if item.get("found") and item.get("image") and os.path.exists(item["image"])]
        if images:
            self.viewer_window = ImageViewerWindow(self, images, 0, f"Katalog-Show: {self.catalog_name}")
            self.viewer_window.toggle_slideshow()
        else:
            self.btn_slideshow.configure(text="Keine Bilder!", fg_color="gray")
            self.after(2000, lambda: self.btn_slideshow.configure(text="▶  Katalog Slideshow", fg_color="#8E44AD"))

    def sort_data(self, col_key, apply_filter=True, flip=True):
        if not col_key: return
        if self.load_job: self.after_cancel(self.load_job)
        
        if flip:
            if self.sort_column == col_key: self.sort_reverse = not self.sort_reverse
            else: self.sort_column = col_key; self.sort_reverse = False
        else:
            self.sort_column = col_key

        def sort_helper(x):
            val = x.get(self.sort_column)
            if val is None or val == "---" or val == "":
                return -999999 if self.sort_column in ["score", "time_to_transit", "fits_count"] else ("\uFFFF" if not self.sort_reverse else "")
            
            if hasattr(val, 'item'): val = val.item() 
                
            if self.sort_column in ["score", "time_to_transit", "fits_count"]:
                try: return float(val)
                except: return -999999
            
            import re
            s = str(val).lower()
            return [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', s)]

        self.filtered_data.sort(key=sort_helper, reverse=self.sort_reverse)
        self.data_list.sort(key=sort_helper, reverse=self.sort_reverse)
        
        if self.save_sort_var.get(): 
            self.logic.save_sort_state(self.catalog_name, self.sort_column, self.sort_reverse)
        
        if apply_filter: 
            self.current_page = 1
            self.populate_table()

    def copy_coords_online(self, query, btn_widget):
        btn_widget.configure(text="⏳", state="disabled")
        self.update() 
        data = self.logic.get_object_data(query, filter_mode="Alle")
        coords = data["coords"]
        if coords and "---" not in coords:
            self.master.clipboard_clear(); self.master.clipboard_append(coords)
            btn_widget.configure(text="✅", fg_color="green", state="normal")
        else: btn_widget.configure(text="❌", fg_color="red", state="normal")
        self.after(2000, lambda: btn_widget.configure(text="📋", fg_color="#1F6AA5"))

    def open_aladin_click(self, query, btn):
        orig_text, orig_color = btn.cget("text"), btn.cget("fg_color")
        btn.configure(text="⏳", state="disabled"); self.update()
        data = self.logic.get_object_data(query)
        if data.get("ra_decimal") is not None and data.get("dec_decimal") is not None:
            self.logic.open_aladin(data["ra_decimal"], data["dec_decimal"])
            btn.configure(text="✅", fg_color="green", state="normal")
        else: btn.configure(text="❌", fg_color="red", state="normal")
        self.after(2000, lambda: btn.configure(text=orig_text, fg_color=orig_color, state="normal") if btn.winfo_exists() else None)

    # --- ALADIN LOKAL WORKFLOW (Tabelle) ---
    def show_row_aladin_context(self, event, query, path):
        from tkinter import Menu, filedialog
        menu = Menu(self, tearoff=0)
        menu.add_command(label="🚀 Bild lokal solven (ASTAP -> Aladin Desktop)", command=lambda: self.run_row_local_aladin(query, path))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()
        
    def run_row_local_aladin(self, query, path):
        from tkinter import filedialog
        start_dir = path if path else self.logic.base_folder
        
        # --- FIX: Erlaube JPG und PNG im Dateidialog ---
        file_path = filedialog.askopenfilename(initialdir=start_dir, title="Bild auswählen", filetypes=[("Bilder", "*.fits *.fit *.fts *.jpg *.jpeg *.png"), ("Alle Dateien", "*.*")])
        if not file_path: return
        
        # Koordinaten für diesen Eintrag abrufen
        data = self.logic.get_object_data(query, filter_mode="Alle")
        coords = data.get("coords", "")
        
        self.lbl_loading.configure(text="ASTAP läuft...", text_color="yellow")
        self.update()
        
        def status_cb(msg, is_ok):
            # Update für das Label im Katalog
            color = "green" if is_ok else "orange"
            self.after(0, self.lbl_loading.configure, {"text": msg, "text_color": color})
            
            # NEU: Wir schicken die Nachricht an das Log-Fenster der Haupt-GUI (master statt parent!)
            if hasattr(self.master, "add_log_message"):
                self.after(0, self.master.add_log_message, msg)

        # NEU: Start-Nachricht ins Log schreiben
        if hasattr(self.master, "add_log_message"):
            self.master.add_log_message(f"Starte Workflow für: {os.path.basename(file_path)}")
            
        self.logic.run_local_solve_and_aladin(file_path, coords, status_cb)
    
    def on_object_name_click(self, query_id):
        if self.on_click_command: self.on_click_command(query_id)

    def populate_table(self):
        if self.is_destroyed: return
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        
        total_items = len(self.filtered_data)
        max_page = max(1, (total_items - 1) // self.items_per_page + 1)
        if self.current_page > max_page: self.current_page = max_page
            
        self.lbl_page_info.configure(text=f"Seite {self.current_page} von {max_page}")
        self.btn_prev_page.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_next_page.configure(state="normal" if self.current_page < max_page else "disabled")

        self.current_load_index = (self.current_page - 1) * self.items_per_page
        self.lbl_loading.configure(text="Zeichne Seite...", text_color="orange")
        self._load_next_chunk()

    def _load_next_chunk(self):
        if self.is_destroyed: return
        
        chunk_size = 50 
        total_items = len(self.filtered_data)
        page_end = min(self.current_page * self.items_per_page, total_items)
        end_index = min(self.current_load_index + chunk_size, page_end)
        
        for i in range(self.current_load_index, end_index):
            if self.is_destroyed: return
            self._create_row(i, self.filtered_data[i])

        self.current_load_index = end_index

        if self.current_load_index < page_end:
            pct = int(((self.current_load_index - (self.current_page - 1) * self.items_per_page) / self.items_per_page) * 100)
            self.lbl_loading.configure(text=f"Zeichne... {pct}%")
            self.load_job = self.after(10, self._load_next_chunk)
        else:
            self.lbl_loading.configure(text=f"Fertig ({total_items} Objekte total)", text_color="gray")
            self.load_job = None

    def _create_row(self, row_idx, item):
        row_color = "#2B2B2B" if row_idx % 2 == 0 else "#333333"
        
        status_icon, status_color = ("✅", "green") if item.get("found") else ("❌", "red")
        ctk.CTkLabel(self.scroll_frame, text=status_icon, text_color=status_color, fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=0, sticky="nsew", pady=1, padx=(0,1))
        
        img_frame = ctk.CTkFrame(self.scroll_frame, fg_color=row_color, corner_radius=0, height=50)
        img_frame.grid(row=row_idx, column=1, sticky="nsew", pady=1, padx=(0,1))
        
        if item.get("found") and item.get("image") and os.path.exists(item["image"]):
            img_path = item["image"]
            img_list = item.get("images", [img_path])
            if img_path in self.image_cache:
                self._create_img_button(img_frame, self.image_cache[img_path], img_path, img_list, item["name"])
            else:
                try:
                    pil_img = Image.open(img_path)
                    pil_img.thumbnail((46, 46)) 
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                    self.image_cache[img_path] = ctk_img
                    self._create_img_button(img_frame, ctk_img, img_path, img_list, item["name"])
                except: pass
        
        search_query = item.get("internal_id") if item.get("internal_id") else item["name"]
        ctk.CTkButton(self.scroll_frame, text="  " + item["name"], anchor="w", fg_color=row_color, corner_radius=0, height=50, hover_color="#444444", command=lambda q=search_query: self.on_object_name_click(q)).grid(row=row_idx, column=2, sticky="nsew", pady=1, padx=(0,1))
        ctk.CTkLabel(self.scroll_frame, text="  " + item.get("constellation", "---"), anchor="w", fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=3, sticky="nsew", pady=1, padx=(0,1))

        t_val = item.get("time_to_transit")
        if t_val is None or t_val == 99 or t_val == "---": t_text, t_color = "---", "gray"
        else: t_text, t_color = f"in {int(t_val)}h {int((t_val - int(t_val)) * 60)}m", ("#3498db" if t_val < 4 else "white")
        ctk.CTkLabel(self.scroll_frame, text="  " + t_text, text_color=t_color, anchor="w", fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=4, sticky="nsew", pady=1, padx=(0,1))

        score_val = item.get("score", 0)
        s_text, s_color = (f"{score_val} %", ("#2ecc71" if score_val >= 80 else "#f39c12" if score_val >= 50 else "#e74c3c")) if score_val > 0 else ("---", "gray")
        ctk.CTkLabel(self.scroll_frame, text=s_text, text_color=s_color, font=ctk.CTkFont(weight="bold"), fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=5, sticky="nsew", pady=1, padx=(0,1))

        ctk.CTkLabel(self.scroll_frame, text="  " + item.get("type", "---"), anchor="w", fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=6, sticky="nsew", pady=1, padx=(0,1))
        ctk.CTkLabel(self.scroll_frame, text="  " + item.get("telescope", "---"), anchor="w", fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=7, sticky="nsew", pady=1, padx=(0,1))
        ctk.CTkLabel(self.scroll_frame, text=str(item.get("fits_count", 0)), fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=8, sticky="nsew", pady=1, padx=(0,1))
        ctk.CTkLabel(self.scroll_frame, text=item.get("date", "---"), fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=9, sticky="nsew", pady=1, padx=(0,1))
        
        note_text = "✅" if self.logic.get_note(item["name"]) else ""
        ctk.CTkLabel(self.scroll_frame, text=note_text, text_color="green", font=ctk.CTkFont(size=14), fg_color=row_color, corner_radius=0, height=50).grid(row=row_idx, column=10, sticky="nsew", pady=1, padx=(0,1))

        btn_frame = ctk.CTkFrame(self.scroll_frame, fg_color=row_color, corner_radius=0, height=50)
        btn_frame.grid(row=row_idx, column=11, sticky="nsew", pady=1)
        if item.get("found"):
            ctk.CTkButton(btn_frame, text="📂", width=40, height=30, command=lambda p=item.get("path"): self.logic.open_system_folder(p)).place(relx=0.5, rely=0.5, anchor="center")
        else:
            fallback_q = item["name"]
            btn = ctk.CTkButton(btn_frame, text="📋", width=40, height=30, fg_color="#1F6AA5")
            btn.configure(command=lambda q=fallback_q, b=btn: self.copy_coords_online(q, b))
            btn.place(relx=0.5, rely=0.5, anchor="center")

        aladin_frame = ctk.CTkFrame(self.scroll_frame, fg_color=row_color, corner_radius=0, height=50)
        aladin_frame.grid(row=row_idx, column=12, sticky="nsew", pady=1)
        if item.get("name"):
            btn_aladin = ctk.CTkButton(aladin_frame, text="Aladin", width=60, height=30, fg_color="#8B0000", hover_color="#600000")
            btn_aladin.configure(command=lambda q=search_query, b=btn_aladin: self.open_aladin_click(q, b))
            # --- NEU: Rechtsklick für lokales Solve ---
            btn_aladin.bind("<Button-3>", lambda e, q=search_query, p=item.get("path"): self.show_row_aladin_context(e, q, p))
            btn_aladin.place(relx=0.5, rely=0.5, anchor="center")

    def _create_img_button(self, parent, ctk_img, current_img, img_list, name):
        idx = img_list.index(current_img) if current_img in img_list else 0
        ctk.CTkButton(parent, text="", image=ctk_img, width=46, height=46, fg_color="transparent", corner_radius=0, hover=False, command=lambda imgs=img_list, i=idx, n=name: self.open_large_image(imgs, i, n)).place(relx=0.5, rely=0.5, anchor="center")

    def open_large_image(self, img_list, start_index, name):
        self.viewer_window = ImageViewerWindow(self, img_list, start_index, name)