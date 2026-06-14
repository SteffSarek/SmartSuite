# ==============================================================================
# MODULE_CALENDAR.PY - Astronomischer Kalender & Himmelsereignisse (Auto-Cached)
# ==============================================================================
import sys
import os

# --- ABSOLUTER FIX FÜR PYINSTALLER .EXE ABSTÜRZE & LIVE-TERMINAL ---
# Wir fangen alle Terminal-Ausgaben ab und leiten sie in unser eigenes System um.
class OutputRedirector:
    def __init__(self):
        self.buffer = ""
        self.ui_callback = None
        
    def write(self, string):
        self.buffer += string
        if self.ui_callback:
            self.ui_callback(string)
            
    def flush(self):
        pass # Hier ist der "Flush"-Befehl, den Skyfield gesucht hat!

if not hasattr(sys, 'stdout_redirected'):
    global_redirector = OutputRedirector()
    if sys.stdout is None: sys.stdout = global_redirector
    if sys.stderr is None: sys.stderr = global_redirector
    sys.stdout = global_redirector
    sys.stderr = global_redirector
    sys.stdout_redirected = True
else:
    global_redirector = sys.stdout

import tkinter as tk
import customtkinter as ctk
import threading
from datetime import datetime, timedelta
import math
import numpy as np
import pytz
import json
import time

import ephem
from skyfield.api import Loader, wgs84

# Wir zwingen Skyfield, im echten Programm-Ordner zu suchen
import smart_utils as utils
import module_obs_list

# Lädt Ephemeriden in den neuen AstroData-Ordner
sky_loader = Loader(utils.get_data_dir(), verbose=True)

# Auch der Cache kommt dort rein
CACHE_FILE = os.path.join(utils.get_data_dir(), "smartsuite_calendar_cache.json")
CACHE_LIFETIME_SECONDS = 43200  # 12 Stunden

class AstroCalendarFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        self.is_calculating = False
        self._calc_result = None 
        
        # --- UI AUFBAU ---
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(top_frame, text="🗓️ Astro Beobachtungs-Kalender", font=("Arial", 18, "bold")).pack(side="left", padx=10, pady=10)
        
        self.btn_calc = ctk.CTkButton(top_frame, text="🔄 Aktualisieren", command=lambda: self._trigger_load(force=True), fg_color="#2980b9", hover_color="#3498db", width=130)
        self.btn_calc.pack(side="right", padx=10)
        
        # --- HIER IST DER TERMINAL-BUTTON WIEDER ---
        self.btn_log = ctk.CTkButton(top_frame, text="🐞 Terminal", command=self.open_debug_log, fg_color="#34495e", hover_color="#2c3e50", width=100)
        self.btn_log.pack(side="right", padx=10)
        
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=0)
        
        self.lbl_location = ctk.CTkLabel(info_frame, text="Standort wird geladen...", text_color="gray", font=("Arial", 12))
        self.lbl_location.pack(side="left", padx=10)
        
        self.after(0, self.update_location_label)

        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        self.lbl_welcome = ctk.CTkLabel(self.scroll_frame, text="Lade Kalender...", text_color="gray")
        self.lbl_welcome.pack(pady=50)

        # Direkt beim Start einmal laden!
        self.refresh_ui()

    # --- DAS EIGENE TERMINAL FENSTER ---
    def open_debug_log(self):
        log_win = ctk.CTkToplevel(self)
        log_win.title("Entwickler Terminal (Logs)")
        log_win.geometry("700x500")
        log_win.attributes("-topmost", True)
        
        textbox = ctk.CTkTextbox(log_win, font=("Consolas", 11), fg_color="#1e1e1e", text_color="#2ecc71")
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        textbox.insert("end", global_redirector.buffer)
        textbox.see("end")
        
        def append_to_textbox(text):
            try:
                textbox.insert("end", text)
                textbox.see("end")
            except: pass
            
        def thread_safe_append(text):
            self.after(0, lambda: append_to_textbox(text))
            
        global_redirector.ui_callback = thread_safe_append
        
        def on_close():
            global_redirector.ui_callback = None
            log_win.destroy()
            
        log_win.protocol("WM_DELETE_WINDOW", on_close)

    def update_location_label(self):
        cfg = utils.load_config()
        lat = cfg.get("default_lat", "51.16")
        lon = cfg.get("default_lon", "10.45")
        self.lbl_location.configure(text=f"Aktueller Standort: Lat {lat}° / Lon {lon}°")

    def refresh_ui(self):
        if not self.is_calculating:
            self._trigger_load(force=False)

    # ==========================================
    # SICHERE HAUPT-THREAD-STEUERUNG (POLLING)
    # ==========================================
    def _trigger_load(self, force=False):
        if self.is_calculating: return
        self.is_calculating = True
        self.btn_calc.configure(state="disabled")
        
        self.update_location_label()
        
        # CACHE PRÜFEN (Im Haupt-Thread!)
        if not force and os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                if time.time() - cache_data.get("timestamp", 0) < CACHE_LIFETIME_SECONDS:
                    events = cache_data.get("events", [])
                    for ev in events:
                        ev["time"] = datetime.fromisoformat(ev["time"])
                    self.render_calendar(events)
                    return
            except Exception as e:
                print(f"Calendar Cache Load Error: {e}")

        # WENN KEIN CACHE -> HEAVY LIFTING IM HINTERGRUND
        self._show_loading()
        self._calc_result = None
        threading.Thread(target=self._worker_calculate_heavy, daemon=True).start()
        self._poll_calc_result()

    def _poll_calc_result(self):
        if self._calc_result is not None:
            self.render_calendar(self._calc_result)
        else:
            self.after(100, self._poll_calc_result)

    def _show_loading(self):
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        ctk.CTkLabel(self.scroll_frame, text="⏳ Lade Bahndaten & Berechne Mechanik (ISS & Jahr)... Bitte warten.", font=("Arial", 14)).pack(pady=50)

    def _worker_calculate_heavy(self):
        print("Starte Hintergrund-Berechnung...")
        events_iss = self._calc_iss_events()
        events_year = self._calc_year_events()
        
        print("Führe Listen zusammen...")
        all_events = events_iss + events_year
        all_events.sort(key=lambda x: x["time"])
        
        try:
            cache_save = []
            for ev in all_events:
                ev_copy = ev.copy()
                ev_copy["time"] = ev_copy["time"].isoformat()
                cache_save.append(ev_copy)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "events": cache_save}, f, indent=4)
            print("Cache erfolgreich aktualisiert.")
        except Exception as e: 
            print(f"Cache Save Error: {e}")
            
        self._calc_result = all_events

    def ephem_to_local(self, ephem_date, tz):
        utc_dt = ephem_date.datetime().replace(tzinfo=pytz.utc)
        return utc_dt.astimezone(tz)

    # ==========================================
    # HIMMELSJAHR GENERATOR
    # ==========================================
    def _generate_month_summary(self, year, month):
        sun = ephem.Sun()
        planets = {"Merkur": ephem.Mercury(), "Venus": ephem.Venus(), "Mars": ephem.Mars(), "Jupiter": ephem.Jupiter(), "Saturn": ephem.Saturn()}
        mid_month = ephem.Date(datetime(year, month, 15))
        sun.compute(mid_month)
        const_map = {'Ari': 'Widder', 'Tau': 'Stier', 'Gem': 'Zwillinge', 'Cnc': 'Krebs', 'Leo': 'Löwe', 'Vir': 'Jungfrau', 'Lib': 'Waage', 'Sco': 'Skorpion', 'Sgr': 'Schütze', 'Cap': 'Steinbock', 'Aqr': 'Wassermann', 'Psc': 'Fische', 'Oph': 'Schlangenträger', 'Cet': 'Walfisch', 'Ori': 'Orion', 'Aur': 'Fuhrmann'}
        lines = []
        if month == 1: lines.append("— Die Erde kommt Anfang des Monats in Sonnennähe (Perihel).")
        elif month == 7: lines.append("— Die Erde erreicht Anfang des Monats ihre Sonnenferne (Aphel).")
            
        for name, p in planets.items():
            p.compute(mid_month)
            sep = math.degrees(ephem.separation(sun, p))
            const_abbr = ephem.constellation(p)[0]
            const_name = const_map.get(const_abbr, const_abbr)
            diff_ra = (p.ra - sun.ra)
            diff_ra = (diff_ra + math.pi) % (2 * math.pi) - math.pi
            diff_deg = math.degrees(diff_ra)
            
            if sep < 12: 
                if name == "Merkur": lines.append("— Merkur lässt sich diesen Monat nicht blicken.")
                elif name == "Venus": lines.append("— Venus hält sich zu nah an der Sonne auf und bleibt unsichtbar.")
            else:
                if name == "Venus":
                    if diff_deg > 0: lines.append(f"— Venus dominiert als strahlender Abendstern im Sternbild {const_name}.")
                    else: lines.append(f"— Venus leuchtet als heller Morgenstern im Sternbild {const_name}.")
                elif name == "Merkur":
                    if sep > 18: 
                        if diff_deg > 0: lines.append("— Merkur bietet eine kurze Sichtbarkeit am frühen Abendhimmel.")
                        else: lines.append("— Merkur zeigt sich flüchtig in der Morgendämmerung.")
                else: 
                    if sep > 150: lines.append(f"— {name} steht im Sternbild {const_name} in Opposition und ist die ganze Nacht optimal zu sehen.")
                    elif diff_deg > 0: 
                        if diff_deg > 90: lines.append(f"— {name} ist ein auffälliges Objekt für die erste Nachthälfte ({const_name}).")
                        else: lines.append(f"— {name} verabschiedet sich langsam am frühen Abendhimmel.")
                    else: 
                        if diff_deg < -90: lines.append(f"— {name} dominiert den Morgenhimmel und die zweite Nachthälfte.")
                        else: lines.append(f"— {name} taucht in der Morgendämmerung wieder auf ({const_name}).")
        return "\n".join(lines)

    # ==========================================
    # BERECHNUNG: ISS TRANSITE UND ÜBERFLÜGE
    # ==========================================
    def _calc_iss_events(self):
        cfg = utils.load_config()
        lat = float(cfg.get("default_lat", "51.16"))
        lon = float(cfg.get("default_lon", "10.45"))
        local_tz = pytz.timezone('Europe/Berlin')
        events = []
        
        try:
            print("Lade Skyfield Ephemeriden...")
            ts = sky_loader.timescale()
            t0 = ts.now()
            t1_dt = t0.utc_datetime() + timedelta(days=10)
            t1 = ts.from_datetime(t1_dt)
            
            eph = sky_loader('de421.bsp')
            sun, moon, earth = eph['sun'], eph['moon'], eph['earth']
            
            topos = wgs84.latlon(lat, lon)
            observer = earth + topos
            
            print("Lade aktuelle ISS Stationsdaten...")
            stations_url = 'https://celestrak.org/NORAD/elements/stations.txt'
            satellites = sky_loader.tle_file(stations_url)
            iss = {sat.name: sat for sat in satellites}.get('ISS (ZARYA)')
            
            if not iss: return events
                
            print("Suche nach ISS Ueberfluegen...")
            t_pass, events_pass = iss.find_events(topos, t0, t1, altitude_degrees=5.0)
            
            passes = []
            current_pass = {}
            for ti, ev in zip(t_pass, events_pass):
                if ev == 0: current_pass['rise'] = ti
                elif ev == 1: current_pass['culminate'] = ti
                elif ev == 2: 
                    current_pass['set'] = ti
                    if 'rise' in current_pass: passes.append(current_pass)
                    current_pass = {}
                    
            for p in passes:
                t_start = p['rise']
                t_end = p['set']
                t_culm = p.get('culminate', t_start)
                
                dt_start = t_start.utc_datetime()
                dt_end = t_end.utc_datetime()
                
                sec = int((dt_end - dt_start).total_seconds())
                if sec <= 0: continue
                
                t_arr = ts.utc(dt_start.year, dt_start.month, dt_start.day, 
                               dt_start.hour, dt_start.minute, 
                               dt_start.second + np.arange(sec))
                               
                iss_topo = (iss - topos).at(t_arr)
                ra_iss, dec_iss, _ = iss_topo.radec()
                iss_alt_arr = iss_topo.altaz()[0].degrees
                
                sun_app = observer.at(t_arr).observe(sun).apparent()
                ra_sun, dec_sun, _ = sun_app.radec()
                sun_alt_arr = sun_app.altaz()[0].degrees
                
                moon_app = observer.at(t_arr).observe(moon).apparent()
                ra_moon, dec_moon, _ = moon_app.radec()
                moon_alt_arr = moon_app.altaz()[0].degrees
                
                r_iss = ra_iss.radians; d_iss = dec_iss.radians
                r_sun = ra_sun.radians; d_sun = dec_sun.radians
                r_moon = ra_moon.radians; d_moon = dec_moon.radians
                
                cos_sun = np.sin(d_iss)*np.sin(d_sun) + np.cos(d_iss)*np.cos(d_sun)*np.cos(r_iss - r_sun)
                sep_sun = np.degrees(np.arccos(np.clip(cos_sun, -1.0, 1.0)))
                cos_moon = np.sin(d_iss)*np.sin(d_moon) + np.cos(d_iss)*np.cos(d_moon)*np.cos(r_iss - r_moon)
                sep_moon = np.degrees(np.arccos(np.clip(cos_moon, -1.0, 1.0)))
                
                min_sun_sep = np.min(sep_sun)
                min_moon_sep = np.min(sep_moon)
                
                # --- STRENGERER TRANSIT-FILTER ---
                is_transit = False
                # Max 1.5 Grad Abweichung für einen "nahen" Vorbeiflug (Sonne)
                if min_sun_sep < 1.5:
                    idx = np.argmin(sep_sun)
                    if sun_alt_arr[idx] > 5:
                        t_transit = t_arr[idx]; alt = iss_alt_arr[idx]
                        dt_local = t_transit.utc_datetime().replace(tzinfo=pytz.utc).astimezone(local_tz)
                        if min_sun_sep < 0.28:
                            duration = round(len(np.where(sep_sun < 0.28)[0]) * 1.0, 1)
                            events.append({"time": dt_local, "icon": "☀️", "title": "ISS Transit vor der Sonne!", "desc": f"Direkter Treffer! Dauer: {duration} Sekunden. Höhe: {int(alt)}°."})
                        else:
                            dist_km = round(min_sun_sep * 11.5)
                            events.append({"time": dt_local, "icon": "☀️", "title": "Naher Sonnen-Transit", "desc": f"ISS verfehlt das Zentrum um {round(min_sun_sep, 1)}° (ca. {dist_km} km entfernt). Höhe: {int(alt)}°."})
                        is_transit = True
                        
                # Max 1.5 Grad Abweichung für einen "nahen" Vorbeiflug (Mond)
                if not is_transit and min_moon_sep < 1.5:
                    idx = np.argmin(sep_moon)
                    if moon_alt_arr[idx] > 5:
                        t_transit = t_arr[idx]; alt = iss_alt_arr[idx]
                        dt_local = t_transit.utc_datetime().replace(tzinfo=pytz.utc).astimezone(local_tz)
                        if min_moon_sep < 0.28:
                            duration = round(len(np.where(sep_moon < 0.28)[0]) * 1.0, 1)
                            events.append({"time": dt_local, "icon": "🌕", "title": "ISS Transit vor dem Mond!", "desc": f"Direkter Treffer! Dauer: {duration} Sekunden. Höhe: {int(alt)}°."})
                        else:
                            dist_km = round(min_moon_sep * 11.5)
                            events.append({"time": dt_local, "icon": "🌕", "title": "Naher Mond-Transit", "desc": f"ISS verfehlt das Zentrum um {round(min_moon_sep, 1)}° (ca. {dist_km} km entfernt). Höhe: {int(alt)}°."})
                        is_transit = True
                        
                if not is_transit:
                    sun_culm_alt = observer.at(t_culm).observe(sun).apparent().altaz()[0].degrees
                    if sun_culm_alt < -6:
                        if iss.at(t_culm).is_sunlit(eph):
                            iss_culm_alt = (iss - topos).at(t_culm).altaz()[0].degrees
                            if iss_culm_alt > 35:
                                dt_rise = dt_start.replace(tzinfo=pytz.utc).astimezone(local_tz)
                                dt_culm = t_culm.utc_datetime().replace(tzinfo=pytz.utc).astimezone(local_tz)
                                dt_set = t_end.utc_datetime().replace(tzinfo=pytz.utc).astimezone(local_tz)
                                
                                # Himmelsrichtungen berechnen
                                def get_dir(time_obj):
                                    az = (iss - topos).at(time_obj).altaz()[1].degrees
                                    dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
                                    return dirs[int((az + 11.25) / 22.5) % 16]
                                    
                                dir_rise = get_dir(t_start)
                                dir_culm = get_dir(t_culm)
                                dir_set = get_dir(t_end)
                                
                                # --- NEU: Sternbild am höchsten Punkt berechnen ---
                                # Dafür brauchen wir ein klassisches ephem Objekt
                                import ephem
                                obs_ephem = ephem.Observer()
                                cfg = utils.load_config()
                                obs_ephem.lat = str(cfg.get("default_lat", "51.16"))
                                obs_ephem.lon = str(cfg.get("default_lon", "10.45"))
                                obs_ephem.date = t_culm.utc_datetime()
                                
                                # Wir nutzen die RA/DEC der ISS zum Kulminationszeitpunkt
                                iss_topo = (iss - topos).at(t_culm)
                                ra_iss, dec_iss, _ = iss_topo.radec()
                                
                                # Einen Dummy-Stern an diese Position setzen
                                dummy = ephem.FixedBody()
                                dummy._ra = ra_iss.radians
                                dummy._dec = dec_iss.radians
                                dummy.compute(obs_ephem)
                                
                                const_abbr = ephem.constellation(dummy)[0]
                                const_map = {
                                    'Ari': 'Widder', 'Tau': 'Stier', 'Gem': 'Zwillinge', 'Cnc': 'Krebs',
                                    'Leo': 'Löwe', 'Vir': 'Jungfrau', 'Lib': 'Waage', 'Sco': 'Skorpion',
                                    'Sgr': 'Schütze', 'Cap': 'Steinbock', 'Aqr': 'Wassermann', 'Psc': 'Fische',
                                    'Oph': 'Schlangenträger', 'Cet': 'Walfisch', 'Ori': 'Orion', 'Aur': 'Fuhrmann',
                                    'Sex': 'Sextant', 'UMa': 'Großer Bär', 'Peg': 'Pegasus', 'Cyg': 'Schwan',
                                    'Cas': 'Kassiopeia', 'Cep': 'Kepheus', 'Boo': 'Bärenhüter', 'Her': 'Herkules',
                                    'Lyr': 'Leier', 'Aql': 'Adler', 'CrB': 'Nördliche Krone', 'Dra': 'Drache',
                                    'CVn': 'Nördliche Krone', 'Cam': 'Giraffe', 'And': 'Andromeda', 'Per': 'Perseus'
                                }
                                const_de = const_map.get(const_abbr, const_abbr)
                                
                                desc_text = (f"Die ISS zieht sichtbar als sehr heller Punkt über den Himmel!\n"
                                             f"• Auftauchen: {dt_rise.strftime('%H:%M')} Uhr im {dir_rise}\n"
                                             f"• Höchster Punkt: {dt_culm.strftime('%H:%M')} Uhr ({int(iss_culm_alt)}° im {dir_culm} -> Sternbild {const_de})\n"
                                             f"• Verschwinden: ca. {dt_set.strftime('%H:%M')} Uhr im {dir_set}")
                                             
                                events.append({"time": dt_culm, "icon": "🛰️", "title": "Heller ISS Überflug", "desc": desc_text})
                                
            print("ISS Berechnung abgeschlossen.")
            return events
            
        except Exception as e:
            print(f"ISS Calculation Error: {e}")
            events.append({"time": datetime.now(local_tz), "icon": "⚠️", "title": "Fehler bei ISS-Berechnung", "desc": f"Technischer Fehler: {str(e)}"})
            return events

    # ==========================================
    # BERECHNUNG: DAS JAHRESPROGRAMM
    # ==========================================
    def _calc_year_events(self):
        print("Berechne Jahres-Ereignisse...")
        cfg = utils.load_config()
        lat_str = str(cfg.get("default_lat", "51.16"))
        lon_str = str(cfg.get("default_lon", "10.45"))
        local_tz = pytz.timezone('Europe/Berlin')
        current_year = datetime.now().year
        
        observer = ephem.Observer()
        observer.lat = lat_str
        observer.lon = lon_str
        observer.elevation = 150
        moon = ephem.Moon()
        sun = ephem.Sun()
        
        events = []
        start_utc = datetime(current_year, 1, 1, tzinfo=pytz.utc)
        end_utc = datetime(current_year + 1, 1, 1, tzinfo=pytz.utc)
        start_ephem = ephem.Date(start_utc)
        end_ephem = ephem.Date(end_utc)

        # --- 1. JAHRESZEITEN (Äquinoktien & Solstitien) ---
        try:
            spring = self.ephem_to_local(ephem.next_vernal_equinox(str(current_year)), local_tz)
            events.append({"time": spring, "icon": "🌱", "title": "Frühlingsanfang", "desc": "Frühlings-Tag-und-Nachtgleiche. Tag und Nacht sind heute annähernd gleich lang."})
            
            summer = self.ephem_to_local(ephem.next_summer_solstice(str(current_year)), local_tz)
            events.append({"time": summer, "icon": "☀️", "title": "Sommeranfang", "desc": "Sommersonnenwende. Der längste Tag und die kürzeste Nacht des Jahres."})
            
            autumn = self.ephem_to_local(ephem.next_autumnal_equinox(str(current_year)), local_tz)
            events.append({"time": autumn, "icon": "🍂", "title": "Herbstanfang", "desc": "Herbst-Tag-und-Nachtgleiche. Ab jetzt werden die Nächte wieder länger als die Tage."})
            
            winter = self.ephem_to_local(ephem.next_winter_solstice(str(current_year)), local_tz)
            events.append({"time": winter, "icon": "❄️", "title": "Winteranfang", "desc": "Wintersonnenwende. Der kürzeste Tag und die längste Nacht des Jahres. Perfekt für lange Astronomie-Nächte!"})
        except Exception as e:
            print(f"Jahreszeiten Fehler: {e}")

        # --- 2. VOLLMOND & MONDFINSTERNISSE ---
        moon_names = {
            1: "Wolfsmond / Eismond", 2: "Schneemond / Hornung", 3: "Wurmmond / Lenzmond",
            4: "Ostermond / Grasmond", 5: "Blumenmond / Wonnemond", 6: "Erdbeermond / Rosenmond",
            7: "Heumond / Donnermond", 8: "Getreidemond / Roter Mond", 9: "Erntemond / Herbstmond",
            10: "Jägermond / Weinmond", 11: "Nebelmond / Bibermond", 12: "Kalter Mond / Julmond"
        }

        curr = start_ephem
        full_moons_this_month = {}
        
        while True:
            fm = ephem.next_full_moon(curr)
            if fm > end_ephem: break
            
            dt_local = self.ephem_to_local(fm, local_tz)
            month = dt_local.month
            
            # 1. Supermond & Blaumond Logik
            if month in full_moons_this_month:
                moon_title = f"Blaumond (Zweiter Vollmond im {dt_local.strftime('%B')})"
            else:
                full_moons_this_month[month] = True
                moon_title = f"Vollmond ({moon_names.get(month, '')})"
                
            observer.date = fm
            moon.compute(observer)
            sun.compute(observer)
            
            dist_km = moon.earth_distance * 149597870.7
            super_str = ""
            if dist_km < 360000:
                moon_title = f"🌟 Supermond ({moon_names.get(month, '')})"
                super_str = f" Der Mond ist heute besonders nah ({int(dist_km)} km) und wirkt riesig!"

            # 2. Mondfinsternis Logik (Berechnung des Abstands zum Erdschatten)
            anti_sun_ra = (sun.ra + math.pi) % (2 * math.pi)
            anti_sun_dec = -sun.dec
            shadow_sep = math.degrees(ephem.separation((anti_sun_ra, anti_sun_dec), (moon.ra, moon.dec)))
            
            # Ist der Mond während der Finsternis über dem Horizont?
            if shadow_sep < 1.6 and math.degrees(moon.alt) > -5:
                if shadow_sep < 0.45:
                    events.append({"time": dt_local, "icon": "🔴", "title": "Totale Mondfinsternis (Blutmond!)", "desc": "Astronomisches Highlight! Der Mond wandert vollständig durch den Kernschatten der Erde und leuchtet blutrot."})
                elif shadow_sep < 0.95:
                    events.append({"time": dt_local, "icon": "🌗", "title": "Partielle Mondfinsternis", "desc": "Der Mond wandert teilweise durch den Kernschatten der Erde (ein Stück 'fehlt')."})
                else:
                    events.append({"time": dt_local, "icon": "🌕", "title": f"Halbschatten-Mondfinsternis ({moon_names.get(month, '')})", "desc": "Der Mond streift den Halbschatten der Erde. Visuell kaum auffällig."})
            else:
                events.append({"time": dt_local, "icon": "🌕", "title": moon_title, "desc": f"Der Mond ist voll beleuchtet. Deep-Sky extrem schwierig.{super_str}"})
                
            curr = fm

        # --- 2b. NEUMOND & SONNENFINSTERNISSE ---
        curr = start_ephem
        while True:
            nm = ephem.next_new_moon(curr)
            if nm > end_ephem: break
            
            # Um zu prüfen, ob es eine lokal sichtbare Sonnenfinsternis gibt, 
            # suchen wir den Punkt der größten Annäherung (± 6 Stunden um den Neumond in 15 Min. Schritten)
            min_sep = 999.0
            best_time = nm
            for offset in range(-24, 25):
                # FIX: Das Ergebnis der Rechnung wieder explizit in ein ephem.Date umwandeln!
                test_time = ephem.Date(nm + offset * 15 * ephem.minute)
                observer.date = test_time
                sun.compute(observer)
                moon.compute(observer)
                sep = math.degrees(ephem.separation(sun, moon))
                if sep < min_sep:
                    min_sep = sep
                    best_time = test_time
            
            # Rechnen mit der besten Zeit
            observer.date = best_time
            sun.compute(observer)
            moon.compute(observer)
            sun_r = math.degrees(sun.radius)
            moon_r = math.degrees(moon.radius)
            
            # Wenn sich Mond und Sonne berühren UND die Sonne über dem Horizont steht
            if min_sep < (sun_r + moon_r) and math.degrees(sun.alt) > 0:
                # Prozentuale Bedeckung berechnen
                coverage = max(0, (sun_r + moon_r - min_sep) / (2 * sun_r)) * 100
                dt_local = self.ephem_to_local(best_time, local_tz)
                
                if coverage > 98:
                    events.append({"time": dt_local, "icon": "🌒", "title": "Totale / Ringförmige Sonnenfinsternis!", "desc": f"Spektakulär! Die Sonne wird an diesem Standort zu {int(coverage)}% vom Mond verdeckt. Höhe: {int(math.degrees(sun.alt))}°."})
                else:
                    events.append({"time": dt_local, "icon": "🌘", "title": "Partielle Sonnenfinsternis", "desc": f"Die Sonne wird an deinem Standort zu {int(coverage)}% vom Mond verdeckt. (Höchste Bedeckung um {dt_local.strftime('%H:%M')} Uhr auf {int(math.degrees(sun.alt))}° Höhe)."})
            else:
                events.append({"time": self.ephem_to_local(nm, local_tz), "icon": "🌑", "title": "Neumond", "desc": "Perfekte Bedingungen! Dunkler Himmel für Deep-Sky."})
                
            curr = nm

        # --- 3. LUNAR X & GOLDENER HENKEL ---
        in_handle = False; in_x = False
        current_time = start_utc
        step = timedelta(hours=1)
        while current_time < end_utc:
            observer.date = current_time
            moon.compute(observer)
            colong = math.degrees(moon.colong); alt = math.degrees(moon.alt)
            
            if 32.0 <= colong <= 34.0:
                if not in_handle and alt > 0:
                    events.append({"time": current_time.astimezone(local_tz), "icon": "🌔", "title": "Goldener Henkel", "desc": f"Das Jura-Gebirge ragt ins Dunkel. Höhe: {alt:.1f}°"})
                    in_handle = True
            else: in_handle = False

            if 358.0 <= colong <= 360.0:
                if not in_x and alt > 0:
                    events.append({"time": current_time.astimezone(local_tz), "icon": "🌓", "title": "Lunar X & V", "desc": f"Licht-Schatten-Effekt ('X' und 'V') am Terminator. Höhe: {alt:.1f}°"})
                    in_x = True
            else: in_x = False
            current_time += step

        # --- 4. PLANETEN OPPOSITIONEN & KONJUNKTIONEN ---
        outer_planets = [
            ("Mars", ephem.Mars(), "🔴", "Mars in Opposition. Hell und nah!"),
            ("Jupiter", ephem.Jupiter(), "🟠", "Jupiter in Opposition. Größter Durchmesser."),
            ("Saturn", ephem.Saturn(), "🪐", "Saturn in Opposition. Ringe leuchten hell."),
            ("Uranus", ephem.Uranus(), "🟢", "Uranus in Opposition. Beste Sichtbarkeit."),
            ("Neptun", ephem.Neptune(), "🔵", "Neptun in Opposition.")
        ]
        for p_name, p_obj, p_icon, p_desc in outer_planets:
            curr = start_utc; seps = []
            while curr <= end_utc + timedelta(days=1):
                observer.date = curr; sun.compute(observer); p_obj.compute(observer)
                seps.append((curr, ephem.separation(sun, p_obj)))
                curr += timedelta(days=1)
            for i in range(1, len(seps)-1):
                if seps[i-1][1] > seps[i][1] < seps[i+1][1] and seps[i][1] > math.radians(150): 
                    dt_local = seps[i][0].astimezone(local_tz).replace(hour=22, minute=0)
                    events.append({"time": dt_local, "icon": p_icon, "title": f"{p_name} Opposition", "desc": p_desc})

        v_obj = ephem.Venus(); curr = start_utc; seps = []
        while curr <= end_utc + timedelta(days=1):
            observer.date = curr; sun.compute(observer); v_obj.compute(observer)
            seps.append((curr, ephem.separation(sun, v_obj)))
            curr += timedelta(days=1)
        for i in range(1, len(seps)-1):
            if seps[i-1][1] < seps[i][1] > seps[i+1][1] and seps[i][1] > math.radians(40):
                dt_local = seps[i][0].astimezone(local_tz).replace(hour=20, minute=0)
                events.append({"time": dt_local, "icon": "⚪", "title": "Venus: Größte Elongation", "desc": "Maximaler scheinbarer Abstand zur Sonne."})

        bright_planets_conj = [
            ("Venus", ephem.Venus(), "⚪"),
            ("Mars", ephem.Mars(), "🔴"),
            ("Jupiter", ephem.Jupiter(), "🟠"),
            ("Saturn", ephem.Saturn(), "🪐")
        ]
        for p_name, p_obj, p_icon in bright_planets_conj:
            in_conj = False; curr = start_utc; best_event = None
            while curr <= end_utc:
                observer.date = curr
                moon.compute(observer); p_obj.compute(observer); sun.compute(observer)
                sep = math.degrees(ephem.separation(moon, p_obj))
                is_visible = math.degrees(moon.alt) > 5 and math.degrees(sun.alt) < -4
                if sep < 6.0 and is_visible:
                    in_conj = True
                    if best_event is None or sep < best_event['sep']:
                        best_event = {"time": curr, "sep": sep, "phase": moon.phase, "alt": math.degrees(moon.alt)}
                else:
                    if in_conj and best_event is not None:
                        if best_event["sep"] <= 4.5: 
                            dt_local = best_event["time"].astimezone(local_tz)
                            events.append({"time": dt_local, "icon": p_icon, "title": f"Mond trifft {p_name}", "desc": f"Schöne Konjunktion! Engster sichtbarer Abstand: {round(best_event['sep'], 1)}°. Mondphase: {int(best_event['phase'])}%. Höhe: {int(best_event['alt'])}°."})
                        best_event = None
                    in_conj = False
                curr += timedelta(hours=1)

        # --- HILFSFUNKTIONEN FÜR RICHTUNG UND STERNBILDER ---
        const_map = {
            'Ari': 'Widder', 'Tau': 'Stier', 'Gem': 'Zwillinge', 'Cnc': 'Krebs',
            'Leo': 'Löwe', 'Vir': 'Jungfrau', 'Lib': 'Waage', 'Sco': 'Skorpion',
            'Sgr': 'Schütze', 'Cap': 'Steinbock', 'Aqr': 'Wassermann', 'Psc': 'Fische',
            'Oph': 'Schlangenträger', 'Cet': 'Walfisch', 'Ori': 'Orion', 'Aur': 'Fuhrmann',
            'Sex': 'Sextant', 'UMa': 'Großer Bär', 'Peg': 'Pegasus', 'Cyg': 'Schwan'
        }

        def get_compass(az_rad):
            """Rechnet Bogenmaß in klassische Kompassrichtungen (N, NO, SW etc.) um"""
            az_deg = math.degrees(az_rad)
            dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
            return dirs[int((az_deg + 11.25) / 22.5) % 16]

        # --- 4b. PLANETEN KONJUNKTIONEN (Alle Planeten) ---
        planet_list = [
            ("Merkur", ephem.Mercury(), "🟤"), ("Venus", ephem.Venus(), "⚪"),
            ("Mars", ephem.Mars(), "🔴"), ("Jupiter", ephem.Jupiter(), "🟠"),
            ("Saturn", ephem.Saturn(), "🪐"), ("Uranus", ephem.Uranus(), "🟢"),
            ("Neptun", ephem.Neptune(), "🔵")
        ]
        
        planet_pairs = []
        for i in range(len(planet_list)):
            for j in range(i+1, len(planet_list)):
                planet_pairs.append((
                    planet_list[i][0], planet_list[i][1], planet_list[j][0], planet_list[j][1], 
                    planet_list[i][2], planet_list[j][2]
                ))
        
        for p1_name, p1_obj, p2_name, p2_obj, icon1, icon2 in planet_pairs:
            curr = start_utc
            in_conj = False
            
            vis_start = None
            vis_end = None
            min_sep_overall = 999.0
            best_vis_event = None # Speichert nur Momente, an denen es ECHT SICHTBAR ist
            
            while curr <= end_utc:
                observer.date = curr
                p1_obj.compute(observer)
                p2_obj.compute(observer)
                
                sep = math.degrees(ephem.separation(p1_obj, p2_obj))
                
                if sep < 6.0: 
                    if not in_conj: 
                        in_conj = True
                        vis_start = None
                        vis_end = None
                        min_sep_overall = 999.0
                        best_vis_event = None
                        
                    # Merke den absoluten Rekordabstand (auch wenn er mittags ist) für den Text
                    if sep < min_sep_overall:
                        min_sep_overall = sep
                        
                    sun.compute(observer)
                    alt1 = math.degrees(p1_obj.alt)
                    alt2 = math.degrees(p2_obj.alt)
                    
                    # Bei extrem hellen Planeten reicht bürgerliche Dämmerung (-3°) und extrem niedrige Höhe (> 2°)
                    is_visible = math.degrees(sun.alt) < -3 and alt1 > 2 and alt2 > 2
                    
                    if is_visible:
                        if vis_start is None: vis_start = curr
                        vis_end = curr
                        
                        # Wir aktualisieren das "Beste Event" NUR mit Zeiten, in denen es auch dunkel ist!
                        # Priorität: Der engste Abstand WÄHREND der Sichtbarkeit
                        if best_vis_event is None or sep < best_vis_event['sep']:
                            best_vis_event = {
                                "time": curr, 
                                "sep": sep, 
                                "alt": max(alt1, alt2)
                            }
                else:
                    if in_conj:
                        # Die Konjunktion ist vorbei. Wir werten sie aus!
                        # WICHTIG: Wurde sie NIE im Dunkeln gesehen (vis_start is None), wird sie IGNORIERT!
                        if vis_start is not None and best_vis_event is not None and min_sep_overall <= 5.0:
                            dt_local = best_vis_event["time"].astimezone(local_tz)
                            
                            observer.date = best_vis_event["time"]
                            p1_obj.compute(observer)
                            const_abbr = ephem.constellation(p1_obj)[0]
                            const_de = const_map.get(const_abbr, const_abbr)
                            direction = get_compass(p1_obj.az)
                            
                            start_str = vis_start.astimezone(local_tz).strftime('%d.%m.')
                            end_str = vis_end.astimezone(local_tz).strftime('%d.%m.')
                            
                            if start_str != end_str:
                                vis_str = f"Sichtbar ca. vom {start_str} bis {end_str}!"
                            else:
                                vis_str = "Nur heute kurz sichtbar!"
                                
                            events.append({
                                "time": dt_local, 
                                "icon": f"{icon1}{icon2}", 
                                "title": f"Konjunktion: {p1_name} & {p2_name}", 
                                "desc": f"Engster Abstand: {round(min_sep_overall, 1)}° | {vis_str}\n(Beste Zeit: {dt_local.strftime('%H:%M')} Uhr auf {int(best_vis_event['alt'])}°, Richtung {direction}, Sternbild {const_de})."
                            })
                        
                    in_conj = False
                
                curr += timedelta(hours=3)

        # --- 4c. PLANETENPARADEN ---
        parade_planets = [
            ("Merkur", ephem.Mercury(), True), ("Venus", ephem.Venus(), True),
            ("Mars", ephem.Mars(), True), ("Jupiter", ephem.Jupiter(), True),
            ("Saturn", ephem.Saturn(), True), ("Uranus", ephem.Uranus(), False),
            ("Neptun", ephem.Neptune(), False)
        ]
        
        obs_parade = ephem.Observer()
        obs_parade.lat, obs_parade.lon = lat_str, lon_str
        obs_parade.horizon = '-6' 
        
        curr = start_ephem
        cooldown_until = start_ephem
        
        while curr < end_ephem:
            if curr < cooldown_until:
                curr += 1; continue
                
            obs_parade.date = curr
            try:
                morning_time = obs_parade.previous_rising(ephem.Sun(), use_center=True)
                evening_time = obs_parade.next_setting(ephem.Sun(), use_center=True)
                check_times = [("Morgenhimmel", morning_time), ("Abendhimmel", evening_time)]
            except: curr += 1; continue
            
            parade_found = False
            for time_name, t_check in check_times:
                obs_parade.date = t_check
                visible_planets, az_list, ra_list, naked_eye_count = [], [], [], 0
                
                for p_name, p_obj, is_naked_eye in parade_planets:
                    p_obj.compute(obs_parade)
                    if math.degrees(p_obj.alt) > 2:
                        visible_planets.append(p_name)
                        ra_list.append(math.degrees(p_obj.ra))
                        az_list.append(p_obj.az) # Radian für Kompass speichern
                        if is_naked_eye: naked_eye_count += 1
                            
                if len(visible_planets) >= 5 or naked_eye_count >= 4:
                    ra_list.sort()
                    gaps = [ra_list[i+1] - ra_list[i] for i in range(len(ra_list)-1)]
                    gaps.append(360.0 - ra_list[-1] + ra_list[0])
                    spread = 360.0 - max(gaps)
                    
                    if spread < 160.0:
                        dt_local = self.ephem_to_local(t_check, local_tz)
                        # Blickrichtung aus dem Minimum/Maximum Azimut ableiten
                        dir_str = f"{get_compass(min(az_list))} bis {get_compass(max(az_list))}"
                        
                        events.append({
                            "time": dt_local, "icon": "🌌", "title": f"Große Planetenparade ({time_name})", 
                            "desc": f"{len(visible_planets)} Planeten ({', '.join(visible_planets)}) reihen sich über {int(spread)}° am Himmel auf. (Blickrichtung: {dir_str})."
                        })
                        parade_found = True
                        cooldown_until = curr + 20
                        break
            
            if not parade_found: curr += 1

        # --- 5. METEORSCHAUER ---
        # Daten: (Name, Monat, Tag, ZHR, Sternbild, RA des Radianten, Dec des Radianten, Beschreibung)
        meteor_showers = [
            ("Quadrantiden", 1, 3, 120, "Bärenhüter", "15:20", "49:00", "Kurzes Maximum, aber potenziell sehr stark."),
            ("Lyriden", 4, 22, 18, "Leier", "18:04", "34:00", "Mittlere Stärke, manchmal helle Feuerkugeln."),
            ("Perseiden", 8, 12, 100, "Perseus", "03:04", "58:00", "Der bekannteste Schauer! Schnelle, helle Meteore."),
            ("Orioniden", 10, 21, 20, "Orion", "06:20", "16:00", "Hervorgerufen durch den Halleyschen Kometen."),
            ("Leoniden", 11, 17, 15, "Löwe", "10:08", "22:00", "Schnelle Meteore, historisch für Stürme bekannt."),
            ("Geminiden", 12, 14, 150, "Zwillinge", "07:28", "33:00", "Der verlässlichste Schauer des Jahres!")
        ]
        
        for name, m, d, zhr, const_name, ra_str, dec_str, desc in meteor_showers:
            peak_date = datetime(current_year, m, d, 23, 0, tzinfo=local_tz)
            observer.date = peak_date.astimezone(pytz.utc)
            
            moon.compute(observer)
            moon_phase = moon.phase
            cond = "Sehr gut" if moon_phase < 20 else "Befriedigend" if moon_phase < 60 else "Schlecht (Mond stört!)"
            
            # Radianten berechnen (Ephem FixedBody)
            radiant = ephem.readdb(f"Radiant,f|S,{ra_str},{dec_str},0,2000")
            radiant.compute(observer)
            rad_alt = math.degrees(radiant.alt)
            direction = get_compass(radiant.az)
            
            if rad_alt < 0:
                rad_str = f"Der Radiant ({const_name}) geht erst später in der Nacht auf (Richtung {direction})."
            else:
                rad_str = f"Der Radiant steht um 23 Uhr ca. {int(rad_alt)}° hoch in Richtung {direction} (Sternbild {const_name})."
            
            events.append({"time": peak_date, "icon": "🌠", "title": f"{name} (Maximum)", "desc": f"ZHR: ~{zhr} Meteore/h. {desc}\n{rad_str} Bedingungen: {cond} ({moon_phase:.0f}% Mondbeleuchtung)."})

        return events

    # ==========================================
    # RENDERING & UI LOGIK
    # ==========================================
    def render_calendar(self, events):
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        months_de = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        current_month = None
        real_current_month = datetime.now().month
        target_scroll_widget = None
        
        if not events: ctk.CTkLabel(self.scroll_frame, text="Keine Ereignisse gefunden.", text_color="gray").pack(pady=50)
            
        existing_list = module_obs_list.load_list()
        existing_keys = [f"{x['iso_date']}_{x['title']}" for x in existing_list]
        
        for ev in events:
            if ev["time"].month != current_month:
                current_month = ev["time"].month
                year = ev["time"].year
                m_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                m_frame.pack(fill="x", pady=(20, 5))
                ctk.CTkLabel(m_frame, text=f"{months_de[current_month]} {year}", font=("Arial", 16, "bold"), text_color="#3b8ed0").pack(anchor="w", padx=5)
                ctk.CTkFrame(m_frame, height=2, fg_color="#3b8ed0").pack(fill="x", padx=5, pady=(2, 10))
                
                summary_text = self._generate_month_summary(year, current_month)
                if summary_text:
                    info_card = ctk.CTkFrame(self.scroll_frame, fg_color="#1a2b3c", border_width=1, border_color="#2980b9", corner_radius=8)
                    info_card.pack(fill="x", padx=5, pady=(0, 10))
                    ctk.CTkLabel(info_card, text="📖 Himmelsjahr-Tipps:", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", padx=10, pady=(10, 2))
                    ctk.CTkLabel(info_card, text=summary_text, font=("Arial", 13, "bold"), text_color="#d1d8e0", justify="left").pack(anchor="w", padx=15, pady=(0, 10))

                if current_month == real_current_month and target_scroll_widget is None:
                    target_scroll_widget = m_frame

            card = ctk.CTkFrame(self.scroll_frame, fg_color="#242424", border_width=1, border_color="#333333", corner_radius=8)
            card.pack(fill="x", padx=5, pady=4)
            card.grid_columnconfigure(0, weight=0, minsize=60)  
            card.grid_columnconfigure(1, weight=0, minsize=80)  
            card.grid_columnconfigure(2, weight=1)              
            card.grid_columnconfigure(3, weight=0, minsize=120) 
            
            icon_container = ctk.CTkFrame(card, width=50, height=50, fg_color="transparent")
            icon_container.grid(row=0, column=0, padx=(10, 5), pady=10)
            icon_container.pack_propagate(False)
            icon_lbl = ctk.CTkLabel(icon_container, text=ev["icon"], font=("Segoe UI Emoji", 28))
            icon_lbl.place(relx=0.5, rely=0.5, anchor="center")
            
            iso_date = ev["time"].strftime("%Y-%m-%d")
            disp_date = ev["time"].strftime("%d.%m.")
            time_str = ev["time"].strftime("%H:%M")
            
            date_frame = ctk.CTkFrame(card, fg_color="transparent")
            date_frame.grid(row=0, column=1, padx=(10, 5), pady=10, sticky="w")
            ctk.CTkLabel(date_frame, text=disp_date, font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w")
            ctk.CTkLabel(date_frame, text=time_str, font=("Arial", 12), text_color="gray").pack(anchor="w")
            
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.grid(row=0, column=2, padx=15, pady=10, sticky="ew")
            ctk.CTkLabel(info_frame, text=ev["title"], font=("Arial", 15, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(info_frame, text=ev["desc"], font=("Arial", 12), text_color="gray", anchor="w", justify="left").pack(fill="x")
            
            ev_key = f"{iso_date}_{ev['title']}"
            if ev_key in existing_keys:
                btn_add = ctk.CTkButton(card, text="✔ Auf Liste", width=100, fg_color="#27ae60", state="disabled")
            else:
                btn_add = ctk.CTkButton(card, text="➕ Zur Liste", width=100, fg_color="#2980b9", hover_color="#3498db")
                def on_add(e_info=ev, b=btn_add, i_d=iso_date, d_d=disp_date, t_s=time_str):
                    module_obs_list.add_event(i_d, d_d, t_s, e_info["title"], e_info["desc"], e_info["icon"])
                    b.configure(text="✔ Auf Liste", fg_color="#27ae60", state="disabled")
                btn_add.configure(command=on_add)
            btn_add.grid(row=0, column=3, padx=15, pady=10, sticky="e")

        self.btn_calc.configure(state="normal")
        self.is_calculating = False
        if target_scroll_widget: self.after(100, lambda: self._do_auto_scroll(target_scroll_widget))

    def _do_auto_scroll(self, target_widget):
        self.update_idletasks()
        try:
            target_y = target_widget.winfo_y()
            canvas = self.scroll_frame._parent_canvas
            bbox = canvas.bbox("all")
            if bbox:
                total_scrollable_height = bbox[3]
                if total_scrollable_height > 0:
                    fraction = target_y / total_scrollable_height
                    canvas.yview_moveto(fraction)
        except Exception: pass