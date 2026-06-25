# ==============================================================================
# MODULE_ASTROTRACKER.PY - Integrierter Astrotracker (Kometen, Asteroiden, SN)
# ==============================================================================
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import threading
import webbrowser
import math
import numpy as np
import datetime
import os
import subprocess
import urllib.parse
import time
import requests
import re
import json
import gzip
from bs4 import BeautifulSoup
from io import StringIO

import smart_utils as utils
import module_obs_list

# Skyfield: Wir nutzen jetzt den zentralen AstroData Ordner!
from skyfield.api import Loader, wgs84
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN

DATA_DIR = utils.get_data_dir()
sky_loader = Loader(DATA_DIR, verbose=True)

def _df(filename):
    """Hilfsfunktion: Gibt den absoluten Pfad im AstroData-Ordner zurück."""
    return os.path.join(DATA_DIR, filename)

# ==============================================================================
# DIALOGE & BASIS-KLASSE
# ==============================================================================
class TimeInputDialog(ctk.CTkToplevel):
    # NEU: title_text und desc_text als Parameter!
    def __init__(self, master, default_time="", title_text="Aufnahmezeitpunkt", desc_text="Bitte Zeitpunkt eingeben:"):
        super().__init__(master)
        self.title(title_text)
        self.geometry("380x200")
        self.result = None
        self.attributes("-topmost", True)
        ctk.CTkLabel(self, text=desc_text, font=("Arial", 12, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="Format: YYYY-MM-DD HH:MM", text_color="gray").pack(pady=(0, 10))
        self.entry = ctk.CTkEntry(self, width=200, justify="center")
        self.entry.pack(pady=5)
        self.entry.insert(0, default_time)
        ctk.CTkButton(self, text="Bestätigen", command=self.on_ok).pack(pady=20)
        self.bind("<Return>", lambda e: self.on_ok())
        self.entry.focus()
        self.grab_set()
        self.wait_window()
        
    def on_ok(self):
        self.result = self.entry.get().strip()
        self.destroy()

class AstroModuleBase(ctk.CTkFrame):
    def __init__(self, master, obj_type_name="Unknown"):
        super().__init__(master, fg_color="transparent")
        self.obj_type_name = obj_type_name 
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._setup_base_ui()

    def _setup_base_ui(self):
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(10,0))
        
        self.table_container = ctk.CTkFrame(self)
        self.table_container.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        
        self._style_treeview()
        self.tree = ttk.Treeview(self.table_container, show='headings')
        self.vsb = ttk.Scrollbar(self.table_container, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self.table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.vsb.grid(row=0, column=1, sticky='ns')
        self.hsb.grid(row=1, column=0, sticky='ew')
        self.table_container.grid_columnconfigure(0, weight=1)
        self.table_container.grid_rowconfigure(0, weight=1)
        
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Double-1>", self.on_double_click)

        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(self.log_frame, orientation="horizontal", height=10)
        self.progress_bar.pack(fill="x", padx=5, pady=(5, 0))
        self.progress_bar.set(0.0)

        self.log_box = ctk.CTkTextbox(self.log_frame, height=80, font=("Consolas", 11), fg_color="#1e1e1e")
        self.log_box.pack(fill="x", padx=5, pady=5)
        self.log_box.configure(state="disabled")
        
    def _style_treeview(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2b2b2b", foreground="white", rowheight=28, fieldbackground="#2b2b2b", borderwidth=0)
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading", background="#565b5e", foreground="white", relief="flat", font=('Helvetica', 10, 'bold'), cursor="hand2")

    def log(self, message):
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{time_str}] {message}\n"
        def append_log():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", full_msg)
            self.log_box.see("end") 
            self.log_box.configure(state="disabled")
        self.after(0, append_log)
    
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white", activebackground="#1f538d")
            menu.add_command(label="📋 Direkt auf Beobachtungsliste setzen", command=lambda: self.export_to_smartsuite_list(item))
            menu.add_separator()
            menu.add_command(label="🌌 An N.I.N.A. (Framing) übergeben", command=lambda: self.send_to_nina(item))
            menu.add_separator()
            menu.add_command(label="🚀 Bild prüfen (ASTAP -> Aladin Desktop)", command=lambda: self.run_automation_workflow(item))
            menu.add_separator()
            menu.add_command(label="🎯 Koordinaten (RA/DEC) kopieren", command=lambda: self.copy_coords_to_clipboard(item))
            menu.add_command(label="📋 Alle Infos in Zwischenablage kopieren", command=lambda: self.copy_to_clipboard(item))
            menu.add_separator()
            self.add_custom_context_menu_items(menu, item)
            menu.add_command(label="🌟 Koordinaten in Aladin Lite (Browser) öffnen", command=lambda: self.open_in_aladin_lite(item))
            menu.post(event.x_root, event.y_root)

    def add_custom_context_menu_items(self, menu, item): pass
    def on_double_click(self, event): pass

    def get_coords_from_item(self, item):
        row_values = self.tree.item(item, 'values')
        display_cols = self.tree["columns"]
        ra_val, dec_val = None, None
        for i, col_name in enumerate(display_cols):
            if "r.a." in col_name.lower(): ra_val = row_values[i]
            elif "dec" in col_name.lower(): dec_val = row_values[i]
        if ra_val and dec_val: return f"{ra_val} {dec_val}"
        return None

    def _parse_ra_to_decimal(self, ra_str):
        parts = str(ra_str).split(':')
        h = float(parts[0]); m = float(parts[1]) if len(parts) > 1 else 0; s = float(parts[2]) if len(parts) > 2 else 0
        return (h + (m / 60.0) + (s / 3600.0)) * 15.0

    def _parse_dec_to_decimal(self, dec_str):
        dec_str = str(dec_str).strip()
        sign = -1 if dec_str.startswith('-') else 1
        clean_str = dec_str.replace('+', '').replace('-', '')
        parts = clean_str.split(':')
        d = float(parts[0]); m = float(parts[1]) if len(parts) > 1 else 0; s = float(parts[2]) if len(parts) > 2 else 0
        return sign * (d + (m / 60.0) + (s / 3600.0))

    def copy_coords_to_clipboard(self, item):
        coords = self.get_coords_from_item(item)
        if coords:
            self.clipboard_clear(); self.clipboard_append(coords)
            self.log(f"In Zwischenablage kopiert: {coords}")

    def copy_to_clipboard(self, item):
        row_values = self.tree.item(item, 'values')
        cols = self.tree["columns"]
        copy_text = "\n".join([f"{c}: {str(v)}" for c, v in zip(cols, row_values)])
        self.clipboard_clear(); self.clipboard_append(copy_text)
        self.log("Komplette Infos kopiert!")

    def open_in_aladin_lite(self, item):
        coords = self.get_coords_from_item(item)
        if coords:
            safe_coords = urllib.parse.quote(coords)
            webbrowser.open(f"https://aladin.cds.unistra.fr/AladinLite/?target={safe_coords}&fov=0.3")

    def send_to_nina(self, item):
        row_values = self.tree.item(item, 'values')
        obj_name = str(row_values[0]).replace("🔗 ", "").strip() 
        coords_str = self.get_coords_from_item(item)
        if not coords_str: return
        parts = coords_str.split()
        if len(parts) == 2:
            try:
                ra_dec = self._parse_ra_to_decimal(parts[0])
                dec_dec = self._parse_dec_to_decimal(parts[1])
                response = requests.get(f"http://localhost:1888/v2/api/framing/set-coordinates?RAangle={ra_dec}&DecAngle={dec_dec}", timeout=3)
                if response.status_code == 200: self.log(f"✅ Koordinaten erfolgreich an N.I.N.A. übergeben!")
                else: self.log(f"❌ Fehler von N.I.N.A.: {response.status_code}")
            except: self.log("❌ N.I.N.A. API nicht erreichbar.")

    def export_to_smartsuite_list(self, item):
        row_values = self.tree.item(item, 'values')
        obj_name = str(row_values[0]).replace("🔗 ", "").strip()
        
        import pytz
        local_tz = pytz.timezone('Europe/Berlin')
        
        # Wir schlagen heute Abend 22:00 Uhr LOKALZEIT vor
        default_time = datetime.datetime.now().replace(hour=22, minute=0, second=0).strftime('%Y-%m-%d %H:%M')
        
        if self.obj_type_name == "Supernova":
            res = default_time 
        else:
            # Wir rufen den Dialog explizit mit "Lokalzeit" Texten auf!
            res = TimeInputDialog(
                self, 
                default_time=default_time, 
                title_text="Planung (Lokalzeit)", 
                desc_text="Bitte geplanten Beobachtungszeitpunkt\n(LOKALE UHRZEIT) eingeben:"
            ).result
            
        if not res: return 
        
        try:
            # 1. Wir lesen die Eingabe als lokales Datum (ohne Zeitzone)
            naive_dt = datetime.datetime.strptime(res, "%Y-%m-%d %H:%M")
            # 2. Wir machen es zu einem "echten" deutschen Datum (berücksichtigt Sommerzeit!)
            local_dt = local_tz.localize(naive_dt)
            # 3. Für Skyfield (die Mathematik) rechnen wir es hart in UTC um
            obs_time_utc = local_dt.astimezone(datetime.timezone.utc)
        except:
            messagebox.showerror("Fehler", "Falsches Datums-/Zeitformat.")
            return

        # NEU: Berechne die Koordinaten für diesen Zukunfts-Moment!
        coords_str = None
        ra_dec = None
        dec_dec = None
        
        try:
            ts = sky_loader.timescale()
            t_o = ts.from_datetime(obs_time_utc)  # HIER GEÄNDERT!
            eph = sky_loader('de421.bsp')
            cfg = utils.load_config()
            lat = float(cfg.get("default_lat", 51.16))
            lon = float(cfg.get("default_lon", 10.45))
            observer = (eph['earth'] + wgs84.latlon(lat, lon)).at(t_o)
            
            target_orb = None
            if self.obj_type_name == "Comet" and hasattr(self, 'raw_comets_df'):
                rows = self.raw_comets_df[self.raw_comets_df['designation'] == obj_name]
                if not rows.empty:
                    from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
                    target_orb = eph['sun'] + mpc.comet_orbit(rows.iloc[0], ts, GM_SUN)
            elif self.obj_type_name == "Asteroid" and hasattr(self, 'raw_asteroids_df'):
                rows = self.raw_asteroids_df[self.raw_asteroids_df['designation'] == obj_name]
                if not rows.empty:
                    from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
                    target_orb = eph['sun'] + mpc.mpcorb_orbit(rows.iloc[0], ts, GM_SUN)
                    
            if target_orb:
                obs = observer.observe(target_orb)
                # .observe() ist von Haus aus bereits astrometrisch (J2000)!
                ra, dec, _ = obs.radec() 
                ra_dec = ra.hours * 15.0
                dec_dec = dec.degrees
                
                h, m, s = ra.hms()
                abs_d = abs(dec.degrees)
                dd = int(abs_d)
                mm = int((abs_d - dd) * 60)
                ss = (abs_d - dd - mm/60) * 3600
                c_str = f"RA: {int(h):02d}h {int(m):02d}m {int(s):02d}s | DEC: {'+' if dec.degrees>=0 else '-'}{dd:02d}d {mm:02d}m {int(ss):02d}s"
        except Exception as e:
            self.log(f"Konnte Vorhersage nicht berechnen: {e}")
            pass

        # FALLBACK: Wenn die Ephemeriden-Vorausberechnung scheitert (oder es eine Supernova ist)
        if ra_dec is None or dec_dec is None:
            coords_str_fallback = self.get_coords_from_item(item)
            if not coords_str_fallback: return
            parts = coords_str_fallback.split()
            if len(parts) == 2:
                ra_dec = self._parse_ra_to_decimal(parts[0])
                dec_dec = self._parse_dec_to_decimal(parts[1])
                c_str = f"RA: {parts[0]} | DEC: {parts[1]}"
            else: return
        
        cfg = utils.load_config()
        target_dir = cfg.get("custom_tools_path", "")
        notes_path = os.path.join(target_dir, "user_notes.json") if target_dir else "user_notes.json"
        cache_path = os.path.join(target_dir, "coordinate_cache.json") if target_dir else "coordinate_cache.json"
        
        clean_name = obj_name.lower().replace(" ", "").replace("_", "").replace("-", "")
            
        cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f: cache = json.load(f)
            except: pass
            
        cache[clean_name] = {"ra": ra_dec, "dec": dec_dec, "coords_str": c_str}
        
        try:
            with open(cache_path, "w", encoding="utf-8") as f: json.dump(cache, f, indent=4)
        except: pass
            
        notes = {}
        if os.path.exists(notes_path):
            try:
                with open(notes_path, "r", encoding="utf-8") as f: notes = json.load(f)
            except: pass
            
        target_key = obj_name
        for k in notes.keys():
            if k.lower().replace(" ", "").replace("_", "").replace("-", "") == clean_name:
                target_key = k; break
                
        # Hinweis im Text: Wir zeigen dem Nutzer die LOKALZEIT an!
        calc_note = f" (Berechnet für {local_dt.strftime('%d.%m. %H:%M')} Lokalzeit)" if self.obj_type_name != "Supernova" else ""
        
        if target_key not in notes: 
            notes[target_key] = {"todo": True, "note": f"Geplant aus AstroTracker{calc_note}.", "type": self.obj_type_name, "tags": []}
        else: 
            notes[target_key]["todo"] = True
            # BUGFIX: Überschreibe die alte Notiz zwingend mit der neu berechneten Zeit!
            notes[target_key]["note"] = f"Geplant aus AstroTracker{calc_note}."
            
        try:
            with open(notes_path, "w", encoding="utf-8") as f: json.dump(notes, f, indent=4, ensure_ascii=False)
            self.log(f"✅ '{obj_name}' erfolgreich zur Liste hinzugefügt!{calc_note}")
            app = self.winfo_toplevel()
            if hasattr(app, "frames") and "obslist" in app.frames:
                app.frames["obslist"].refresh_ui()
        except Exception as e: 
            messagebox.showerror("Fehler", f"Fehler:\n{e}")

    def show_automation_log(self, initial_text):
        if hasattr(self, 'log_win') and self.log_win.winfo_exists(): self.log_win.destroy()
        self.log_win = ctk.CTkToplevel(self)
        self.log_win.title("Automatisierungs-Protokoll")
        self.log_win.geometry("600x400")
        self.log_win.attributes("-topmost", True)
        self.auto_log_text = ctk.CTkTextbox(self.log_win, width=580, height=380, font=("Consolas", 10))
        self.auto_log_text.pack(padx=10, pady=10, fill="both", expand=True)
        self.auto_log_text.insert("end", initial_text + "\n")
        self.auto_log_text.configure(state="disabled")

    def update_automation_log(self, text):
        if hasattr(self, 'log_win') and self.log_win.winfo_exists():
            self.auto_log_text.configure(state="normal")
            self.auto_log_text.insert("end", text + "\n")
            self.auto_log_text.see("end") 
            self.auto_log_text.configure(state="disabled")

# ==============================================================================
# MODUL: KOMETEN
# ==============================================================================
class CometTrackerModul(AstroModuleBase):
    def __init__(self, master):
        super().__init__(master, obj_type_name="Comet")
        self.df = pd.DataFrame()
        self.display_df = pd.DataFrame()
        self.raw_comets_df = pd.DataFrame() 
        self.current_sort_col = tk.StringVar(value="_mag_val")
        self.sort_ascending = tk.BooleanVar(value=True)
        self.setup_module_ui()
        if not self.load_from_cache(): self.log("Warte auf manuellen Datenabruf...")

    def setup_module_ui(self):
        self.refresh_btn = ctk.CTkButton(self.top_frame, text="MPC Daten laden & Berechnen", command=self.load_data_thread, width=200)
        self.refresh_btn.pack(side="left", padx=10, pady=10)
        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(self.top_frame, placeholder_text="Schnellsuche...", textvariable=self.search_var, width=200)
        self.search_entry.pack(side="left", padx=10, pady=10)
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        self.check_visible_var = tk.BooleanVar(value=False)
        self.check_visible = ctk.CTkCheckBox(self.top_frame, text="Nur sichtbare (> 5° Höhe)", variable=self.check_visible_var, command=self.apply_filter)
        self.check_visible.pack(side="left", padx=20, pady=10)
        self.status_label = ctk.CTkLabel(self.top_frame, text="Bereit", text_color="gray")
        self.status_label.pack(side="right", padx=10, pady=10)

    def add_custom_context_menu_items(self, menu, item):
        menu.add_command(label="📖 Details auf Yoshida (aerith.net) öffnen", command=lambda: self.open_yoshida_link(item))
        menu.add_separator()
        menu.add_command(label="🗓️ Als Kalender-Termin exportieren", command=lambda: self.export_to_smartsuite(item))

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.open_yoshida_link(item)

    def export_to_smartsuite(self, item):
        row_values = self.tree.item(item, 'values')
        obj_name = str(row_values[0])
        matching_row = self.display_df[self.display_df['Komet'] == obj_name]
        if matching_row.empty: return
        row_data = matching_row.iloc[0]
        
        if "_time_val" in row_data and not pd.isna(row_data["_time_val"]): dt = datetime.datetime.fromtimestamp(row_data["_time_val"])
        else: dt = datetime.datetime.now().replace(hour=22, minute=0)
            
        iso_date = dt.strftime("%Y-%m-%d"); display_date = dt.strftime("%d.%m."); time_str = dt.strftime("%H:%M")
        title = f"{obj_name}"
        
        mag = row_data.get("Mag", "---"); trend = row_data.get("Trend (7 Tage)", "---")
        alt = row_data.get("_max_alt", "---")
        alt_str = f"{int(alt)}°" if isinstance(alt, (float, int)) and alt != -90.0 else "---"
        ra = row_data.get("R.A.", "---"); dec = row_data.get("Decl.", "---")
        
        desc = f"Komet zur optimalen Beobachtungszeit!\nHelligkeit: {mag} ({trend})\nHöhe am Himmel: {alt_str}\nKoordinaten: RA {ra} | DEC {dec}"
        
        if module_obs_list.add_event(iso_date, display_date, time_str, title, desc, "☄"):
            self.log(f"Erfolgreich: '{obj_name}' zum Kalender hinzugefügt!")
            app = self.winfo_toplevel()
            if hasattr(app, "frames"):
                if "obslist" in app.frames: app.frames["obslist"].refresh_ui()
                if "calendar" in app.frames: app.frames["calendar"].refresh_ui()
        else:
            messagebox.showinfo("Bereits vorhanden", f"Der Komet '{obj_name}' steht an diesem Tag bereits im Kalender!")

    def load_from_cache(self):
        if os.path.exists(_df("cache_kometen.pkl")):
            if (time.time() - os.path.getmtime(_df("cache_kometen.pkl"))) / 3600 < 12: 
                try:
                    self.df = pd.read_pickle(_df("cache_kometen.pkl"))
                    if os.path.exists(_df("cache_kometen_raw.pkl")): self.raw_comets_df = pd.read_pickle(_df("cache_kometen_raw.pkl"))
                    self.update_after_load()
                    return True
                except: pass
        return False

    def open_yoshida_link(self, item):
        row_values = self.tree.item(item, 'values')
        name = str(row_values[0])
        try:
            matching_row = self.display_df[self.display_df['Komet'] == name]
            if not matching_row.empty and '_yoshida_url' in matching_row.columns:
                webbrowser.open(matching_row.iloc[0]['_yoshida_url'])
            else: webbrowser.open("http://www.aerith.net/comet/weekly/current.html")
        except: pass

    def load_data_thread(self):
        self.refresh_btn.configure(state="disabled"); self.progress_bar.set(0.0)
        threading.Thread(target=self.fetch_data, daemon=True).start()

    def fetch_data(self):
        try:
            self.log("Schritt 1: Yoshida Links analysieren...")
            yoshida_mags = {}; yoshida_links = {}
            try:
                response = requests.get("http://www.aerith.net/comet/weekly/current.html", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                def get_clean_id(n):
                    m = re.search(r'([1-9][0-9]*[PCDX]|[PCDX]/\d{4}\s*[A-Z]{1,2}[0-9]*)', str(n))
                    return m.group(1).replace(" ", "").upper() if m else None
                for a in soup.find_all('a', href=True):
                    cid = get_clean_id(a.get_text(strip=True))
                    if cid: yoshida_links[cid] = urllib.parse.urljoin("http://www.aerith.net/comet/weekly/current.html", a['href'])
                lines = soup.get_text(separator='\n').split('\n'); current_comet_id = None
                for i, line in enumerate(lines):
                    line = line.strip(); cid = get_clean_id(line)
                    if cid and len(line) < 80: current_comet_id = cid
                    if "Date(TT)" in line and current_comet_id:
                        for j in range(i+1, min(len(lines), i+15)):
                            if any(lines[j].strip().startswith(m) for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                                try: yoshida_mags[current_comet_id] = float(lines[j].split()[9])
                                except: pass
                                break 
                self.log(f"Erfolg: {len(yoshida_mags)} Helligkeiten & Detail-Links gefunden.")
            except: self.log("Warnung: Yoshida nicht erreichbar.")

            self.log("Schritt 2: Lade MPC Bahnelemente via Skyfield...")
            ts = sky_loader.timescale(); t = ts.now(); t_fut = ts.utc(t.utc.year, t.utc.month, t.utc.day + 7)
            eph = sky_loader('de421.bsp'); sun, earth = eph['sun'], eph['earth']
            cfg = utils.load_config(); lat = float(cfg.get("default_lat", 51.16)); lon = float(cfg.get("default_lon", 10.45))
            observer = earth + wgs84.latlon(lat, lon)

            with sky_loader.open(mpc.COMET_URL) as f: raw_df = mpc.load_comets_dataframe(f)
            comets_df = (raw_df.sort_values('reference').groupby('designation', as_index=False).last().set_index('designation', drop=False))
            self.raw_comets_df = comets_df
            self.log(f"Erfolg: {len(comets_df)} Kometen gefunden.")

            self.log("Schritt 3: Simuliere Sonnenlauf für lokales Dunkelheits-Fenster...")
            t_array = ts.utc(t.utc.year, t.utc.month, t.utc.day, t.utc.hour + np.arange(0, 24, 0.5))
            sun_alt, _, _ = observer.at(t_array).observe(sun).apparent().altaz()
            dark_mask = sun_alt.degrees < -15
            if not np.any(dark_mask): dark_mask = sun_alt.degrees < -12 
            if not np.any(dark_mask): dark_mask = sun_alt.degrees < -6 
            dark_times = t_array[dark_mask]

            self.log("Schritt 4: Filter Kometen & berechne Ephemeriden für sichtbare Objekte...")
            row_data = []; total = len(comets_df)
            for i, (idx_name, row) in enumerate(comets_df.iterrows()):
                if i % 15 == 0: self.after(0, lambda val=i/total: self.progress_bar.set(val))
                try:
                    k_name = str(row['designation']); cid = get_clean_id(k_name)
                    has_mpc = pd.notna(row.get('magnitude_g')) and pd.notna(row.get('magnitude_k'))
                    has_yo = cid and cid in yoshida_mags
                    if not has_mpc and not has_yo: continue 

                    try: orb = mpc.comet_orbit(row, ts, GM_SUN); target = sun + orb
                    except: continue 
                        
                    mag = None; mag_src = ""; trend_str = "❓"
                    if has_yo: mag = yoshida_mags[cid]; mag_src = " (Yoshida)"
                    if has_mpc:
                        r_n = sun.at(t).observe(target).distance().au; d_n = observer.at(t).observe(target).distance().au
                        m_n = float(row['magnitude_g']) + 5*math.log10(d_n) + 2.5*float(row['magnitude_k'])*math.log10(r_n)
                        r_f = sun.at(t_fut).observe(sun+orb).distance().au; d_f = observer.at(t_fut).observe(sun+orb).distance().au
                        m_f = float(row['magnitude_g']) + 5*math.log10(d_f) + 2.5*float(row['magnitude_k'])*math.log10(r_f)
                        diff = m_f - m_n
                        if diff < -0.05: trend_str = "↗ Heller"
                        elif diff > 0.05: trend_str = "↘ Schwächer"
                        else: trend_str = "➡ Konstant"
                        if mag is None: mag = m_n; mag_src = " (MPC)"
                    
                    if pd.notna(mag) and mag > 18.0: continue

                    obs = observer.at(t).observe(target); ra, dec, dist = obs.apparent().radec()
                    h, m, s = ra.hms(); ra_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
                    dec_deg = dec.degrees; sign = "+" if dec_deg >= 0 else "-"
                    abs_d = abs(dec_deg); dd = int(abs_d); mm = int((abs_d - dd) * 60); ss = int((abs_d - dd - mm/60) * 3600)
                    
                    best_t = "Nicht sichtbar"; max_a = -90.0; time_val = np.nan
                    if len(dark_times) > 0:
                        alts = observer.at(dark_times).observe(target).apparent().altaz()[0].degrees
                        max_a = np.max(alts)
                        if max_a >= 5.0:
                            best_idx = np.argmax(alts)
                            local_dt = dark_times[best_idx].utc_datetime().replace(tzinfo=datetime.timezone.utc).astimezone()
                            best_t = f"{local_dt.strftime('%H:%M')} Uhr ({int(max_a)}°)"; time_val = local_dt.timestamp()
                        else: best_t = "Zu tief (< 5°)"
                    else: best_t = "Keine Dunkelheit"

                    try:
                        py = int(row.get('perihelion_year', 0))
                        pm = int(row.get('perihelion_month', 0))
                        pd_day = int(row.get('perihelion_day', 0))
                        p_dist = row.get('perihelion_distance_au', np.nan)
                        if py > 0 and pm > 0:
                            if pd.notna(p_dist): perihel_str = f"{pd_day:02d}.{pm:02d}.{py} ({round(float(p_dist), 2)} AE)"
                            else: perihel_str = f"{pd_day:02d}.{pm:02d}.{py}"
                        else: perihel_str = "-"
                    except: perihel_str = "-"

                    y_url = yoshida_links.get(cid, "http://www.aerith.net/comet/weekly/current.html")
                    row_data.append({
                        "Komet": k_name, "Mag": f"{round(mag, 1)}{mag_src}" if pd.notna(mag) else "Keine Daten", 
                        "Trend (7 Tage)": trend_str, "Beste Zeit": best_t, "Perihel": perihel_str, 
                        "R.A.": ra_str, "Decl.": f"{sign}{dd:02d}:{mm:02d}:{ss:02d}", "Dist. Erde (AE)": round(dist.au, 3),
                        "Dist. Sonne (AE)": round(sun.at(t).observe(target).distance().au, 3), 
                        "_mag_val": mag if pd.notna(mag) else 99.0, "_yoshida_url": y_url, "_max_alt": max_a, "_time_val": time_val
                    })
                except: continue

            self.after(0, lambda: self.progress_bar.set(1.0)) 
            if not row_data:
                self.log("FEHLER: Keine Kometen übrig."); self.after(0, lambda: self.refresh_btn.configure(state="normal")); return

            self.df = pd.DataFrame(row_data)
            try: self.df.to_pickle(_df("cache_kometen.pkl")); self.raw_comets_df.to_pickle(_df("cache_kometen_raw.pkl"))
            except: pass
            
            self.after(0, self.update_after_load)
            self.log("Berechnung erfolgreich abgeschlossen.")
            
        except Exception as e:
            self.log(f"KRITISCHER FEHLER: {e}"); self.after(0, lambda: self.progress_bar.set(0.0))
            self.after(0, lambda: self.refresh_btn.configure(state="normal"))

    def update_after_load(self):
        self.refresh_btn.configure(state="normal"); self.apply_filter()

    def sort_by_header(self, col):
        if self.current_sort_col.get() == col: self.sort_ascending.set(not self.sort_ascending.get())
        else: self.current_sort_col.set(col); self.sort_ascending.set(True)
        self.apply_filter()

    def apply_filter(self):
        if self.df.empty: return
        t_df = self.df.copy()
        if self.check_visible_var.get() and '_max_alt' in t_df.columns: t_df = t_df[t_df['_max_alt'] >= 5.0]
        search = self.search_var.get().lower()
        if search: t_df = t_df[t_df.apply(lambda row: row.astype(str).str.lower().str.contains(search).any(), axis=1)]
        
        sort_col = self.current_sort_col.get()
        if sort_col == "Mag" and "_mag_val" in t_df.columns: sort_col = "_mag_val"
        if sort_col in t_df.columns: t_df = t_df.sort_values(by=sort_col, ascending=self.sort_ascending.get())

        self.display_df = t_df
        self.status_label.configure(text=f"{len(t_df)} Objekte"); self.populate_table(self.display_df)

    def populate_table(self, df):
        self.tree.delete(*self.tree.get_children())
        cols = [c for c in df.columns if not c.startswith("_")]; self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by_header(c))
            self.tree.column(col, width=200 if col=="Komet" else 120, anchor="w")
        for _, row in df[cols].iterrows(): self.tree.insert("", "end", values=list(row))

    def run_automation_workflow(self, item):
        cfg = utils.load_config()
        astap_exe = cfg.get("astap_path", ""); aladin_exe = cfg.get("aladin_path", "")
        if not os.path.exists(astap_exe) or not os.path.exists(aladin_exe):
            messagebox.showerror("Fehler", "Bitte setze ASTAP/Aladin Pfade in den globalen Einstellungen!")
            return

        row_vals = self.tree.item(item, 'values'); name = str(row_vals[0]).strip()
        coords = self.get_coords_from_item(item)
        if not coords: return

        fp = filedialog.askopenfilename(title="FITS auswählen", filetypes=[("FITS files", "*.fits;*.fit;*.fts")])
        if not fp: return 

        def ext_time(p):
            try:
                with open(p, 'rb') as f:
                    match = re.search(r"DATE-OBS\s*=\s*'([^']+)'", f.read(14400).decode('ascii', errors='ignore'))
                    if match:
                        d = match.group(1).strip()
                        return datetime.datetime.fromisoformat(d) if 'T' in d else datetime.datetime.strptime(d, "%Y-%m-%d")
            except: pass
            return None

        ex_t = ext_time(fp)
        d_str = ex_t.strftime('%Y-%m-%d %H:%M') if ex_t else datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
        # Wir rufen den Dialog explizit mit "UTC" Texten auf!
        res = TimeInputDialog(
            self, 
            default_time=d_str, 
            title_text="Aufnahmezeitpunkt (UTC)", 
            desc_text="Bitte Aufnahmezeitpunkt prüfen/eingeben\n(Zwingend in UTC!):"
        ).result
        if not res: return

        try: o_time = datetime.datetime.strptime(res, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        except: messagebox.showerror("Fehler", "Falsches Format."); return

        threading.Thread(target=self._auto_task, args=(fp, coords, astap_exe, aladin_exe, name, o_time), daemon=True).start()

    def _auto_task(self, fp, coords, astap, aladin, name, o_time):
        self.after(0, lambda: self.show_automation_log("Löse Bild..."))
        target = coords; lbl = name
        
        if hasattr(self, 'raw_comets_df') and not self.raw_comets_df.empty:
            try:
                rows = self.raw_comets_df[self.raw_comets_df['designation'] == name]
                if not rows.empty:
                    ts = sky_loader.timescale(); t_o = ts.from_datetime(o_time); eph = sky_loader('de421.bsp')
                    c_orb = mpc.comet_orbit(rows.iloc[0], ts, GM_SUN)
                    cfg = utils.load_config(); lat = float(cfg.get("default_lat", 51.16)); lon = float(cfg.get("default_lon", 10.45))
                    obs = (eph['earth'] + wgs84.latlon(lat, lon)).at(t_o).observe(eph['sun'] + c_orb)
                    ra, dec, _ = obs.radec(); h, m, s = ra.hms(); abs_d = abs(dec.degrees)
                    dd = int(abs_d); mm = int((abs_d - dd) * 60); ss = (abs_d - dd - mm/60) * 3600
                    target = f"{int(h):02d}:{int(m):02d}:{round(s,1):04.1f} {'+' if dec.degrees>=0 else '-'}{dd:02d}:{mm:02d}:{round(ss,1):04.1f}"
                    lbl = f"{name} ({o_time.strftime('%d.%m %H:%M')} UTC)"
            except: pass

        try:
            subprocess.run([astap, "-f", fp, "-update", "-r", "180"], capture_output=True, text=True, timeout=120)
            base, ext = os.path.splitext(fp); ini = base + ".ini"
            solved = False
            if os.path.exists(ini):
                with open(ini, "r", errors="ignore") as f:
                    txt = f.read()
                    self.after(0, lambda: self.update_automation_log(txt))
                    if "PLTSOLVD= T" in txt or "PLTSOLVD=T" in txt: solved = True
            if not solved:
                self.after(0, lambda: self.update_automation_log("FEHLER: Konnte nicht gelöst werden.")); return
                
            script = _df("temp_aladin_macro_comet.ajs")
            p_load = fp.replace('\\', '/') if ext.lower() in [".fits", ".fit"] else (fp.replace('\\', '/') if not os.path.exists(base+".wcs") else fp.replace('\\', '/'))
            
            with open(script, "w") as f: f.write(f'reset\n{target}\nDSS2\nload "{p_load}"\ndraw green circle {target} 0.9m\ndraw green string {target} "    <--- {lbl}"')
            subprocess.Popen([aladin, "-exec", f'"{script}"'])
        except Exception as e: self.after(0, lambda: self.update_automation_log(f"FEHLER:\n{e}"))

# ==============================================================================
# MODUL: KLEINPLANETEN
# ==============================================================================
class AsteroidTrackerModul(AstroModuleBase):
    def __init__(self, master):
        super().__init__(master, obj_type_name="Asteroid")
        self.df = pd.DataFrame()
        self.display_df = pd.DataFrame()
        self.raw_asteroids_df = pd.DataFrame() 
        self.current_sort_col = tk.StringVar(value="_mag_val")
        self.sort_ascending = tk.BooleanVar(value=True)
        self.setup_module_ui()
        if not self.load_from_cache(): self.log("Warte auf manuellen Datenabruf...")

    def setup_module_ui(self):
        self.list_var = tk.StringVar(value="⭐ Monats-Highlights (< 12 mag)")
        ctk.CTkOptionMenu(self.top_frame, variable=self.list_var, values=["⭐ Monats-Highlights (< 12 mag)", "Helle Hauptgürtel-Klassiker", "PHA (Hazardous)", "NEA (Near Earth)"], width=250).pack(side="left", padx=5, pady=10)
        
        self.refresh_btn = ctk.CTkButton(self.top_frame, text="Laden & Berechnen", command=self.load_data_thread, width=150)
        self.refresh_btn.pack(side="left", padx=10)
        self.search_var = tk.StringVar()
        ctk.CTkEntry(self.top_frame, placeholder_text="Suche...", textvariable=self.search_var, width=120).pack(side="left", padx=10)
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        self.check_visible_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.top_frame, text="> 15° Höhe", variable=self.check_visible_var, command=self.apply_filter).pack(side="left", padx=10)
        self.check_mag_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.top_frame, text="Mag < 18", variable=self.check_mag_var, command=self.apply_filter).pack(side="left", padx=10)
        self.status_label = ctk.CTkLabel(self.top_frame, text="Bereit", text_color="gray"); self.status_label.pack(side="right", padx=10)

    def add_custom_context_menu_items(self, menu, item):
        menu.add_command(label="📖 Objekt in SSD (JPL) öffnen", command=lambda: self.open_jpl_link(item))
        menu.add_separator()
        menu.add_command(label="🗓️ Als Kalender-Termin exportieren", command=lambda: self.export_to_smartsuite(item))

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.open_jpl_link(item)

    def export_to_smartsuite(self, item):
        row_values = self.tree.item(item, 'values')
        obj_name = str(row_values[0])
        matching_row = self.display_df[self.display_df['Objekt'] == obj_name]
        if matching_row.empty: return
        row_data = matching_row.iloc[0]
        
        if "_time_val" in row_data and not pd.isna(row_data["_time_val"]): dt = datetime.datetime.fromtimestamp(row_data["_time_val"])
        else: dt = datetime.datetime.now().replace(hour=23, minute=0)
            
        iso_date = dt.strftime("%Y-%m-%d"); display_date = dt.strftime("%d.%m."); time_str = dt.strftime("%H:%M")
        mag = row_data.get("Beste Mag", row_data.get("Mag", "---"))
        alt = row_data.get("Max. Höhe", row_data.get("Aktuelle Höhe", "---"))
        desc = f"Kleinplanet am Beobachtungspunkt!\nHelligkeit: {mag} mag\nHöhe am Himmel: {alt}\nRA: {row_data.get('R.A.')} | DEC: {row_data.get('Decl.')}"
        
        if module_obs_list.add_event(iso_date, display_date, time_str, f"{obj_name} (Optimum)", desc, "🪨"):
            self.log(f"Erfolgreich: '{obj_name}' exportiert!")
            app = self.winfo_toplevel()
            if hasattr(app, "frames"):
                if "obslist" in app.frames: app.frames["obslist"].refresh_ui()
                if "calendar" in app.frames: app.frames["calendar"].refresh_ui()
        else: messagebox.showinfo("Bereits vorhanden", "Ist bereits im Kalender!")

    def open_jpl_link(self, item):
        raw_name = str(self.tree.item(item, 'values')[0])
        clean_name = raw_name.replace("(", "").replace(")", "").strip()
        safe_name = urllib.parse.quote(clean_name)
        webbrowser.open(f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={safe_name}")

    def load_from_cache(self):
        if os.path.exists(_df("cache_asteroiden.pkl")):
            if (time.time() - os.path.getmtime(_df("cache_asteroiden.pkl"))) / 3600 < 12: 
                try:
                    self.df = pd.read_pickle(_df("cache_asteroiden.pkl"))
                    if os.path.exists(_df("cache_asteroiden_raw.pkl")): self.raw_asteroids_df = pd.read_pickle(_df("cache_asteroiden_raw.pkl"))
                    self.update_after_load()
                    return True
                except: pass
        return False

    def load_data_thread(self):
        self.refresh_btn.configure(state="disabled"); self.progress_bar.set(0.0)
        threading.Thread(target=self.fetch_data, daemon=True).start()

    def fetch_data(self):
        try:
            ts = sky_loader.timescale(); t = ts.now(); eph = sky_loader('de421.bsp'); sun, earth = eph['sun'], eph['earth']
            cfg = utils.load_config(); lat = float(cfg.get("default_lat", 51.16)); lon = float(cfg.get("default_lon", 10.45))
            observer = earth + wgs84.latlon(lat, lon)
            local_tz = datetime.datetime.now().astimezone().tzinfo

            choice = self.list_var.get(); is_hl = "Highlights" in choice

            if "PHA" in choice:
                self.log("Schritt 1: Lade Potentially Hazardous Asteroids vom MPC...")
                with sky_loader.open("https://minorplanetcenter.net/iau/MPCORB/PHA.txt") as f: df = mpc.load_mpcorb_dataframe(f)
            elif "NEA" in choice:
                self.log("Schritt 1: Lade Near Earth Asteroids vom MPC...")
                with sky_loader.open("https://minorplanetcenter.net/iau/MPCORB/NEA.txt") as f: df = mpc.load_mpcorb_dataframe(f)
            else:
                if os.path.exists(_df("bright_asteroids.txt")):
                    self.log("Schritt 1: Lade helle Asteroiden (Klassiker) aus lokalem Cache...")
                    from io import BytesIO
                    with open(_df("bright_asteroids.txt"), "rb") as f:
                        lines = f.readlines()
                        start = next((i+1 for i, l in enumerate(lines) if b"---" in l), 0)
                        df = mpc.load_mpcorb_dataframe(BytesIO(b"".join(lines[start:])))
                else:
                    self.log("WARNUNG: 'bright_asteroids.txt' fehlt! Bitte in den Einstellungen updaten.")
                    self.after(0, lambda: self.refresh_btn.configure(state="normal"))
                    return
            
            # Wir stellen sicher, dass 'designation' existiert, ohne echte Namen zu zerstören
            if 'designation' not in df.columns:
                # Falls die Bezeichnung ausnahmsweise im Index liegt, holen wir sie dort raus
                df['designation'] = df.index
            else:
                # WICHTIG für Skyfield: Wir setzen den Index auf die Namen, 
                # damit die Suche später beim Export nicht abstürzt!
                df = df.set_index('designation', drop=False)
            
            if is_hl or "Klassiker" in choice:
                if 'magnitude_H' in df.columns: df = df[df['magnitude_H'] <= 11.5]
            
            self.raw_asteroids_df = df
            self.log(f"Erfolg: {len(df)} Kleinplaneten geladen.")
            
            if is_hl:
                self.log("Schritt 2: Suche Optimum (Höhe, Dunkelheit, Zeit) in den nächsten 30 Tagen...")
            else:
                self.log("Schritt 2: Berechne Ephemeriden für sichtbare Objekte (Das kann einen Moment dauern)...")

            t_array = ts.utc(t.utc.year, t.utc.month, t.utc.day + np.arange(0, 31), 0, 0) if is_hl else None
            row_data = []; total = len(df)

            for i, (z_num, row) in enumerate(df.iterrows()):
                if total > 0 and i % max(1, total//100) == 0: self.after(0, lambda val=i/total: self.progress_bar.set(val))
                try:
                    H = row.get('magnitude_H', np.nan)
                    if pd.isna(H): continue
                    target = sun + mpc.mpcorb_orbit(row, ts, GM_SUN)
                    obj_name = str(row.get('designation', z_num))
                    
                    if is_hl:
                        obs_arr = observer.at(t_array).observe(target)
                        mags = float(H) + 5.0 * np.log10(obs_arr.apparent().distance().au * sun.at(t_array).observe(target).distance().au)
                        min_mag = np.min(mags)
                        if min_mag > 12.5: continue 
                        
                        b_day = t_array[np.argmin(mags)]
                        t_day = ts.utc(b_day.utc.year, b_day.utc.month, b_day.utc.day, 12 + np.arange(0, 24, 0.5))
                        s_alt = observer.at(t_day).observe(sun).apparent().altaz()[0].degrees
                        
                        mask = s_alt < -12
                        if not np.any(mask): mask = s_alt < -6 
                        if not np.any(mask): continue 
                        
                        d_times = t_day[mask]
                        ast_alt = observer.at(d_times).observe(target).apparent().altaz()[0].degrees
                        max_alt = np.max(ast_alt)
                        if max_alt < 10: continue 
                        
                        opt_t = d_times[np.argmax(ast_alt)]
                        l_dt = opt_t.utc_datetime().replace(tzinfo=datetime.timezone.utc).astimezone(local_tz)
                        
                        ra, dec, _ = observer.at(opt_t).observe(target).apparent().radec(); h, m, s = ra.hms()
                        abs_d = abs(dec.degrees); dd = int(abs_d); mm = int((abs_d - dd) * 60); ss = int((abs_d - dd - mm/60) * 3600)
                        
                        row_data.append({
                            "Objekt": obj_name, "Beste Mag": round(min_mag, 1), "Beste Zeit": f"{l_dt.strftime('%d.%m. %H:%M')} Uhr",
                            "Max. Höhe": f"{int(max_alt)}°", "R.A.": f"{int(h):02d}:{int(m):02d}:{int(s):02d}",
                            "Decl.": f"{'+' if dec.degrees>=0 else '-'}{dd:02d}:{mm:02d}:{ss:02d}", "_mag_val": min_mag, "_alt_val": max_alt, "_time_val": l_dt.timestamp() 
                        })
                    else:
                        obs = observer.at(t).observe(target); ra, dec, dist = obs.apparent().radec()
                        r_d = sun.at(t).observe(target).distance().au; d_d = dist.au
                        mag = float(H) + 5.0 * math.log10(d_d * r_d)
                        if mag > 22.0: continue
                        alt = obs.apparent().altaz()[0].degrees
                        
                        h, m, s = ra.hms(); abs_d = abs(dec.degrees); dd = int(abs_d); mm = int((abs_d - dd) * 60); ss = int((abs_d - dd - mm/60) * 3600)
                        row_data.append({
                            "Objekt": obj_name, "Mag": round(mag, 1), "Aktuelle Höhe": f"{int(alt)}°",
                            "Dist. Erde (AE)": round(d_d, 4), "Dist. Sonne (AE)": round(r_d, 4),
                            "R.A.": f"{int(h):02d}:{int(m):02d}:{int(s):02d}", "Decl.": f"{'+' if dec.degrees>=0 else '-'}{dd:02d}:{mm:02d}:{ss:02d}",
                            "_mag_val": mag, "_alt_val": alt
                        })
                except: continue

            self.after(0, lambda: self.progress_bar.set(1.0)) 
            if not row_data: 
                self.after(0, self.update_after_load)
                return

            self.df = pd.DataFrame(row_data)
            try: self.df.to_pickle(_df("cache_asteroiden.pkl")); self.raw_asteroids_df.to_pickle(_df("cache_asteroiden_raw.pkl"))
            except: pass
            
            self.after(0, self.update_after_load)
            self.log("Berechnung erfolgreich abgeschlossen.")
            
        except Exception as e: 
            self.log(f"KRITISCHER FEHLER: {e}")
            self.after(0, lambda: self.progress_bar.set(0.0))
            self.after(0, lambda: self.refresh_btn.configure(state="normal"))

    def update_after_load(self):
        self.refresh_btn.configure(state="normal"); self.apply_filter()

    def sort_by_header(self, col):
        if self.current_sort_col.get() == col: self.sort_ascending.set(not self.sort_ascending.get())
        else: self.current_sort_col.set(col); self.sort_ascending.set(True)
        self.apply_filter()

    def apply_filter(self):
        if self.df.empty: return
        t_df = self.df.copy()
        if self.check_visible_var.get() and '_alt_val' in t_df.columns: t_df = t_df[t_df['_alt_val'] >= 15.0]
        if self.check_mag_var.get() and '_mag_val' in t_df.columns: t_df = t_df[t_df['_mag_val'] <= 18.0]
        search = self.search_var.get().lower()
        if search: t_df = t_df[t_df.apply(lambda row: row.astype(str).str.lower().str.contains(search).any(), axis=1)]
        
        sort_col = self.current_sort_col.get()
        if sort_col in ["Mag", "Beste Mag"] and "_mag_val" in t_df.columns: sort_col = "_mag_val"
        elif sort_col in ["Aktuelle Höhe", "Max. Höhe"] and "_alt_val" in t_df.columns: sort_col = "_alt_val"
        elif sort_col == "Beste Zeit" and "_time_val" in t_df.columns: sort_col = "_time_val"

        if sort_col in t_df.columns: t_df = t_df.sort_values(by=sort_col, ascending=self.sort_ascending.get())
        self.display_df = t_df
        self.status_label.configure(text=f"{len(t_df)} Objekte"); self.populate_table(self.display_df)

    def populate_table(self, df):
        self.tree.delete(*self.tree.get_children())
        cols = [c for c in df.columns if not c.startswith("_")]; self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by_header(c))
            self.tree.column(col, width=220 if col=="Objekt" else 140 if col=="Beste Zeit" else 100, anchor="w")
        for _, row in df[cols].iterrows(): self.tree.insert("", "end", values=list(row))

    def run_automation_workflow(self, item):
        cfg = utils.load_config()
        astap_exe = cfg.get("astap_path", ""); aladin_exe = cfg.get("aladin_path", "")
        if not os.path.exists(astap_exe) or not os.path.exists(aladin_exe):
            messagebox.showerror("Fehler", "Bitte ASTAP und Aladin Pfade in den Einstellungen prüfen!")
            return

        name = str(self.tree.item(item, 'values')[0])
        coords = self.get_coords_from_item(item)
        if not coords: return

        fp = filedialog.askopenfilename(title="FITS auswählen", filetypes=[("FITS files", "*.fits;*.fit;*.fts")])
        if not fp: return 

        def ext_time(p):
            try:
                with open(p, 'rb') as f:
                    match = re.search(r"DATE-OBS\s*=\s*'([^']+)'", f.read(14400).decode('ascii', errors='ignore'))
                    if match:
                        d = match.group(1).strip()
                        return datetime.datetime.fromisoformat(d) if 'T' in d else datetime.datetime.strptime(d, "%Y-%m-%d")
            except: pass
            return None

        ex_t = ext_time(fp)
        d_str = ex_t.strftime('%Y-%m-%d %H:%M') if ex_t else datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
        # Wir rufen den Dialog explizit mit "UTC" Texten auf!
        res = TimeInputDialog(
            self, 
            default_time=d_str, 
            title_text="Aufnahmezeitpunkt (UTC)", 
            desc_text="Bitte Aufnahmezeitpunkt prüfen/eingeben\n(Zwingend in UTC!):"
        ).result
        if not res: return
        try: o_time = datetime.datetime.strptime(res, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        except: return

        threading.Thread(target=self._auto_task, args=(fp, coords, astap_exe, aladin_exe, name, o_time), daemon=True).start()

    def _auto_task(self, fp, coords, astap, aladin, name, o_time):
        self.after(0, lambda: self.show_automation_log("Löse Bild..."))
        target = coords; lbl = name
        
        if hasattr(self, 'raw_asteroids_df') and not self.raw_asteroids_df.empty:
            try:
                rows = self.raw_asteroids_df[self.raw_asteroids_df['designation'] == name]
                if not rows.empty:
                    ts = sky_loader.timescale(); t_o = ts.from_datetime(o_time); eph = sky_loader('de421.bsp')
                    c_orb = mpc.mpcorb_orbit(rows.iloc[0], ts, GM_SUN)
                    cfg = utils.load_config(); lat = float(cfg.get("default_lat", 51.16)); lon = float(cfg.get("default_lon", 10.45))
                    obs = (eph['earth'] + wgs84.latlon(lat, lon)).at(t_o).observe(eph['sun'] + c_orb)
                    ra, dec, _ = obs.radec(); h, m, s = ra.hms(); abs_d = abs(dec.degrees)
                    dd = int(abs_d); mm = int((abs_d - dd) * 60); ss = (abs_d - dd - mm/60) * 3600
                    target = f"{int(h):02d}:{int(m):02d}:{round(s,1):04.1f} {'+' if dec.degrees>=0 else '-'}{dd:02d}:{mm:02d}:{round(ss,1):04.1f}"
                    lbl = f"{name} ({o_time.strftime('%d.%m %H:%M')} UTC)"
            except: pass

        try:
            subprocess.run([astap, "-f", fp, "-update", "-r", "180"], capture_output=True, text=True, timeout=120)
            base, ext = os.path.splitext(fp); ini = base + ".ini"; solved = False
            if os.path.exists(ini):
                with open(ini, "r", errors="ignore") as f:
                    txt = f.read()
                    self.after(0, lambda: self.update_automation_log(txt))
                    if "PLTSOLVD= T" in txt or "PLTSOLVD=T" in txt: solved = True
            if not solved: self.after(0, lambda: self.update_automation_log("FEHLER: Konnte nicht gelöst werden.")); return
                
            script = _df("temp_aladin_macro_ast.ajs")
            p_load = fp.replace('\\', '/') if ext.lower() in [".fits", ".fit"] else (fp.replace('\\', '/') if not os.path.exists(base+".wcs") else fp.replace('\\', '/'))
            
            with open(script, "w") as f: f.write(f'reset\n{target}\nDSS2\nload "{p_load}"\ndraw green circle {target} 0.3m\ndraw green string {target} " <--- {lbl}"')
            subprocess.Popen([aladin, "-exec", f'"{script}"'])
        except Exception as e: self.after(0, lambda: self.update_automation_log(f"FEHLER:\n{e}"))

# ==============================================================================
# MODUL: SUPERNOVAE
# ==============================================================================
class SupernovaModul(AstroModuleBase):
    def __init__(self, master):
        super().__init__(master, obj_type_name="Supernova")
        self.df = pd.DataFrame()
        self.display_df = pd.DataFrame()
        self.current_sort_col = tk.StringVar(value="-")
        self.sort_ascending = tk.BooleanVar(value=False)
        self.setup_module_ui()
        if not self.load_from_cache(): self.log("Warte auf Datenabruf...")

    def setup_module_ui(self):
        f1 = ctk.CTkFrame(self.top_frame, fg_color="transparent"); f1.grid(row=0, column=0, columnspan=7, sticky="w", padx=10, pady=5)
        self.source_var = tk.StringVar(value="Latest Discoveries")
        ctk.CTkOptionMenu(f1, variable=self.source_var, values=["Latest Discoveries", "Active Supernovae"], width=150).pack(side="left", padx=5)
        self.refresh_btn = ctk.CTkButton(f1, text="Daten laden", command=self.load_data_thread, width=120); self.refresh_btn.pack(side="left", padx=5)
        self.search_var = tk.StringVar()
        ctk.CTkEntry(f1, placeholder_text="Suche...", textvariable=self.search_var, width=150).pack(side="left", padx=10)
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        ctk.CTkButton(f1, text="ℹ️ Typ-Legende", width=110, fg_color="#1f538d", command=self.show_type_legend).pack(side="left", padx=10)
        self.status_label = ctk.CTkLabel(f1, text="Bereit", text_color="gray"); self.status_label.pack(side="right", padx=10)

        f2 = ctk.CTkFrame(self.top_frame, fg_color="transparent"); f2.grid(row=1, column=0, columnspan=7, sticky="w", padx=10, pady=5)
        self.check_date_var = tk.BooleanVar(value=False); ctk.CTkCheckBox(f2, text="Vor max.", variable=self.check_date_var, command=self.apply_filter).pack(side="left", padx=5)
        self.weeks_var = tk.StringVar(value="4"); e1=ctk.CTkEntry(f2, textvariable=self.weeks_var, width=35); e1.pack(side="left", padx=2)
        self.weeks_var.trace_add("write", lambda *args: self.apply_filter()); ctk.CTkLabel(f2, text="W").pack(side="left", padx=(0, 15))

        self.check_mag_var = tk.BooleanVar(value=False); ctk.CTkCheckBox(f2, text="Mag <", variable=self.check_mag_var, command=self.apply_filter).pack(side="left", padx=5)
        self.mag_limit_var = tk.StringVar(value="17.0"); e2=ctk.CTkEntry(f2, textvariable=self.mag_limit_var, width=40); e2.pack(side="left", padx=2)
        self.mag_limit_var.trace_add("write", lambda *args: self.apply_filter()); ctk.CTkLabel(f2, text="").pack(side="left", padx=(0, 15))

        self.check_host_var = tk.BooleanVar(value=False); ctk.CTkCheckBox(f2, text="Benannte Galaxien", variable=self.check_host_var, command=self.apply_filter).pack(side="left", padx=5)
        self.check_confirmed_var = tk.BooleanVar(value=False); ctk.CTkCheckBox(f2, text="Nur echte SN", variable=self.check_confirmed_var, command=self.apply_filter).pack(side="left", padx=15)
        self.check_visible_var = tk.BooleanVar(value=False); ctk.CTkCheckBox(f2, text="Sichtbar (> 15°)", variable=self.check_visible_var, command=self.apply_filter).pack(side="left", padx=15)

    def add_custom_context_menu_items(self, menu, item):
        menu.add_command(label="📖 Details auf Rochester öffnen", command=lambda: self.open_rochester_link(item))

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item: self.open_rochester_link(item)

    def load_from_cache(self):
        if os.path.exists(_df("cache_supernova.pkl")):
            if (time.time() - os.path.getmtime(_df("cache_supernova.pkl"))) / 3600 < 12: 
                try: self.df = pd.read_pickle(_df("cache_supernova.pkl")); self.update_after_load(); return True
                except: pass
        return False

    def open_rochester_link(self, item):
        try:
            row_values = self.tree.item(item, 'values')
            name_val = None
            for i, col in enumerate(self.tree["columns"]):
                if col.lower() in ["name", "sn", "supernova"]:
                    name_val = str(row_values[i])
                    break
            
            if name_val:
                name_col = next((c for c in self.display_df.columns if c.lower() in ["name", "sn", "supernova"]), None)
                if name_col:
                    rows = self.display_df[self.display_df[name_col].astype(str) == name_val]
                    if not rows.empty and '_rochester_url' in rows.columns:
                        url = rows.iloc[0]['_rochester_url']
                        if url: webbrowser.open(url); return
        except Exception as e: self.log(f"Link-Fehler: {e}")
        messagebox.showwarning("Fehler", "Kein gültiger Link hinterlegt.")

    def load_data_thread(self):
        self.refresh_btn.configure(state="disabled"); self.progress_bar.set(0.0)
        threading.Thread(target=self.fetch_data, daemon=True).start()

    def fetch_data(self):
        url = "https://www.rochesterastronomy.org/snimages/snactive.html" if self.source_var.get() == "Active Supernovae" else "https://www.rochesterastronomy.org/snimages/sndate.html"
        try:
            self.log(f"Schritt 1: Lade Daten von RochesterAstronomy ({self.source_var.get()})...")
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            self.log("Schritt 2: Suche und analysiere Datentabelle...")
            target_html = None; link_map = {} 
            for t in soup.find_all('table'):
                headers = [th.text.lower() for th in t.find_all('th')]
                if not headers:
                    first_row = t.find('tr')
                    if first_row: headers = [td.text.lower() for td in first_row.find_all('td')]
                if "date" in " ".join(headers) or "sn" in " ".join(headers):
                    target_html = str(t)
                    for a in t.find_all('a', href=True):
                        txt = a.get_text(strip=True)
                        if txt: link_map[txt] = urllib.parse.urljoin(url, a['href'])
                    break

            if not target_html: 
                self.after(0, lambda: self.refresh_btn.configure(state="normal"))
                return

            df = pd.read_html(StringIO(target_html))[0]
            if str(df.columns[0]) == '0': df.columns = df.iloc[0]; df = df[1:].reset_index(drop=True)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.drop(columns=[c for c in df.columns if "jd" in c.lower()]).fillna("")
            self.df = df
            
            self.log(f"Schritt 3: Formatiere {len(self.df)} Einträge und bereite Filter vor...")
            name_col = next((c for c in self.df.columns if c.lower() in ["name", "sn", "supernova"]), None)
            if name_col:
                link_map_clean = {k.strip().lower(): v for k, v in link_map.items()}
                self.df['_rochester_url'] = self.df[name_col].apply(lambda x: link_map_clean.get(str(x).strip().lower(), ""))
                self.df[name_col] = self.df[name_col].apply(lambda x: f"🔗 {x}" if str(x).strip().lower() in link_map_clean else x)

            date_cols = [c for c in self.df.columns if "date" in c.lower() or "observe" in c.lower()]
            for col in date_cols:
                def force_german_date(val):
                    v = str(val).strip()
                    if not v or v.lower() in ['nan', 'none', '']: return ""
                    v = v.replace('/', '').replace('-', '').replace('.', '').split(' ')[0]
                    if len(v) >= 8 and v[:4].isdigit(): return f"{v[6:8]}.{v[4:6]}.{v[:4]}"
                    return v
                self.df[col] = self.df[col].apply(force_german_date)
                
            if date_cols:
                d_col = next((c for c in date_cols if "first" in c.lower() or "discover" in c.lower()), date_cols[0])
                self.df['_dt_internal'] = pd.to_datetime(self.df[d_col], format="%d.%m.%Y", errors='coerce')
            else: self.df['_dt_internal'] = pd.NaT 
            
            mag_col = next((c for c in self.df.columns if "mag" in c.lower()), None)
            self.df['_mag_internal'] = pd.to_numeric(self.df[mag_col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce') if mag_col else float('nan')

            dec_col = next((c for c in self.df.columns if "dec" in c.lower()), None)
            if dec_col:
                def parse_dec(s):
                    try:
                        s = str(s).strip()
                        if not s: return float('nan')
                        sign = -1 if s.startswith('-') else 1
                        p = s.replace('+', '').replace('-', '').split(':')
                        if len(p) >= 2: return sign * (float(p[0]) + float(p[1])/60.0 + (float(p[2]) if len(p)>2 else 0)/3600.0)
                    except: pass
                    return float('nan')
                self.df['_dec_internal'] = self.df[dec_col].apply(parse_dec)

            self.log("Schritt 4: Speichere lokalen Cache...")
            try: self.df.to_pickle(_df("cache_supernova.pkl"))
            except: pass

            self.after(0, lambda: self.progress_bar.set(1.0))
            self.log("Datenabruf erfolgreich abgeschlossen!")
            self.after(0, self.update_after_load)
            
        except Exception as e:
            self.log(f"KRITISCHER FEHLER: {e}")
            self.after(0, lambda: self.progress_bar.set(0.0))
            self.after(0, lambda: self.refresh_btn.configure(state="normal"))

    def update_after_load(self):
        self.refresh_btn.configure(state="normal")
        cols = [c for c in self.df.columns if not c.startswith("_")]
        d_col = next((c for c in cols if "date" in c.lower()), None)
        if d_col: self.current_sort_col.set(d_col); self.sort_ascending.set(False)
        elif cols: self.current_sort_col.set(cols[0])
        self.apply_filter()

    def apply_filter(self):
        if self.df.empty: return
        t_df = self.df.copy()

        if self.check_date_var.get() and '_dt_internal' in t_df.columns:
            try: t_df = t_df[t_df['_dt_internal'] >= (datetime.datetime.now() - datetime.timedelta(weeks=float(self.weeks_var.get())))]
            except: pass

        if self.check_mag_var.get() and '_mag_internal' in t_df.columns:
            try: t_df = t_df[t_df['_mag_internal'] <= float(self.mag_limit_var.get())]
            except: pass

        if self.check_host_var.get():
            host_col = next((c for c in t_df.columns if "host" in c.lower()), None)
            if host_col: t_df = t_df[~t_df[host_col].astype(str).str.lower().isin(["none", "anonymous", "", "unknown", "nan"])]

        if self.check_confirmed_var.get():
            name_col = next((c for c in t_df.columns if c.lower() in ["name", "sn", "supernova"]), None)
            if name_col: t_df = t_df[~t_df[name_col].astype(str).str.replace('🔗 ', '').str.startswith('AT')]

        if self.check_visible_var.get() and '_dec_internal' in t_df.columns:
            try:
                lat = float(utils.load_config().get("default_lat", 51.16))
                t_df = t_df[(90.0 - (lat - t_df['_dec_internal']).abs()) >= 15.0]
            except: pass

        search = self.search_var.get().lower()
        if search: t_df = t_df[t_df.apply(lambda row: row.astype(str).str.lower().str.contains(search).any(), axis=1)]

        sort_col = self.current_sort_col.get(); actual_sort_col = sort_col
        if "mag" in sort_col.lower() and '_mag_internal' in t_df.columns: actual_sort_col = "_mag_internal"
        if "date" in sort_col.lower() and '_dt_internal' in t_df.columns: actual_sort_col = "_dt_internal"
        if actual_sort_col in t_df.columns: t_df = t_df.sort_values(by=actual_sort_col, ascending=self.sort_ascending.get(), na_position='last')

        self.display_df = t_df
        self.status_label.configure(text=f"{len(t_df)} Objekte"); self.populate_table(self.display_df)

    def populate_table(self, df):
        self.tree.delete(*self.tree.get_children())
        cols = [c for c in df.columns if not c.startswith("_")]; self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by_header(c))
            self.tree.column(col, width=120, anchor="w")
        for _, row in df[cols].iterrows(): self.tree.insert("", "end", values=list(row))

    def sort_by_header(self, col):
        if self.current_sort_col.get() == col: self.sort_ascending.set(not self.sort_ascending.get())
        else:
            self.current_sort_col.set(col)
            if "date" in col.lower(): self.sort_ascending.set(False)
            else: self.sort_ascending.set(True)
        self.apply_filter()

    def show_type_legend(self):
        if hasattr(self, 'legend_win') and self.legend_win.winfo_exists(): self.legend_win.focus(); return
        self.legend_win = ctk.CTkToplevel(self)
        self.legend_win.title("Legende: Astronomische Typen"); self.legend_win.geometry("550x500"); self.legend_win.attributes("-topmost", True)
        tb = ctk.CTkTextbox(self.legend_win, wrap="word", font=("Arial", 13)); tb.pack(fill="both", expand=True, padx=15, pady=15)
        tb.insert("0.0", "🌟 ECHTE SUPERNOVAE\n• Ia: Thermonuklear (Weißer Zwerg)\n• II: Kernkollaps\n\n🔥 AUSBRÜCHE\n• Nova: Oberflächen-Explosion\n• CV: Flackern\n• LRN: Stern-Kollision\n\n❓ UNBEKANNT\n• unk (AT): Lichtblitz gefunden, Spektrum fehlt.")
        tb.configure(state="disabled")

    def run_automation_workflow(self, item):
        cfg = utils.load_config()
        astap = cfg.get("astap_path", ""); aladin = cfg.get("aladin_path", "")
        if not os.path.exists(astap) or not os.path.exists(aladin):
            messagebox.showerror("Fehler", "Bitte setze ASTAP/Aladin Pfade in den globalen Einstellungen!")
            return
        coords = self.get_coords_from_item(item)
        if not coords: return
        r_vals = self.tree.item(item, 'values'); n="Supernova"; m=""
        for i, c in enumerate(self.tree["columns"]):
            if c.lower() in ["name", "sn", "supernova"]: n = str(r_vals[i]).replace("🔗 ", "").strip()
            elif "mag" in c.lower(): m = str(r_vals[i]).strip()
        lbl = f"{n} (Mag: {m})" if m else n

        fp = filedialog.askopenfilename(title="FITS auswählen", filetypes=[("FITS files", "*.fits;*.fit;*.fts")])
        if not fp: return 
        threading.Thread(target=self._auto_task, args=(fp, coords, astap, aladin, lbl), daemon=True).start()

    def _auto_task(self, fp, coords, astap, aladin, lbl):
        self.after(0, lambda: self.show_automation_log("Löse Bild..."))
        try:
            subprocess.run([astap, "-f", fp, "-update", "-r", "180"], capture_output=True, text=True, timeout=120)
            base, ext = os.path.splitext(fp); ini = base + ".ini"; solved = False
            if os.path.exists(ini):
                with open(ini, "r", errors="ignore") as f:
                    txt = f.read()
                    self.after(0, lambda: self.update_automation_log(txt))
                    if "PLTSOLVD= T" in txt or "PLTSOLVD=T" in txt: solved = True
            if not solved: self.after(0, lambda: self.update_automation_log("FEHLER: Konnte nicht gelöst werden.")); return
            
            script = _df("temp_aladin_macro_sn.ajs")
            p_load = fp.replace('\\', '/') if ext.lower() in [".fits", ".fit"] else (fp.replace('\\', '/') if not os.path.exists(base+".wcs") else fp.replace('\\', '/'))
            
            with open(script, "w") as f: f.write(f'reset\n{coords}\nDSS2\nload "{p_load}"\ndraw red circle {coords} 0.3m\ndraw red string {coords} " <--- {lbl}"')
            subprocess.Popen([aladin, "-exec", f'"{script}"'])
        except Exception as e: self.after(0, lambda: self.update_automation_log(f"FEHLER:\n{e}"))

# ==============================================================================
# HAUPTFRAME DES TRACKERS (Tab-Ansicht)
# ==============================================================================
class AstroTrackerFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)
        
        tab_comets = self.tabview.add("☄ Kometen")
        tab_sn = self.tabview.add("💥 Supernovae")
        tab_ast = self.tabview.add("🪨 Kleinplaneten")
        
        self.mod_comets = CometTrackerModul(tab_comets)
        self.mod_comets.pack(fill="both", expand=True)
        
        self.mod_sn = SupernovaModul(tab_sn)
        self.mod_sn.pack(fill="both", expand=True)
        
        self.mod_ast = AsteroidTrackerModul(tab_ast)
        self.mod_ast.pack(fill="both", expand=True)