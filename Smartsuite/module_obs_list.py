# ==============================================================================
# MODULE_OBS_LIST.PY - Beobachtungsliste (Vereint Kalender, Archiv & Wetter)
# ==============================================================================
import sys
# --- ABSOLUTER FIX FÜR PYINSTALLER .EXE ABSTÜRZE ---
if sys.stdout is None:
    class DummyWriter:
        def write(self, *args, **kwargs): pass
        def flush(self): pass
    sys.stdout = DummyWriter()
if sys.stderr is None:
    class DummyWriter:
        def write(self, *args, **kwargs): pass
        def flush(self): pass
    sys.stderr = DummyWriter()

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import json
import os
import webbrowser
import math
import re
from datetime import datetime, timedelta
import pytz
import threading
import requests
import numpy as np

# --- GRAFIK IMPORTS ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

import warnings
from astropy.utils.exceptions import AstropyWarning
warnings.simplefilter('ignore', category=AstropyWarning)

from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_body, get_sun
import astropy.units as u
import ephem

import smart_utils as utils

OBS_FILE = "smartsuite_obslist.json"

def normalize_string(s):
    return s.lower().replace(" ", "").replace("_", "").replace("-", "")

# --- NEU: Globale Kompass-Umrechnung ---
def az_to_compass(az):
    dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((az + 11.25) / 22.5) % 16
    return dirs[idx]

def load_list():
    if os.path.exists(OBS_FILE):
        try:
            with open(OBS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return []

def save_list(data):
    with open(OBS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def add_event(iso_date, display_date, time_str, title, desc, icon):
    data = load_list()
    for item in data:
        if item.get("iso_date") == iso_date and item.get("title") == title: return False
    data.append({
        "id": str(datetime.now().timestamp()), "iso_date": iso_date, 
        "display_date": display_date, "time": time_str, "title": title, "desc": desc, "icon": icon
    })
    data.sort(key=lambda x: x.get("iso_date", ""))
    save_list(data)
    return True

# --- FIX: Kugelsicheres Löschen (Ignoriert alte KeyErrors!) ---
def remove_event(event_id, fallback_title=None, fallback_date=None):
    data = load_list()
    new_data = []
    for x in data:
        x_id = x.get("id")
        if x_id and event_id and str(x_id) == str(event_id):
            continue
        if not event_id and fallback_title and fallback_date:
            if x.get("title") == fallback_title and x.get("iso_date") == fallback_date:
                continue
        new_data.append(x)
    save_list(new_data)
# --------------------------------------------------------------

# --- NEU: ZENTRALE PFAD-VERWALTUNG ---
def get_list_paths():
    cfg = utils.load_config()
    target_dir = cfg.get("custom_tools_path", "")
    
    notes_path = os.path.join(target_dir, "user_notes.json") if target_dir else "user_notes.json"
    cache_path = os.path.join(target_dir, "coordinate_cache.json") if target_dir else "coordinate_cache.json"
    cat_path = os.path.join(target_dir, "catalogs.json") if target_dir else "catalogs.json"
    
    return notes_path, cache_path, cat_path

def load_aae_targets_rich():
    notes_path, cache_path, cat_path = get_list_paths()
    
    # NEU: Wenn die Datei gar nicht existiert, brechen wir ab und geben None zurück!
    if not os.path.exists(notes_path):
        return None
        
    notes = {}
    try:
        with open(notes_path, "r", encoding="utf-8") as f: notes = json.load(f)
    except: pass
        
    if not notes: return []
    
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f: cache = json.load(f)
        except: pass

    common_names = {}
    caldwell_map = {}
    if os.path.exists(cat_path):
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                common_names = cat_data.get("common_names", {})
                caldwell_map = cat_data.get("caldwell", {})
        except: pass

    unique_targets = {}
    cache_needs_save = False

    for key, note_data in notes.items():
        if not note_data.get("todo"): continue
        clean_key = normalize_string(key)
        resolved_key = clean_key
        for c_name, cat_id in common_names.items():
            if normalize_string(c_name) == clean_key:
                resolved_key = normalize_string(cat_id)
                break
                
        c_match = re.match(r'^c(\d+)$', resolved_key)
        if c_match:
            c_num = c_match.group(1)
            if c_num in caldwell_map:
                resolved_key = normalize_string(caldwell_map[c_num])
                
        m = re.search(r'((?:ngc|m|ic|c)\d+)', resolved_key)
        base_id = m.group(1) if m else resolved_key
        search_keys = [clean_key, resolved_key, base_id]
        cache_entry = None
        for sk in search_keys:
            if sk in cache:
                cache_entry = cache[sk]; break
        if not cache_entry:
            for c_k, c_v in cache.items():
                if any(sk.startswith(c_k) or c_k.startswith(sk) for sk in search_keys):
                    cache_entry = c_v; break

        if not cache_entry:
            lookup_name = key
            if base_id.startswith("ngc"): lookup_name = f"NGC {base_id[3:]}"
            elif base_id.startswith("m"): lookup_name = f"M {base_id[1:]}"
            elif base_id.startswith("ic"): lookup_name = f"IC {base_id[2:]}"
            try:
                coord = SkyCoord.from_name(lookup_name)
                cache_entry = {
                    "ra": coord.ra.deg, "dec": coord.dec.deg,
                    "coords_str": f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                }
                cache[resolved_key] = cache_entry
                cache_needs_save = True
            except: pass

        if cache_entry:
            ra = cache_entry["ra"]; dec = cache_entry["dec"]
            hash_key = f"pos_{round(ra, 2)}_{round(dec, 2)}"
        else:
            ra = None; dec = None
            hash_key = f"id_{base_id}"

        if note_data.get("display_name"):
            display_name = note_data["display_name"]
        else:
            display_name = key.upper()
            if base_id.startswith("ngc"): display_name = f"NGC {base_id[3:]}"
            elif base_id.startswith("m"): display_name = f"M {base_id[1:]}"
            elif base_id.startswith("ic"): display_name = f"IC {base_id[2:]}"
            elif base_id.startswith("c"): display_name = f"C {base_id[1:]}"
            if key.upper() not in display_name and not display_name.startswith(key.upper()):
                display_name += f" ({key.upper()})"

        if hash_key in unique_targets:
            existing_name = unique_targets[hash_key]["name"]
            if key.upper() not in existing_name: unique_targets[hash_key]["name"] += f" / {key.upper()}"
            if note_data.get("note"):
                existing_note = unique_targets[hash_key]["note"]
                if note_data["note"] not in existing_note:
                    separator = " | " if existing_note else ""
                    unique_targets[hash_key]["note"] += f"{separator}{note_data['note']}"
        else:
            unique_targets[hash_key] = {
                "name": display_name, "note": note_data.get("note", ""), "type": note_data.get("type", "Auto"), 
                "ra": ra, "dec": dec, "coords_str": cache_entry["coords_str"] if cache_entry else "Keine Koordinaten gefunden", "score": -1,
                "raw_key": key 
            }

    if cache_needs_save:
        try:
            with open(cache_path, "w", encoding="utf-8") as f: json.dump(cache, f, indent=4)
        except: pass

    cfg = utils.load_config()
    lat = float(cfg.get("default_lat", 51.16))
    lon = float(cfg.get("default_lon", 10.45))
    loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
    now = Time.now()
    local_tz = pytz.timezone('Europe/Berlin')
    
    try:
        moon = get_body("moon", now)
        sun = get_sun(now)
        moon_phase = (1 - math.cos(math.radians(sun.separation(moon).deg))) / 2 * 100
        lst = now.sidereal_time('apparent', longitude=loc.lon).hour
        
        t_arr = now + np.linspace(0, 24, 48) * u.hour
        plot_times = [dt.replace(tzinfo=pytz.utc).astimezone(local_tz) for dt in t_arr.datetime]
        
        for tgt in unique_targets.values():
            if tgt["ra"] is not None and tgt["dec"] is not None:
                tgt_coord = SkyCoord(ra=tgt["ra"]*u.deg, dec=tgt["dec"]*u.deg)
                tgt["moon_sep"] = tgt_coord.separation(moon).deg
                tgt["moon_phase"] = moon_phase
                ra_hours = tgt["ra"] / 15.0
                time_to_transit = (ra_hours - lst) % 24
                transit_dt = datetime.now() + timedelta(hours=time_to_transit)
                tgt["transit_time"] = transit_dt.strftime("%H:%M")
                tgt["max_alt"] = 90 - abs(lat - tgt["dec"])
                
                altaz = tgt_coord.transform_to(AltAz(obstime=now, location=loc))
                tgt["current_alt"] = altaz.alt.deg
                
                altaz_arr = tgt_coord.transform_to(AltAz(obstime=t_arr, location=loc))
                tgt["plot_alts"] = list(altaz_arr.alt.deg)
                tgt["plot_times"] = plot_times
                
                alt_score = max(0, min(50, (tgt["max_alt"] - 15) / 65 * 50))
                dist_factor = max(0, (90 - tgt["moon_sep"]) / 90)
                moon_score = 50 - ((tgt["moon_phase"] / 100) * dist_factor * 50)
                tgt["score"] = int(round(alt_score + moon_score))
            
    except Exception as e:
        pass

    final_list = list(unique_targets.values())
    final_list.sort(key=lambda x: x.get("score", -1), reverse=True) 
    return final_list


class ObsListFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._weather_forecasts = None
        self._weather_error = False
        
        self.last_events = []
        self.last_targets = []
        self._temp_search_result = None
        
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(top_frame, text="📋 Kombinierte Beobachtungsliste", font=("Arial", 18, "bold")).pack(side="left", padx=10, pady=10)
        
        btn_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        btn_frame.pack(side="right")
        
        self.btn_mobile = ctk.CTkButton(btn_frame, text="📱 Handy-App Sync", fg_color="#e67e22", hover_color="#d35400", command=self.export_mobile_app)
        self.btn_mobile.pack(side="left", padx=5)
        
        self.btn_ics = ctk.CTkButton(btn_frame, text="📅 .ics", width=60, fg_color="#2980b9", command=self.export_ics)
        self.btn_ics.pack(side="left", padx=5)
        
        self.btn_pdf = ctk.CTkButton(btn_frame, text="🖨️ PDF", width=60, fg_color="#8e44ad", command=self.export_pdf_html)
        self.btn_pdf.pack(side="left", padx=5)
        
        self.weather_container = ctk.CTkFrame(self, fg_color="#141414", border_width=1, border_color="#34495e", corner_radius=8, cursor="hand2")
        self.weather_container.pack(fill="x", padx=20, pady=(0, 5))
        self.weather_content = ctk.CTkFrame(self.weather_container, fg_color="transparent", cursor="hand2")
        self.weather_content.pack(pady=10)
        self.weather_lbl = ctk.CTkLabel(self.weather_content, text="Lade Astro-Wetter (Open-Meteo)...", font=("Arial", 12), text_color="gray", cursor="hand2")
        self.weather_lbl.pack()
        self.weather_lat = 51.16
        self.weather_lon = 10.45
        
        self.weather_container.bind("<Button-1>", self.open_weather_website)
        self.weather_content.bind("<Button-1>", self.open_weather_website)
        self.weather_lbl.bind("<Button-1>", self.open_weather_website)
        
        self.load_weather()

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=5)
        
        self.tab_tonight = self.tabview.add("✨ Heute Nacht")
        self.tab_events = self.tabview.add("📅 Himmelsereignisse (Termine)")
        self.tab_targets = self.tabview.add("🔭 Deep-Sky Ziele (Live-Daten)")
        
        self.scroll_tonight = ctk.CTkScrollableFrame(self.tab_tonight, fg_color="transparent")
        self.scroll_tonight.pack(fill="both", expand=True)
        self.scroll_events = ctk.CTkScrollableFrame(self.tab_events, fg_color="transparent")
        self.scroll_events.pack(fill="both", expand=True)
        
        self.target_input_frame = ctk.CTkFrame(self.tab_targets, fg_color="#1a1a1a", border_width=1, border_color="#3498db")
        self.target_input_frame.pack(fill="x", padx=5, pady=(5, 10))
        
        input_row = ctk.CTkFrame(self.target_input_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=5, pady=(10, 0))
        
        ctk.CTkLabel(input_row, text="Ziele manuell hinzufügen:", font=("Arial", 13, "bold"), text_color="#3498db").pack(side="left", padx=(5, 10))
        
        self.target_name_entry = ctk.CTkEntry(input_row, placeholder_text="Name (z.B. M 31)", width=150)
        self.target_name_entry.pack(side="left", padx=(0, 10))
        
        self.btn_search_target = ctk.CTkButton(input_row, text="🔍 Suchen", width=80, fg_color="#2980b9", hover_color="#3498db", command=self.search_manual_target)
        self.btn_search_target.pack(side="left", padx=(0, 10))
        
        self.btn_stellarium_get = ctk.CTkButton(input_row, text="🌌 Aus Stellarium übernehmen", width=180, fg_color="#8e44ad", hover_color="#9b59b6", command=self.get_from_stellarium)
        self.btn_stellarium_get.pack(side="left", padx=(0, 10))
        
        self.target_note_entry = ctk.CTkEntry(input_row, placeholder_text="Notiz (Optional)")
        self.target_note_entry.pack(side="left", padx=(0, 10), expand=True, fill="x")
        
        self.btn_add_target = ctk.CTkButton(input_row, text="➕ Zur Liste", width=120, fg_color="#27ae60", hover_color="#2ecc71", command=self.add_manual_target, state="disabled")
        self.btn_add_target.pack(side="right", padx=5)
        
        preview_row = ctk.CTkFrame(self.target_input_frame, fg_color="transparent")
        preview_row.pack(fill="x", padx=10, pady=(2, 10))
        
        self.preview_lbl = ctk.CTkLabel(preview_row, text="", font=("Consolas", 12), text_color="gray", height=20)
        self.preview_lbl.pack(side="left", padx=(195, 0)) 
        
        self.target_name_entry.bind("<KeyRelease>", self._on_name_change)
        self.target_name_entry.bind("<Return>", lambda e: self.search_manual_target())
        self.target_note_entry.bind("<Return>", lambda e: self.add_manual_target() if self.btn_add_target.cget("state") == "normal" else None)

        self.scroll_targets = ctk.CTkScrollableFrame(self.tab_targets, fg_color="transparent")
        self.scroll_targets.pack(fill="both", expand=True)
        
        self.after(100, self.refresh_ui)

    def _on_name_change(self, event=None):
        self.btn_add_target.configure(state="disabled")
        self.preview_lbl.configure(text="", text_color="gray")
        self._temp_search_result = None

    def search_manual_target(self):
        name = self.target_name_entry.get().strip()
        if not name: return
        self.btn_search_target.configure(state="disabled", text="⏳...")
        self.preview_lbl.configure(text="Sucht in der Simbad Datenbank...", text_color="yellow")
        self.update_idletasks()
        
        def worker():
            try:
                coord = SkyCoord.from_name(name)
                ra_deg = coord.ra.deg; dec_deg = coord.dec.deg
                coords_str = f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                self._temp_search_result = {"name": name, "ra": ra_deg, "dec": dec_deg, "coords_str": coords_str}
                self.after(0, self._search_success)
            except Exception as e:
                self.after(0, lambda err=str(e): self._search_failed(err))
                
        threading.Thread(target=worker, daemon=True).start()

    def _search_success(self):
        self.btn_search_target.configure(state="normal", text="🔍 Suchen")
        self.btn_add_target.configure(state="normal")
        c_str = self._temp_search_result["coords_str"]
        self.preview_lbl.configure(text=f"✅ Gefunden: {c_str}", text_color="#2ecc71")

    def _search_failed(self, err_msg):
        self.btn_search_target.configure(state="normal", text="🔍 Suchen")
        self.btn_add_target.configure(state="disabled")
        self._temp_search_result = None
        self.preview_lbl.configure(text="❌ Objekt nicht gefunden. Bitte Schreibweise prüfen.", text_color="#e74c3c")
        
    def get_from_stellarium(self):
        self.btn_stellarium_get.configure(state="disabled", text="⏳...")
        self.update_idletasks()
        
        def worker():
            try:
                url = "http://localhost:8090/api/objects/info?format=json"
                r = requests.get(url, timeout=2)
                
                if r.status_code == 200:
                    data = r.json()
                    name = data.get("name", data.get("localized-name", ""))
                    if not name:
                        name = "Stellarium Ziel"
                        
                    ra_deg = data.get("raJ2000", data.get("ra", None))
                    dec_deg = data.get("decJ2000", data.get("dec", None))
                    
                    if ra_deg is not None and dec_deg is not None:
                        self.after(0, lambda n=name, r=ra_deg, d=dec_deg: self._apply_stellarium_direct(n, r, d))
                    elif name != "Stellarium Ziel":
                        self.after(0, lambda n=name: self._apply_stellarium_target(n))
                    else:
                        self.after(0, lambda: messagebox.showinfo("Stellarium", "Es ist gerade kein Objekt in Stellarium markiert!"))
                else:
                    self.after(0, lambda: messagebox.showwarning("Stellarium", "Konnte keine Daten von Stellarium abrufen."))
            except Exception as e:
                self.after(0, lambda: messagebox.showwarning("Stellarium", "Keine Verbindung zu Stellarium.\n\nIst Stellarium geöffnet und das 'Remote Control' Plugin (Port 8090) aktiv?"))
            finally:
                self.after(0, lambda: self.btn_stellarium_get.configure(state="normal", text="🌌 Aus Stellarium übernehmen"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_stellarium_direct(self, name, ra, dec):
        self.target_name_entry.delete(0, "end")
        self.target_name_entry.insert(0, name)
        self.target_note_entry.delete(0, "end")
        self.target_note_entry.insert(0, "Aus Stellarium importiert")
        
        try:
            coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
            coords_str = f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
            
            self._temp_search_result = {
                "name": name,
                "ra": ra,
                "dec": dec,
                "coords_str": coords_str
            }
            
            self.btn_search_target.configure(state="normal", text="🔍 Suchen")
            self.btn_add_target.configure(state="normal")
            
            self.preview_lbl.configure(text=f"🌌 Importiert: {coords_str}", text_color="#9b59b6")
        except Exception as e:
            self._search_failed(str(e))

    def _apply_stellarium_target(self, name):
        self.target_name_entry.delete(0, "end")
        self.target_name_entry.insert(0, name)
        self.target_note_entry.delete(0, "end")
        self.target_note_entry.insert(0, "Aus Stellarium importiert")
        self.search_manual_target()

    def send_to_stellarium(self, target_name, ra_deg=None, dec_deg=None):
        def worker():
            try:
                url_focus = "http://localhost:8090/api/main/focus"
                r = requests.post(url_focus, params={"target": target_name, "sync": "true"}, timeout=2)
                
                if r.status_code == 200 and r.text.strip().lower() == "true":
                    return 
                    
                if ra_deg is not None and dec_deg is not None:
                    requests.post(url_focus, params={"target": ""}, timeout=1)
                    
                    url_view = "http://localhost:8090/api/main/view"
                    
                    ra_rad = math.radians(ra_deg)
                    dec_rad = math.radians(dec_deg)
                    
                    x = math.cos(dec_rad) * math.cos(ra_rad)
                    y = math.cos(dec_rad) * math.sin(ra_rad)
                    z = math.sin(dec_rad)
                    
                    payload = {"j2000": f"[{x},{y},{z}]"}
                    requests.post(url_view, params=payload, timeout=2)
                    
            except Exception as e:
                self.after(0, lambda: messagebox.showwarning("Stellarium", "Keine Verbindung zu Stellarium auf Port 8090."))

        threading.Thread(target=worker, daemon=True).start()

    def add_manual_target(self):
        if not getattr(self, "_temp_search_result", None): return
        name = self._temp_search_result["name"]
        ra_deg = self._temp_search_result["ra"]
        dec_deg = self._temp_search_result["dec"]
        coords_str = self._temp_search_result["coords_str"]
        note = self.target_note_entry.get().strip()
        
        notes_path, cache_path, _ = get_list_paths()

        cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f: cache = json.load(f)
            except: pass
        
        clean_name = normalize_string(name)
        cache[clean_name] = {"ra": ra_deg, "dec": dec_deg, "coords_str": coords_str}
        try:
            with open(cache_path, "w", encoding="utf-8") as f: json.dump(cache, f, indent=4)
        except: pass

        notes = {}
        if os.path.exists(notes_path):
            try:
                with open(notes_path, "r", encoding="utf-8") as f: notes = json.load(f)
            except: pass
        
        target_key = name
        for k in notes.keys():
            if normalize_string(k) == clean_name:
                target_key = k; break
                
        if target_key not in notes: notes[target_key] = {"todo": True, "note": note, "type": "Manual", "tags": []}
        else:
            notes[target_key]["todo"] = True
            if note:
                if notes[target_key].get("note"): notes[target_key]["note"] += f" | {note}"
                else: notes[target_key]["note"] = note
                    
        try:
            with open(notes_path, "w", encoding="utf-8") as f: json.dump(notes, f, indent=4, ensure_ascii=False)
        except: pass

        self.target_name_entry.delete(0, "end"); self.target_note_entry.delete(0, "end")
        self._on_name_change(); self.refresh_ui()

    def remove_target(self, target_key):
        notes_path, cache_path, _ = get_list_paths()
            
        if os.path.exists(notes_path):
            try:
                with open(notes_path, "r", encoding="utf-8") as f: notes = json.load(f)
                if target_key in notes:
                    notes[target_key]["todo"] = False
                    with open(notes_path, "w", encoding="utf-8") as f: json.dump(notes, f, indent=4, ensure_ascii=False)
                self.refresh_ui()
            except Exception as e: messagebox.showerror("Fehler", f"Konnte Ziel nicht entfernen:\n{e}")
            
    def edit_target_name(self, raw_key, current_name):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Namen bearbeiten")
        dialog.geometry("400x180")
        dialog.attributes("-topmost", True) 
        dialog.grab_set() 
        
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 200
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 90
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="Neuer Name (für Anzeige & Stellarium):", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        
        entry = ctk.CTkEntry(dialog, width=320, font=("Arial", 14))
        entry.pack(pady=5)
        entry.insert(0, current_name)
        entry.focus() 
        
        def save_new_name(event=None):
            new_name = entry.get().strip()
            
            if new_name and new_name != current_name:
                notes_path, cache_path, _ = get_list_paths()
                
                if os.path.exists(notes_path):
                    try:
                        with open(notes_path, "r", encoding="utf-8") as f: 
                            notes = json.load(f)
                            
                        if raw_key in notes:
                            notes[raw_key]["display_name"] = new_name
                            
                            with open(notes_path, "w", encoding="utf-8") as f: 
                                json.dump(notes, f, indent=4, ensure_ascii=False)
                                
                        self.refresh_ui()
                    except Exception as e: 
                        messagebox.showerror("Fehler", f"Konnte Name nicht ändern:\n{e}")
            
            dialog.destroy() 

        entry.bind("<Return>", save_new_name)
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ctk.CTkButton(btn_frame, text="Abbrechen", width=100, fg_color="#c0392b", hover_color="#e74c3c", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Speichern", width=100, fg_color="#27ae60", hover_color="#2ecc71", command=save_new_name).pack(side="right", padx=10)

    def open_weather_website(self, event=None):
        lat_str = f"{abs(self.weather_lat):.2f}N" if self.weather_lat >= 0 else f"{abs(self.weather_lat):.2f}S"
        lon_str = f"{abs(self.weather_lon):.2f}E" if self.weather_lon >= 0 else f"{abs(self.weather_lon):.2f}W"
        url = f"https://www.meteoblue.com/de/wetter/vorhersage/seeing/{lat_str}{lon_str}"
        webbrowser.open(url)

    def open_cloud_radar(self, event=None):
        url = f"https://www.windy.com/?clouds,{self.weather_lat},{self.weather_lon},6"
        webbrowser.open(url)

    def load_weather(self):
        self._weather_forecasts = None
        self._weather_error = False
        
        def fetch():
            try:
                cfg = utils.load_config()
                lat = float(cfg.get("default_lat", 51.16))
                lon = float(cfg.get("default_lon", 10.45))
                self.weather_lat = lat; self.weather_lon = lon
                
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=cloudcover,temperature_2m,dewpoint_2m,windspeed_10m&timezone=Europe%2FBerlin"
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if r.status_code != 200: raise Exception(f"API Error {r.status_code}: {r.text}")
                    
                data = r.json()
                times = data['hourly']['time']
                clouds = data['hourly']['cloudcover']
                temps = data['hourly']['temperature_2m']
                dews = data['hourly']['dewpoint_2m']
                winds = data['hourly']['windspeed_10m']
                
                today = datetime.now().date()
                forecasts = []
                
                for day_offset in range(3):
                    target_date = today + timedelta(days=day_offset)
                    night_clouds = []; night_winds = []; dew_spreads = [] 
                    for t_str, c, temp, dew, w in zip(times, clouds, temps, dews, winds):
                        dt = datetime.fromisoformat(t_str)
                        if (dt.date() == target_date and dt.hour >= 22) or (dt.date() == target_date + timedelta(days=1) and dt.hour <= 4):
                            night_clouds.append(c); night_winds.append(w)
                            if temp is not None and dew is not None: dew_spreads.append(temp - dew)
                            
                    if night_clouds:
                        avg_c = sum(night_clouds) / len(night_clouds)
                        avg_w = sum(night_winds) / len(night_winds)
                        min_spread = min(dew_spreads) if dew_spreads else 5.0
                        
                        observer = ephem.Observer()
                        observer.date = ephem.Date(datetime(target_date.year, target_date.month, target_date.day, 21, 0)) 
                        moon = ephem.Moon()
                        moon.compute(observer)
                        moon_phase = moon.phase
                        
                        score = 100.0
                        score -= avg_c
                        if avg_w > 15: score -= 10
                        if avg_w > 25: score -= 20
                        
                        dew_risk = "OK"
                        if min_spread <= 1.0: score -= 10; dew_risk = "Hoch!"
                        elif min_spread <= 2.5: score -= 5; dew_risk = "Mittel"
                            
                        score -= (moon_phase * 0.25)
                        score = max(0, min(100, int(score)))
                        
                        if score >= 75: color = "#2ecc71"; icon = "✨"
                        elif score >= 40: color = "#f39c12"; icon = "⛅"
                        else: color = "#e74c3c"; icon = "☁️"
                            
                        if moon_phase > 90: moon_icon = "🌕"
                        elif moon_phase > 60: moon_icon = "🌖"
                        elif moon_phase > 40: moon_icon = "🌗"
                        elif moon_phase > 15: moon_icon = "🌘"
                        else: moon_icon = "🌑"
                            
                        day_name = "Heute" if day_offset == 0 else "Morgen" if day_offset == 1 else "Übermorgen"
                        info_str = f"Score: {score} | ☁️{int(avg_c)}% | 💨{int(avg_w)}kmh | 💧{dew_risk} | {moon_icon}{int(moon_phase)}%"
                        forecasts.append({"name": f"{day_name}:", "text": f"{icon} {info_str}", "color": color})
                
                self._weather_forecasts = forecasts
            except Exception as e:
                print(f"Weather fetch error: {e}")
                self._weather_error = True

        threading.Thread(target=fetch, daemon=True).start()
        self._poll_weather()

    def _poll_weather(self):
        if self._weather_forecasts is not None:
            self.render_weather(self._weather_forecasts)
            self.render_tonight_tab() 
        elif self._weather_error:
            self.weather_lbl.configure(text="Astro-Wetter zurzeit nicht erreichbar.", text_color="gray")
            self.render_tonight_tab()
        else:
            self.after(100, self._poll_weather)

    def render_weather(self, forecasts):
        for w in self.weather_content.winfo_children(): w.destroy()
        for idx, fc in enumerate(forecasts):
            f_frame = ctk.CTkFrame(self.weather_content, fg_color="transparent", cursor="hand2")
            f_frame.pack(side="left", expand=True)
            f_frame.bind("<Button-1>", self.open_weather_website)
            l1 = ctk.CTkLabel(f_frame, text=fc["name"], font=("Arial", 12, "bold"), text_color="#ecf0f1", cursor="hand2")
            l1.pack(side="left", padx=(0, 5))
            l1.bind("<Button-1>", self.open_weather_website)
            l2 = ctk.CTkLabel(f_frame, text=fc["text"], font=("Arial", 12, "bold"), text_color=fc["color"], cursor="hand2")
            l2.pack(side="left")
            l2.bind("<Button-1>", self.open_weather_website)
            if idx < len(forecasts) - 1:
                sep = ctk.CTkLabel(self.weather_content, text="  |  ", text_color="#7f8c8d", cursor="hand2")
                sep.pack(side="left", padx=5)
                sep.bind("<Button-1>", self.open_weather_website)
                
        links_frame = ctk.CTkFrame(self.weather_content, fg_color="transparent")
        links_frame.pack(side="left", padx=(15, 0))
        hint_mb = ctk.CTkLabel(links_frame, text="🌐 Meteoblue Seeing", font=("Arial", 11, "underline"), text_color="#3498db", cursor="hand2")
        hint_mb.pack(side="left", padx=(0, 10))
        hint_mb.bind("<Button-1>", self.open_weather_website)
        hint_radar = ctk.CTkLabel(links_frame, text="📡 Wolkenradar (Windy)", font=("Arial", 11, "underline"), text_color="#3498db", cursor="hand2")
        hint_radar.pack(side="left")
        hint_radar.bind("<Button-1>", self.open_cloud_radar)

    def generate_night_plan(self, targets):
        cfg = utils.load_config()
        lat = float(cfg.get("default_lat", 51.16))
        lon = float(cfg.get("default_lon", 10.45))
        loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
        local_tz = pytz.timezone('Europe/Berlin')

        now = datetime.now(local_tz)
        if now.hour >= 17 or now.hour < 6:
            start_dt = now
        else:
            start_dt = now.replace(hour=18, minute=0, second=0, microsecond=0)

        times_local = [start_dt + timedelta(minutes=15*i) for i in range(60)]
        astro_times = Time(times_local)
        sun_altaz = get_sun(astro_times).transform_to(AltAz(obstime=astro_times, location=loc))

        dark_indices = [i for i, alt in enumerate(sun_altaz.alt.deg) if alt < -6]
        if not dark_indices: return {"Süd": [], "Nord": []}

        first_dark = times_local[dark_indices[0]]
        last_dark = times_local[dark_indices[-1]]

        plan_start = max(first_dark, now)
        mins = 15 * math.ceil(plan_start.minute / 15)
        plan_start = plan_start.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=mins)

        if plan_start >= last_dark: return {"Süd": [], "Nord": []}

        valid_targets = [t for t in targets if t.get('ra') is not None]

        def build_plan_for_hemisphere(is_south):
            plan = []
            current_time = plan_start
            scheduled_counts = {t['name']: 0 for t in valid_targets}

            while current_time < last_dark:
                time_left = last_dark - current_time
                if time_left < timedelta(minutes=20): break 
                
                actual_duration = min(timedelta(hours=1, minutes=30), time_left)
                mid_time = current_time + (actual_duration / 2)
                mid_astro = Time(mid_time)

                best_target = None
                best_score = -9999

                for t in valid_targets:
                    coord = SkyCoord(ra=t['ra']*u.deg, dec=t['dec']*u.deg)
                    altaz = coord.transform_to(AltAz(obstime=mid_astro, location=loc))
                    alt = altaz.alt.deg
                    az = altaz.az.deg

                    target_is_south = (90 <= az <= 270)
                    if is_south and not target_is_south: continue
                    if not is_south and target_is_south: continue

                    if alt > 5:
                        current_score = t.get('score', 0)
                        if alt >= 20: current_score += (alt * 2) 
                        else: current_score -= ((20 - alt) * 5) 
                        current_score -= (scheduled_counts[t['name']] * 150)

                        if current_score > best_score:
                            best_score = current_score
                            best_target = t
                            best_target['_temp_alt'] = alt
                            best_target['_temp_az'] = az 

                if best_target:
                    plan.append({
                        "start": current_time,
                        "end": current_time + actual_duration,
                        "target": best_target,
                        "alt": best_target['_temp_alt'],
                        "az": best_target['_temp_az']
                    })
                    scheduled_counts[best_target['name']] += 1
                    current_time += actual_duration
                else:
                    current_time += timedelta(minutes=30)
            return plan

        return {
            "Süd": build_plan_for_hemisphere(is_south=True),
            "Nord": build_plan_for_hemisphere(is_south=False)
        }
    
    def render_tonight_tab(self):
        for widget in self.scroll_tonight.winfo_children(): widget.destroy()
        
        ctk.CTkLabel(self.scroll_tonight, text=f"✨ Planung für {datetime.now().strftime('%d.%m.%Y')}", font=("Arial", 22, "bold"), text_color="#f1c40f").pack(pady=(10, 20))
        
        w_frame = ctk.CTkFrame(self.scroll_tonight, fg_color="#1a1a1a", border_width=1, border_color="#34495e", corner_radius=8)
        w_frame.pack(fill="x", padx=10, pady=5)
        w_str = "Wetter wird geladen..."
        if self._weather_forecasts: w_str = self._weather_forecasts[0]['text']
        ctk.CTkLabel(w_frame, text="Bedingungen Heute", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", padx=10, pady=(10,0))
        ctk.CTkLabel(w_frame, text=w_str, font=("Arial", 14)).pack(anchor="w", padx=10, pady=(5,10))
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        events_today = [e for e in self.last_events if e['iso_date'] == today_str]
        
        if events_today:
            e_frame = ctk.CTkFrame(self.scroll_tonight, fg_color="#1a1a1a", border_width=1, border_color="#e67e22", corner_radius=8)
            e_frame.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(e_frame, text="Besondere Ereignisse Heute", font=("Arial", 14, "bold"), text_color="#e67e22").pack(anchor="w", padx=10, pady=(10,0))
            for e in events_today:
                ctk.CTkLabel(e_frame, text=f"{e.get('icon','')} {e['title']} - {e['time']}\n{e['desc']}", justify="left").pack(anchor="w", padx=10, pady=(5,10))
                
        night_plans = {"Süd": [], "Nord": []}
        if self.last_targets:
            night_plans = self.generate_night_plan(self.last_targets)
            
        t_frame = ctk.CTkFrame(self.scroll_tonight, fg_color="#1a1a1a", border_width=1, border_color="#2ecc71", corner_radius=8)
        t_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(t_frame, text="Teleskop-Plan für Heute Nacht (je 1,5 Std)", font=("Arial", 14, "bold"), text_color="#2ecc71").pack(anchor="w", padx=10, pady=(10,0))
        
        if not night_plans.get("Süd") and not night_plans.get("Nord"):
            ctk.CTkLabel(t_frame, text="Keine gut sichtbaren Ziele auf deiner Liste oder Wetter zu schlecht/zu hell.", text_color="gray").pack(anchor="w", padx=10, pady=(5,10))
        else:
            for hemi in ["Süd", "Nord"]:
                p_list = night_plans.get(hemi, [])
                if not p_list: continue
                
                ctk.CTkLabel(t_frame, text=f"Blickrichtung {hemi}:", font=("Arial", 13, "bold"), text_color="#3498db").pack(anchor="w", padx=15, pady=(10,2))
                
                for idx, block in enumerate(p_list):
                    s_str = block['start'].strftime('%H:%M')
                    e_str = block['end'].strftime('%H:%M')
                    t_name = block['target']['name']
                    alt = int(block['alt'])
                    comp = az_to_compass(block['az']) 
                    
                    bg_color = "#242424" if idx % 2 == 0 else "#2a2a2a"
                    row_frame = ctk.CTkFrame(t_frame, fg_color=bg_color, corner_radius=4)
                    row_frame.pack(fill="x", padx=15, pady=4)
                    
                    time_lbl = ctk.CTkLabel(row_frame, text=f"🕒 {s_str} - {e_str}", font=("Consolas", 13, "bold"), text_color="#f39c12", width=130, anchor="w")
                    time_lbl.pack(side="left", padx=10, pady=5)
                    
                    name_lbl = ctk.CTkLabel(row_frame, text=t_name, font=("Arial", 14, "bold"), text_color="#ecf0f1")
                    name_lbl.pack(side="left", padx=10, pady=5)
                    
                    alt_lbl = ctk.CTkLabel(row_frame, text=f"(Ø Höhe: {alt}°, Richtung: {comp})", font=("Arial", 12), text_color="#7f8c8d")
                    alt_lbl.pack(side="left", padx=5, pady=5)
                
        btn_ai = ctk.CTkButton(self.scroll_tonight, text="🤖 KI-Berater: Tagespläne auswerten (Prompt kopieren)", height=40, font=("Arial", 14, "bold"), fg_color="#8e44ad", hover_color="#9b59b6")
        btn_ai.configure(command=lambda: self.generate_ai_prompt(w_str, events_today, night_plans))
        btn_ai.pack(pady=20, padx=10, fill="x")

    def generate_ai_prompt(self, weather_str, events_today, night_plans):
        cfg = utils.load_config()
        lat = cfg.get("default_lat", "51.16")
        
        day_of_year = datetime.now().timetuple().tm_yday
        focus_categories = [
            "einen spannenden veränderlichen Stern (z.B. Bedeckungsveränderliche, Algol-Typ etc.)",
            "einen aktuell sichtbaren Kometen oder interessanten Kleinplaneten",
            "einen fotografisch reizvollen Planetarischen Nebel oder Dunkelnebel",
            "eine besondere Galaxie (z.B. Edge-On, interagierendes Paar)",
            "einen dichten Kugelsternhaufen oder offenen Sternhaufen"
        ]
        daily_focus = focus_categories[day_of_year % len(focus_categories)]
        
        prompt = "Du bist ein erfahrener Astronom und Astrofotograf.\n"
        prompt += "Meine Ausrüstung besteht aus folgenden Smart-Teleskopen: Seestar S30 Pro, Seestar S50 und Dwarf 3. Sie haben in der App einen Planungs-Modus.\n\n"
        prompt += f"Heute ist der {datetime.now().strftime('%d.%m.%Y')}. Mein Standort liegt auf dem Breitengrad {lat}° (Nordhalbkugel).\n"
        prompt += f"Die Wetter- und Mondbedingungen für heute Nacht lauten: {weather_str}\n\n"
        
        if events_today:
            prompt += "Besondere Himmelsereignisse heute:\n"
            for e in events_today: prompt += f"- {e['title']}: {e['desc']}\n"
            prompt += "\n"
            
        prompt += "Da ich meinen Standort wählen kann (oder zwei Teleskope gleichzeitig nutze), habe ich hier ZWEI getrennte Pläne berechnet:\n\n"
        if not night_plans.get("Süd") and not night_plans.get("Nord"): 
            prompt += "- (Plan konnte wegen Wetter/Höhe oder fehlender Ziele nicht erstellt werden)\n"
        else:
            for hemi in ["Süd", "Nord"]:
                if night_plans.get(hemi):
                    prompt += f"--- PLAN FÜR BLICKRICHTUNG {hemi.upper()} ---\n"
                    for block in night_plans[hemi]:
                        comp = az_to_compass(block['az'])
                        prompt += f"- {block['start'].strftime('%H:%M')} bis {block['end'].strftime('%H:%M')}: {block['target']['name']} (Höhe: {int(block['alt'])}°, Richtung: {comp})\n"
                    prompt += "\n"
                
        prompt += "Bitte beantworte mir folgende Punkte exakt in dieser Reihenfolge:\n"
        prompt += "1. Lohnt sich Astrofotografie heute bei diesem Wetter und der Mondphase?\n"
        prompt += "2. Schau dir meine beiden Pläne (Nord und Süd) an: Sind die Reihenfolgen sinnvoll gewählt, oder würdest du (wegen Lichtverschmutzung, Mond oder Objekttyp) etwas tauschen?\n"
        prompt += "3. Aktuelles: Bitte nenne mir (nutze unbedingt deine Web-Suche) einen Kometen ODER eine frische Supernova, die ich in einen der Pläne integrieren könnte.\n"
        prompt += f"4. Dein 'Tipp des Tages': Ein Objekt, das heute gut passt und noch NICHT in meinen Plänen steht. Lege den Fokus heute explizit auf: {daily_focus}.\n"
        
        self.winfo_toplevel().clipboard_clear()
        self.winfo_toplevel().clipboard_append(prompt)
        
        msg = "Der Prompt mit beiden Teleskop-Plänen wurde kopiert!\n\nMöchtest du ChatGPT jetzt im Browser öffnen?"
        if messagebox.askyesno("KI-Prompt kopiert!", msg):
            import webbrowser
            webbrowser.open("https://chatgpt.com/")

    def delete_event(self, event_id, fallback_title=None, fallback_date=None):
        remove_event(event_id, fallback_title, fallback_date)
        self.refresh_ui()

    def _handle_missing_target_list(self):
        msg = ("Es wurde keine Beobachtungsliste (user_notes.json) gefunden.\n\n"
               "Hast du den AstroArchive Explorer? Klicke auf 'Ja', um den Ordner auszuwählen.\n"
               "Möchtest du eine völlig neue, leere Liste anlegen? Klicke auf 'Nein'.")
               
        reply = messagebox.askyesnocancel("Beobachtungsliste fehlt", msg)
        
        cfg = utils.load_config()
        
        if reply is True: 
            d = filedialog.askdirectory(title="Ordner mit user_notes.json auswählen")
            if d:
                cfg["custom_tools_path"] = os.path.normpath(d)
                utils.save_config("custom_tools_path", cfg["custom_tools_path"])
                
        elif reply is False: 
            new_dir = utils.get_data_dir()
            cfg["custom_tools_path"] = new_dir
            utils.save_config("custom_tools_path", new_dir)
            
            try:
                with open(os.path.join(new_dir, "user_notes.json"), "w", encoding="utf-8") as f: 
                    json.dump({}, f)
                with open(os.path.join(new_dir, "coordinate_cache.json"), "w", encoding="utf-8") as f: 
                    json.dump({}, f)
                messagebox.showinfo("Erfolg", "Leere Beobachtungsliste wurde erfolgreich angelegt!")
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Dateien nicht anlegen: {e}")
    
    def refresh_ui(self):
        for widget in self.scroll_events.winfo_children(): widget.destroy()
        self.last_events = load_list()
        
        if not self.last_events:
            ctk.CTkLabel(self.scroll_events, text="Keine Termine geplant.\n\nFüge Ereignisse aus dem Astro Kalender hinzu!", text_color="gray").pack(pady=50)
        else:
            for item in self.last_events:
                card = ctk.CTkFrame(self.scroll_events, fg_color="#1e272e", border_width=1, border_color="#34495e", corner_radius=8)
                card.pack(fill="x", padx=5, pady=5)
                ctk.CTkLabel(card, text=item.get("icon", "🔭"), font=("Arial", 32)).pack(side="left", padx=(15, 10), pady=10)
                date_frame = ctk.CTkFrame(card, fg_color="transparent", width=70)
                date_frame.pack(side="left", padx=10)
                ctk.CTkLabel(date_frame, text=item.get("display_date", ""), font=("Arial", 14, "bold"), text_color="#3498db").pack()
                ctk.CTkLabel(date_frame, text=item.get("time", ""), font=("Arial", 12), text_color="gray").pack()
                info_frame = ctk.CTkFrame(card, fg_color="transparent")
                info_frame.pack(side="left", fill="x", expand=True, padx=15, pady=10)
                ctk.CTkLabel(info_frame, text=item.get("title", ""), font=("Arial", 15, "bold"), anchor="w").pack(fill="x")
                ctk.CTkLabel(info_frame, text=item.get("desc", ""), font=("Arial", 12), text_color="gray", anchor="w", justify="left").pack(fill="x")
                
                btn_del = ctk.CTkButton(
                    card, text="❌", width=40, fg_color="#c0392b", hover_color="#e74c3c", 
                    command=lambda i=item.get("id"), t=item.get("title"), d=item.get("iso_date"): self.delete_event(i, t, d)
                )
                btn_del.pack(side="right", padx=15)

        for widget in self.scroll_targets.winfo_children(): widget.destroy()
        lbl_loading = ctk.CTkLabel(self.scroll_targets, text="Lade Objekte & Koordinaten...", text_color="orange")
        lbl_loading.pack(pady=50)
        self.update_idletasks()
        
        self.last_targets = load_aae_targets_rich()
        
        if self.last_targets is None:
            lbl_loading.configure(text="Warte auf Benutzereingabe...")
            self._handle_missing_target_list()
            self.last_targets = load_aae_targets_rich()
            
        lbl_loading.destroy()
        
        local_tz = pytz.timezone('Europe/Berlin')
        
        if self.last_targets is None:
            ctk.CTkLabel(self.scroll_targets, text="Beobachtungsliste nicht konfiguriert.\n\nStarte das Programm neu oder setze den Pfad in den Einstellungen.", text_color="#e74c3c").pack(pady=50)
        elif len(self.last_targets) == 0:
            ctk.CTkLabel(self.scroll_targets, text="Beobachtungsliste leer.", text_color="gray").pack(pady=50)
        else:
            for item in self.last_targets:
                card = ctk.CTkFrame(self.scroll_targets, fg_color="#242424", border_width=1, border_color="#333333", corner_radius=8)
                card.pack(fill="x", padx=5, pady=5)
                
                top_card = ctk.CTkFrame(card, fg_color="transparent")
                top_card.pack(fill="x")
                
                left_block = ctk.CTkFrame(top_card, fg_color="transparent")
                left_block.pack(side="left", fill="both", expand=True, padx=15, pady=10)
                
                icon = "🌌" if "Galaxy" in item["type"] else "☁️" if "Nebula" in item["type"] else "✨" if "Cluster" in item["type"] else "🔭"
                title_frame = ctk.CTkFrame(left_block, fg_color="transparent")
                title_frame.pack(fill="x")
                ctk.CTkLabel(title_frame, text=icon, font=("Arial", 20)).pack(side="left", padx=(0, 10))
                ctk.CTkLabel(title_frame, text=item["name"], font=("Arial", 16, "bold"), text_color="#f1c40f", anchor="w").pack(side="left")
                
                btn_edit = ctk.CTkButton(title_frame, text="✏️", width=24, height=24, fg_color="transparent", hover_color="#2c3e50")
                btn_edit.configure(command=lambda k=item["raw_key"], n=item["name"]: self.edit_target_name(k, n))
                btn_edit.pack(side="left", padx=(10, 0))
                
                coord_frame = ctk.CTkFrame(left_block, fg_color="transparent")
                coord_frame.pack(fill="x", pady=(2, 5))
                ctk.CTkLabel(coord_frame, text=item["coords_str"], font=("Consolas", 12), text_color="#95a5a6").pack(side="left")
                
                if item["ra"] is not None:
                    btn_copy = ctk.CTkButton(coord_frame, text="📋", width=24, height=24, fg_color="transparent", hover_color="#2c3e50", border_width=1)
                    def do_copy(b=btn_copy, txt=item["coords_str"]):
                        self.winfo_toplevel().clipboard_clear()
                        self.winfo_toplevel().clipboard_append(txt)
                        b.configure(text="✅", text_color="#2ecc71", border_color="#2ecc71")
                        self.after(2000, lambda: b.configure(text="📋", text_color="white", border_color="gray"))
                    btn_copy.configure(command=do_copy)
                    btn_copy.pack(side="left", padx=10)
                    
                    btn_stellarium = ctk.CTkButton(coord_frame, text="🔭 In Stellarium zeigen", height=24, fg_color="transparent", text_color="#8e44ad", border_color="#8e44ad", border_width=1, hover_color="#3e1a3a")
                    btn_stellarium.configure(command=lambda n=item["name"], r=item.get("ra"), d=item.get("dec"): self.send_to_stellarium(n, r, d))
                    btn_stellarium.pack(side="left", padx=5)
                    
                    btn_nina_push = ctk.CTkButton(coord_frame, text="🌌 An N.I.N.A. senden", height=24, fg_color="transparent", text_color="#e74c3c", border_color="#e74c3c", border_width=1, hover_color="#3e1a1a")
                    
                    def push_to_nina(n=item["name"], r=item.get("ra"), d=item.get("dec")):
                        def worker():
                            try:
                                url = f"http://localhost:1888/v2/api/framing/set-coordinates?RAangle={r}&DecAngle={d}"
                                res = requests.get(url, timeout=2)
                                if res.status_code == 200:
                                    pass
                                else:
                                    self.after(0, lambda: messagebox.showwarning("N.I.N.A.", f"N.I.N.A. meldet Fehler: {res.status_code}"))
                            except Exception as e:
                                self.after(0, lambda: messagebox.showwarning("N.I.N.A.", "Keine Verbindung zu N.I.N.A.\n\nIst N.I.N.A. geöffnet?"))
                                
                        threading.Thread(target=worker, daemon=True).start()
                        
                    btn_nina_push.configure(command=push_to_nina)
                    btn_nina_push.pack(side="left", padx=5)
                
                if item["note"]: ctk.CTkLabel(left_block, text=f"📝 {item['note']}", font=("Arial", 12), text_color="gray", anchor="w", justify="left").pack(fill="x")

                right_block = ctk.CTkFrame(top_card, fg_color="#1a1a1a", corner_radius=6)
                right_block.pack(side="right", padx=15, pady=10, fill="y")
                
                r_text_frame = ctk.CTkFrame(right_block, fg_color="transparent")
                r_text_frame.pack(side="left", fill="both", expand=True, padx=(10, 15), pady=10)
                
                r_btn_frame = ctk.CTkFrame(right_block, fg_color="transparent", width=40)
                r_btn_frame.pack(side="right", fill="y", padx=(0, 10), pady=10)
                
                del_btn = ctk.CTkButton(r_btn_frame, text="❌", width=30, height=30, fg_color="#c0392b", hover_color="#e74c3c", command=lambda k=item["raw_key"]: self.remove_target(k))
                del_btn.pack(side="top", anchor="ne")

                if item.get("ra") is not None and "max_alt" in item:
                    transit_color = "#e74c3c" if item["max_alt"] < 20 else "#f39c12" if item["max_alt"] < 40 else "#3498db"
                    t_text = f"Höchster Punkt um {item['transit_time']} Uhr ({int(item['max_alt'])}°)"
                    ctk.CTkLabel(r_text_frame, text=f"⬆ {t_text}", font=("Arial", 12, "bold"), text_color=transit_color, anchor="w").pack(fill="x", pady=(0, 4))
                    
                    m_sep = item["moon_sep"]; m_phase = item["moon_phase"]
                    if m_sep < 20: m_text, m_col = f"⚠️ Mond stört! (Distanz: {int(m_sep)}°, {int(m_phase)}%)", "#e74c3c"
                    elif m_sep < 40: m_text, m_col = f"🌙 Mond nah (Distanz: {int(m_sep)}°, {int(m_phase)}%)", "#f39c12"
                    else: m_text, m_col = f"🌑 Mond OK (Distanz: {int(m_sep)}°)", "gray"
                    ctk.CTkLabel(r_text_frame, text=m_text, font=("Arial", 11, "bold"), text_color=m_col, anchor="w").pack(fill="x", pady=(0, 4))
                    
                    c_alt = item["current_alt"]
                    c_text = f"Jetzt: Unter Horizont" if c_alt < 0 else f"Jetzt sichtbar: {int(c_alt)}° hoch"
                    ctk.CTkLabel(r_text_frame, text=c_text, font=("Arial", 11), text_color="gray", anchor="w").pack(fill="x", pady=(0, 0))
                    
                    score_frame = ctk.CTkFrame(r_btn_frame, fg_color="#2ecc71" if item["score"] > 75 else "#f39c12" if item["score"] > 40 else "#e74c3c", corner_radius=15, width=40, height=30)
                    score_frame.pack(side="bottom", anchor="se")
                    score_frame.pack_propagate(False)
                    ctk.CTkLabel(score_frame, text=str(item["score"]), font=("Arial", 12, "bold"), text_color="white").place(relx=0.5, rely=0.5, anchor="center")
                else:
                    ctk.CTkLabel(r_text_frame, text="Keine Live-Daten", text_color="gray").pack(side="left")

                if "plot_alts" in item:
                    plot_frame = ctk.CTkFrame(card, fg_color="transparent", height=100)
                    plot_frame.pack(fill="x", padx=15, pady=(0, 10))
                    
                    fig = Figure(figsize=(6, 1.2), dpi=100, facecolor='#242424')
                    ax = fig.add_subplot(111)
                    ax.set_facecolor('#242424')
                    
                    alts = np.array(item["plot_alts"])
                    times = item["plot_times"]
                    
                    ax.plot(times, alts, color='#3498db', linewidth=2)
                    ax.fill_between(times, alts, 0, where=(alts > 0), color='#3498db', alpha=0.3)
                    ax.axhline(0, color='#e74c3c', linestyle='--', linewidth=1)
                    
                    ax.set_ylim(-10, 90)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
                    ax.tick_params(axis='x', colors='gray', labelsize=8)
                    ax.tick_params(axis='y', colors='gray', labelsize=8)
                    
                    for spine in ax.spines.values():
                        spine.set_color('#444444')
                        
                    fig.tight_layout(pad=0.3)
                    
                    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
                    canvas.draw()
                    canvas.get_tk_widget().pack(fill="both", expand=True)

        if not self.last_events and not self.last_targets:
            self.btn_ics.configure(state="disabled")
            self.btn_pdf.configure(state="disabled")
        else:
            self.btn_ics.configure(state="normal")
            self.btn_pdf.configure(state="normal")
            
        self.render_tonight_tab()

    def export_ics(self):
        data = load_list()
        if not data: return
        
        cfg = utils.load_config()
        exp_dir = cfg.get("export_path", "")
        
        file_path = filedialog.asksaveasfilename(
            initialdir=exp_dir if exp_dir and os.path.exists(exp_dir) else None,
            defaultextension=".ics", 
            filetypes=[("iCalendar", "*.ics")], 
            initialfile="Astro_Ereignisse.ics"
        )
        if not file_path: return
        local_tz = pytz.timezone('Europe/Berlin')
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//SmartSuite//AstroCalendar//DE\n")
                for item in data:
                    try:
                        time_raw = str(item.get("time", "00:00")).replace(" Uhr", "").strip()
                        date_raw = str(item.get("iso_date", "")).strip()
                        dt_obj = None
                        if date_raw:
                            try: dt_obj = datetime.strptime(f"{date_raw} {time_raw}", "%Y-%m-%d %H:%M")
                            except:
                                try: dt_obj = datetime.strptime(date_raw, "%Y-%m-%d")
                                except: pass
                        if dt_obj is None: dt_obj = datetime.now()
                        dt_local = local_tz.localize(dt_obj)
                        dt_utc = dt_local.astimezone(pytz.utc)
                        dt_start = dt_utc.strftime("%Y%m%dT%H%M00Z")
                        dt_end = (dt_utc + timedelta(hours=2)).strftime("%Y%m%dT%H%M00Z") 
                        dt_stamp = datetime.now(pytz.utc).strftime("%Y%m%dT%H%M00Z")
                        uid = str(item.get("id", str(datetime.now().timestamp()))) + "@smartsuite"
                        icon = str(item.get("icon", ""))
                        title = str(item.get("title", "Astro Event"))
                        desc = str(item.get("desc", "")).replace("\n", "\\n") 
                        f.write("BEGIN:VEVENT\n")
                        f.write(f"UID:{uid}\nDTSTAMP:{dt_stamp}\nDTSTART:{dt_start}\nDTEND:{dt_end}\n")
                        f.write(f"SUMMARY:{icon} {title}\nDESCRIPTION:{desc}\nEND:VEVENT\n")
                    except Exception: pass
                f.write("END:VCALENDAR\n")
            messagebox.showinfo("Export erfolgreich", "Kalenderdatei gespeichert!")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte ICS nicht erstellen:\n{e}")
    
    def export_mobile_app(self):
        events = load_list()
        targets = load_aae_targets_rich()
        if targets is None: targets = []
        
        night_plans = self.generate_night_plan(targets)
        
        cfg = utils.load_config()
        export_dir = cfg.get("export_path", "")
        
        if not export_dir or not os.path.isdir(export_dir):
            messagebox.showinfo("Export-Pfad", "Bitte wähle deinen Cloud-Ordner (Google Drive, iCloud, Dropbox), damit du die Datei auf dem Handy öffnen kannst.")
            export_dir = filedialog.askdirectory(title="Cloud Ordner auswählen")
            if not export_dir: return
            
            cfg["export_path"] = export_dir
            try:
                with open("smartsuite_config.json", "w") as f:
                    json.dump(cfg, f, indent=4)
            except: pass
            
        html_file = os.path.join(export_dir, "Astro_Mobile_Dashboard.html")
        now_str = datetime.now().strftime('%d.%m.%Y, %H:%M')
        
        lat = float(cfg.get("default_lat", 51.16))
        lon = float(cfg.get("default_lon", 10.45))
        loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)

        def get_best_time(ra_deg, dec_deg):
            max_alt = 90 - abs(lat - dec_deg)
            if max_alt < 10: return f"Zu tief am Horizont / unsichtbar (Max: {int(max_alt)}°)"
            is_circumpolar = dec_deg > (90 - lat)
            ra_hours = ra_deg / 15.0
            month_idx = int((8.5 + (ra_hours / 2)) % 12) 
            months = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
            prev_month = months[(month_idx - 1) % 12]
            next_month = months[(month_idx + 1) % 12]
            period = f"{prev_month} bis {next_month}"
            
            days_offset = ra_hours * (365.24 / 24.0)
            base_date = datetime(2025, 9, 22)
            best_date = base_date + timedelta(days=days_offset)
            best_day_str = f"{best_date.day}. {months[best_date.month - 1]}"

            time_offset_min = (15.0 - lon) * 4.0
            is_dst = 4 <= best_date.month <= 10
            transit_hour = 1 if is_dst else 0
            transit_min = int(round(time_offset_min))
            if transit_min < 0:
                transit_min += 60
                transit_hour -= 1
                if transit_hour < 0: transit_hour = 23
            time_str = f"{transit_hour:02d}:{transit_min:02d} Uhr"
            
            alt_str = f"Max: {int(max_alt)}°"
            opt_str = f"Optimum: {best_day_str} um {time_str}"
            if is_circumpolar: return f"Ganzjährig (Beste Zeit: {period}) | {alt_str} | {opt_str}"
            else: return f"{period} | {alt_str} | {opt_str}"

        now = datetime.now()
        start_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now.hour < 12: 
            start_time -= timedelta(days=1)
            
        time_labels = []
        times = []
        for i in range(25): 
            t = start_time + timedelta(minutes=30*i)
            times.append(t)
            time_labels.append(t.strftime("%H:%M"))
            
        astro_times = Time(times)
        frame = AltAz(obstime=astro_times, location=loc)

        # --- HTML FÜR DEN PLAN GENERIEREN ---
        plan_html = ""
        if not night_plans.get("Süd") and not night_plans.get("Nord"):
            plan_html = "<p style='text-align:center; color:#888; margin-top:30px;'>Kein Teleskop-Plan möglich<br><br>(Keine Dunkelheit, Liste leer oder keine Objekte hoch genug)</p>"
        else:
            for hemi in ["Süd", "Nord"]:
                plan_list = night_plans.get(hemi, [])
                if plan_list:
                    plan_html += f"<h3 style='color:#3498db; margin-top:15px; margin-bottom:5px; font-size:16px;'>Blickrichtung: {hemi}</h3>"
                    for block in plan_list:
                        s_str = block['start'].strftime('%H:%M')
                        e_str = block['end'].strftime('%H:%M')
                        t_name = block['target']['name']
                        alt = int(block['alt'])
                        comp = az_to_compass(block['az'])
                        
                        plan_html += f"""
                        <div class="plan-card">
                            <p class="plan-time">🕒 {s_str} - {e_str}</p>
                            <p class="plan-target">{t_name}</p>
                            <p class="plan-alt">Ø Höhe: {alt}° | Richtung: {comp}</p>
                        </div>
                        """

        target_cards_html = ""
        scripts_js = ""
        chart_id = 0
        
        for t in targets:
            if t.get("ra") is None or t.get("dec") is None: continue
            
            coord = SkyCoord(ra=t["ra"]*u.deg, dec=t["dec"]*u.deg)
            altaz = coord.transform_to(frame)
            alts = [round(a, 1) for a in altaz.alt.deg]
            azs = altaz.az.deg
            
            max_alt = max(alts)
            max_idx = alts.index(max_alt)
            best_time_tonight = time_labels[max_idx]
            best_az = azs[max_idx]
            compass_dir = az_to_compass(best_az)
            
            if max_alt < 0:
                tonight_str = "❌ Heute Nacht unter dem Horizont"
            else:
                tonight_str = f"⭐ Heute Nacht: Am höchsten um {best_time_tonight} Uhr ({max_alt}° in Richtung {compass_dir})"
                
            obs_info = get_best_time(t["ra"], t["dec"])
            
            moon_html = ""
            if "moon_sep" in t:
                m_sep = t["moon_sep"]
                m_phase = t["moon_phase"]
                if m_sep < 20: moon_html = f'<p class="moon-danger">⚠️ Mond stört! (Distanz: {int(m_sep)}°, Phase: {int(m_phase)}%)</p>'
                elif m_sep < 40: moon_html = f'<p class="moon-warn">🌙 Mond nah (Distanz: {int(m_sep)}°, Phase: {int(m_phase)}%)</p>'
                else: moon_html = f'<p class="moon-ok">🌑 Mond OK (Distanz: {int(m_sep)}°)</p>'
                
            note_text = t.get("note", "").replace('\n', '<br>')
            note_html = f'<div class="note-box">📝 {note_text}</div>' if note_text else ""
            
            target_cards_html += f"""
            <div class="card">
                <h2>{t['name']}</h2>
                <p class="coords">{t.get('coords_str', '')}</p>
                <p class="obs-info">🔭 {obs_info}</p>
                <p class="tonight-info">{tonight_str}</p>
                {moon_html}
                {note_html}
                <div class="chart-container">
                    <canvas id="chart_{chart_id}"></canvas>
                </div>
            </div>
            """
            
            scripts_js += f"""
            new Chart(document.getElementById('chart_{chart_id}'), {{
                type: 'line',
                data: {{
                    labels: {json.dumps(time_labels)},
                    datasets: [{{
                        data: {json.dumps(alts)},
                        borderColor: '#e74c3c',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)',
                        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    scales: {{
                        y: {{ min: 0, max: 90, grid: {{ color: '#333' }}, ticks: {{ color: '#888', stepSize: 30 }} }},
                        x: {{ grid: {{ color: '#333' }}, ticks: {{ color: '#888', maxTicksLimit: 6 }} }}
                    }},
                    plugins: {{ legend: {{ display: false }}, tooltip: {{ mode: 'index', intersect: false }} }},
                    interaction: {{ mode: 'nearest', axis: 'x', intersect: false }}
                }}
            }});
            """
            chart_id += 1

        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Astro Mobile Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background-color: #121212; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 15px; padding-bottom: 70px; }}
        .header {{ padding: 0 0 15px 0; text-align: center; border-bottom: 1px solid #333; margin-bottom: 20px; }}
        h1 {{ color: #3498db; margin: 0 0 5px 0; font-size: 24px; }}
        .sync-time {{ font-size: 11px; color: #555; }}
        .subtitle {{ font-size: 14px; color: #888; }}
        
        /* Bottom Navigation */
        .bottom-nav {{ position: fixed; bottom: 0; left: 0; width: 100%; background: #1e1e1e; display: flex; border-top: 1px solid #333; z-index: 100; padding-bottom: env(safe-area-inset-bottom); }}
        .nav-btn {{ flex: 1; padding: 10px 5px; text-align: center; color: #888; text-decoration: none; font-size: 13px; font-weight: bold; background: none; border: none; outline: none; }}
        .nav-btn.active {{ color: #3498db; border-top: 2px solid #3498db; background-color: rgba(52, 152, 219, 0.1); }}
        
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        
        /* Plan Styling */
        .plan-card {{ background-color: #1e1e1e; border-left: 4px solid #2ecc71; padding: 15px; margin-bottom: 12px; border-radius: 8px; border-top: 1px solid #333; border-right: 1px solid #333; border-bottom: 1px solid #333; box-shadow: 0 2px 8px rgba(0,0,0,0.5); }}
        .plan-time {{ color: #f39c12; font-family: Consolas, monospace; font-weight: bold; font-size: 15px; margin: 0 0 8px 0; }}
        .plan-target {{ color: #ecf0f1; font-weight: bold; font-size: 17px; margin: 0 0 5px 0; line-height: 1.3; }}
        .plan-alt {{ color: #7f8c8d; font-size: 13px; margin: 0; }}
        
        /* Event Styling */
        .event-card {{ background-color: #1e1e1e; border-radius: 16px; padding: 15px; margin-bottom: 15px; border: 1px solid #333; display: flex; align-items: center; }}
        .e-icon {{ font-size: 28px; margin-right: 15px; min-width: 40px; text-align:center; }}
        .e-date {{ color: #3498db; font-weight: bold; font-size: 16px; margin:0; }}
        .e-time {{ color: #888; font-size: 12px; margin:0; font-weight: normal; }}
        .e-title {{ font-size: 16px; font-weight: bold; margin: 0 0 4px 0; }}
        .e-desc {{ font-size: 13px; color: #aaa; margin: 0; line-height: 1.4; }}
        
        /* Target Styling */
        .card {{ background-color: #1e1e1e; border-radius: 16px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); border: 1px solid #333; }}
        .card h2 {{ margin: 0 0 5px 0; font-size: 20px; color: #ecf0f1; }}
        .coords {{ color: #95a5a6; font-size: 12px; margin: 0 0 5px 0; font-family: Consolas, monospace; }}
        .obs-info {{ color: #2ecc71; font-size: 11px; margin: 0 0 3px 0; font-weight: bold; }}
        .tonight-info {{ color: #3498db; font-size: 11px; margin: 0 0 4px 0; font-weight: bold; }}
        .moon-danger {{ color: #e74c3c; font-size: 11px; margin: 0 0 10px 0; font-weight: bold; }}
        .moon-warn {{ color: #f39c12; font-size: 11px; margin: 0 0 10px 0; font-weight: bold; }}
        .moon-ok {{ color: #7f8c8d; font-size: 11px; margin: 0 0 10px 0; }}
        .note-box {{ background-color: rgba(243, 156, 18, 0.1); border-left: 3px solid #f39c12; padding: 8px 10px; margin-bottom: 15px; font-size: 13px; color: #f1c40f; border-radius: 0 4px 4px 0; }}
        .chart-container {{ position: relative; height: 160px; width: 100%; }}
    </style>
</head>
<body>

    <div class="header">
        <h1>🔭 Astro Dashboard</h1>
        <div class="subtitle">Nacht vom {start_time.strftime('%d.%m.')} auf {(start_time + timedelta(days=1)).strftime('%d.%m.')}</div>
        <div class="sync-time">Letzter Sync: {now_str} Uhr</div>
    </div>

    <!-- TAB 1: HEUTE NACHT (PLAN) -->
    <div id="tab-plan" class="tab-content active">
        <h2 style="font-size: 18px; color: #2ecc71; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 10px;">Teleskop-Plan (je 1,5 Std)</h2>
        {plan_html}
    </div>

    <!-- TAB 2: ZIELE -->
    <div id="tab-targets" class="tab-content">
"""
        if chart_id == 0:
            html += "<p style='text-align:center; color:#888;'>Beobachtungsliste ist leer oder enthält keine Koordinaten.</p>"
        else:
            html += target_cards_html

        html += """
    </div>

    <!-- TAB 3: KALENDER -->
    <div id="tab-events" class="tab-content">
"""
        if not events:
            html += "<p style='text-align:center; color:#888;'>Keine Termine geplant.</p>"
        else:
            for e in events:
                html += f"""
                <div class="event-card">
                    <div class="e-icon">{e.get('icon', '⭐')}</div>
                    <div>
                        <p class="e-title">{e['title']}</p>
                        <p class="e-date">{e.get('display_date', '')} <span class="e-time">{e.get('time', '')} Uhr</span></p>
                        <p class="e-desc">{e['desc'].replace(chr(10), '<br>')}</p>
                    </div>
                </div>"""

        html += f"""
    </div>

    <!-- BOTTOM NAV -->
    <div class="bottom-nav">
        <button class="nav-btn active" onclick="switchTab('plan', this)">✨ Heute</button>
        <button class="nav-btn" onclick="switchTab('targets', this)">🔭 Ziele</button>
        <button class="nav-btn" onclick="switchTab('events', this)">📅 Termine</button>
    </div>

    <script>
        Chart.defaults.color = '#888';
        {scripts_js}
        
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            btn.classList.add('active');
            window.scrollTo(0, 0);
        }}
    </script>
</body>
</html>
"""
        try:
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html)
            
            success_win = ctk.CTkToplevel(self)
            success_win.title("Sync erfolgreich")
            success_win.geometry("350x120")
            success_win.attributes("-topmost", True)
            
            success_win.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() // 2) - 175
            y = self.winfo_rooty() + (self.winfo_height() // 2) - 60
            success_win.geometry(f"+{x}+{y}")
            
            ctk.CTkLabel(success_win, text="✅ Handy-App erfolgreich aktualisiert!", font=("Arial", 14, "bold"), text_color="#2ecc71").pack(expand=True)
            success_win.after(1500, success_win.destroy)
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte App nicht exportieren:\n{e}")

    def export_pdf_html(self):
        events = load_list()
        targets = load_aae_targets_rich()
        if targets is None: targets = []
        
        cfg = utils.load_config()
        exp_dir = cfg.get("export_path", "")
        if exp_dir and os.path.isdir(exp_dir):
            html_file = os.path.join(exp_dir, "smartsuite_druckansicht.html")
        else:
            html_file = os.path.abspath("smartsuite_druckansicht.html")
        
        html = f"""<html><head><meta charset="utf-8"><title>Astro Planungs-Dashboard</title><style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; max-width: 900px; margin: 0 auto; color: #222; background: #fff; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin-bottom: 20px; }}
                h2 {{ color: #8e44ad; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                .event {{ display: flex; align-items: center; border-bottom: 1px solid #eee; padding: 10px 0; page-break-inside: avoid; }}
                .date-box {{ min-width: 90px; color: #3498db; font-weight: bold; }}
                .details {{ flex-grow: 1; }}
                .title {{ font-size: 16px; font-weight: bold; margin: 0 0 3px 0; }}
                .desc {{ font-size: 13px; color: #555; margin: 0; }}
                .target-card {{ border: 1px solid #ccc; padding: 12px; border-radius: 6px; background: #fdfdfd; margin-bottom: 10px; page-break-inside: avoid; }}
                .t-head {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-bottom: 5px; }}
                .t-title {{ font-size: 16px; font-weight: bold; color: #c0392b; margin: 0; }}
                .t-score {{ font-weight: bold; color: #27ae60; }}
                .t-coords {{ font-family: monospace; font-size: 11px; color: #7f8c8d; }}
                .t-stats {{ font-size: 12px; font-weight: bold; color: #2980b9; margin: 3px 0; }}
                .t-moon {{ font-size: 12px; color: #e67e22; margin: 0; }}
                .t-note {{ font-size: 13px; color: #333; margin-top: 5px; font-style: italic; }}
            </style></head><body><h1>🔭 Meine Astro-Planung</h1>"""
        if events:
            html += "<h2>📅 Geplante Himmelsereignisse</h2>"
            for item in events:
                html += f"""<div class="event"><div style="font-size: 24px; margin-right: 15px;">{item.get('icon', '⭐')}</div>
                    <div class="date-box">{item.get('display_date', '')}<br><span style="font-size:12px; color:#7f8c8d; font-weight:normal;">{item.get('time', '')}</span></div>
                    <div class="details"><p class="title">{item['title']}</p><p class="desc">{item['desc'].replace(chr(10), '<br>')}</p></div></div>"""
        
        if targets:
            html += "<h2>🎯 Deep-Sky Ziele (Live-Daten für heute Nacht)</h2>"
            for item in targets:
                moon_str = f"Mond-Distanz: {int(item['moon_sep'])}° (Phase: {int(item['moon_phase'])}%)" if "moon_sep" in item else ""
                transit_str = f"Höchster Punkt um {item.get('transit_time', '---')} ({int(item.get('max_alt', 0))}°)" if "max_alt" in item else ""
                score_str = f"Score: {item.get('score', 0)}/100" if item.get('score', -1) >= 0 else ""
                html += f"""<div class="target-card"><div class="t-head"><p class="t-title">{item['name']}</p><span class="t-score">{score_str}</span></div>
                    <p class="t-coords">{item.get('coords_str', '')}</p><p class="t-stats">⬆ {transit_str}</p><p class="t-moon">🌙 {moon_str}</p>
                    <p class="t-note">📝 {item['note'].replace(chr(10), '<br>') if item['note'] else 'Keine Notizen'}</p></div>"""
                
        html += f"<div style='margin-top:30px; font-size:11px; color:#999; text-align:center;'>Generiert mit SmartSuite am {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>"
        html += "<script>window.onload = function() { window.print(); }</script></body></html>"
        try:
            with open(html_file, "w", encoding="utf-8") as f: f.write(html)
            webbrowser.open(f"file://{html_file}")
        except Exception as e: messagebox.showerror("Fehler", f"Konnte Druckansicht nicht erstellen:\n{e}")