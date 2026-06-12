import os
import json
import re
import csv
import fnmatch
import sys
import random
import webbrowser
import numpy as np
from logic_mobile import MobileExporter
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun, get_body
import astropy.units as u
from astropy.time import Time, TimeDelta
from datetime import datetime, timedelta

from logic_scanner import LibraryScanner
from logic_export import HTMLExporter
from logic_atlas import AtlasExporter

from utils import (
    open_system_folder, open_url, clean_name_for_wiki, read_fits_coords,
    normalize_string, get_fits_stats, format_telescope, generate_pretty_name
)

MESSIER_TYPES = {
    "Galaxy": [31, 32, 33, 49, 51, 58, 59, 60, 61, 63, 64, 65, 66, 74, 77, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 94, 95, 96, 98, 99, 100, 101, 102, 104, 105, 106, 108, 109, 110],
    "Nebula": [1, 8, 16, 17, 20, 27, 42, 43, 57, 76, 78, 97],
    "Cluster": [2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 30, 34, 35, 36, 37, 38, 39, 41, 44, 45, 46, 47, 48, 50, 52, 53, 54, 55, 56, 62, 67, 68, 69, 70, 71, 72, 75, 79, 80, 92, 93, 103, 107],
    "Other": [40, 73] 
}
CALDWELL_TYPES = {
    "Galaxy": [4, 5, 7, 12, 18, 21, 23, 24, 29, 30, 32, 35, 36, 38, 40, 43, 44, 45, 48, 51, 52, 53, 55, 56, 60, 61, 62, 63, 65, 66, 70, 72, 77, 83, 85, 87, 88, 89, 93, 101, 103, 108],
    "Nebula": [1, 2, 3, 6, 8, 9, 11, 15, 19, 20, 25, 26, 27, 33, 34, 37, 39, 46, 49, 57, 59, 67, 68, 69, 74, 80, 90, 92, 98, 99, 100, 109],
    "Cluster": [10, 13, 14, 16, 17, 22, 28, 31, 41, 42, 47, 50, 54, 58, 64, 71, 73, 75, 76, 78, 79, 81, 82, 84, 86, 91, 94, 95, 96, 97, 102, 104, 105, 106, 107],
    "Other": []
}
KEYWORD_MAPPING = {
    "Galaxy": ["galaxy", "galaxie", "triangulum", "andromeda", "sombrero", "whirlpool", "pinwheel", "bode", "cigar", "zagarre", "sunflower", "black eye", "tadpole"],
    "Nebula": ["nebula", "nebel", "remnant", "snr", "supernova", "planetary", "veil", "rosette", "lagoon", "orion", "horsehead", "pferdekopf", "california", "cocoon", "iris", "north america", "pelican", "soul", "heart", "wizard", "helix", "dumbbell", "ring", "bubble", "pacman", "tulip", "crescent", "jellyfish", "monkey", "cone", "christmas", "flaming", "tarantula", "carina", "running", "chicken"],
    "Cluster": ["cluster", "haufen", "pleiades", "plejaden", "hyades", "hyaden", "beehive", "krippe", "double cluster", "hertszprung", "globular", "kugel", "omega", "centauri", "coat", "hanger"],
    "Comet": ["comet", "komet", "c/", "p/", "12p", "13p", "tsuchinshan"], 
    "Other": ["moon", "mond", "sun", "sonne", "asterism", "star", "stern", "yso"] 
}

class AstroLogic:
    def __init__(self):
        self.app_path = self._get_app_path()
        self.config_file = os.path.join(self.app_path, "astroarchive_config.json")
        self.catalog_file = os.path.join(self.app_path, "catalogs.json")
        self.notes_file = os.path.join(self.app_path, "user_notes.json")
        self.cache_file = os.path.join(self.app_path, "coordinate_cache.json") 
        
        self.sort_settings = {} 
        self.base_folder = self.load_config()
        
        self.caldwell_map = {}
        self.common_names = {}
        self.constellation_names = {} 
        self.includes_map = {} 
        self.reverse_caldwell_map = {}
        self.user_notes = {} 
        self.coord_cache = {} 
        
        self.list_cache = {}
        
        self.load_catalogs()
        self.load_notes()
        self.load_cache() 
        
        self.index = {}
        self.constellations = {}
        
        self.scanner = LibraryScanner(self.includes_map)
        self.exporter = HTMLExporter(self)
        self.mobile_exporter = MobileExporter(self)
        self.atlas_exporter = AtlasExporter(self)

    def _get_app_path(self):
        if getattr(sys, 'frozen', False): return os.path.dirname(sys.executable)
        else: return os.path.dirname(os.path.abspath(__file__))
    
    def get_smartsuite_path(self):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        return data.get("smartsuite_path", "")

    def set_smartsuite_path(self, path):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        data["smartsuite_path"] = path
        with open(self.config_file, "w") as f: json.dump(data, f)        

    def get_astrometry_key(self):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        return data.get("astrometry_key", "")

    def set_astrometry_key(self, key):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        data["astrometry_key"] = key
        with open(self.config_file, "w") as f: json.dump(data, f)
        
    def get_astap_path(self):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        return data.get("astap_path", "")

    def set_astap_path(self, path):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        data["astap_path"] = path
        with open(self.config_file, "w") as f: json.dump(data, f, indent=4)

    def get_aladin_path(self):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        return data.get("aladin_path", "")

    def set_aladin_path(self, path):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        data["aladin_path"] = path
        with open(self.config_file, "w") as f: json.dump(data, f, indent=4)

    def run_local_solve_and_aladin(self, file_path, coords_str=None, callback=None):
        astap_exe = self.get_astap_path()
        aladin_exe = self.get_aladin_path()
        
        if not astap_exe or not os.path.exists(astap_exe) or not aladin_exe or not os.path.exists(aladin_exe):
            if callback: callback("Fehler: Pfade fehlen!", False)
            return

        def task():
            if callback: callback("Bereite Bild vor...", True)
            try:
                import subprocess
                import numpy as np
                from PIL import Image
                from astropy.io import fits
                import traceback
                import logging
                import os
                import shutil
                import requests
                
                base, ext = os.path.splitext(file_path)
                
                temp_dir = os.path.join(self.app_path, "temp")
                os.makedirs(temp_dir, exist_ok=True) 
                
                script_path = os.path.join(temp_dir, "temp_aladin_macro.ajs")
                temp_solve_fits = os.path.join(temp_dir, "temp_astap_input.fits")
                wcs_path = os.path.join(temp_dir, "temp_astap_input.wcs")
                
                temp_r = os.path.join(temp_dir, "Red.fits")
                temp_g = os.path.join(temp_dir, "Green.fits")
                temp_b = os.path.join(temp_dir, "Blue.fits")
                
                is_jpg = ext.lower() in [".jpg", ".jpeg", ".png"]
                
                if os.path.exists(wcs_path):
                    try: os.remove(wcs_path)
                    except: pass
                
                if is_jpg:
                    try:
                        img_color = Image.open(file_path).convert('RGB')
                        img_data_16 = np.array(img_color.convert('L'), dtype=np.uint16) * 257 
                        fits.PrimaryHDU(data=np.flip(img_data_16, axis=0)).writeto(temp_solve_fits, overwrite=True)
                        estimated_fov = round((img_color.height * 2.4) / 3600, 2)
                    except Exception as e:
                        logging.error(f"Fehler JPG Kopie: {e}")
                        if callback: callback("Bildlese-Fehler!", False)
                        return
                else:
                    try:
                        shutil.copy2(file_path, temp_solve_fits)
                        estimated_fov = 2.5
                    except Exception as e:
                        logging.error(f"Fehler FITS Kopie: {e}")
                        return
                
                solved = False
                fov_list = [str(estimated_fov), "1.3", "2.5", "3.8", "5.0", "7.5", "10.0", "15.0", "0.7"] if is_jpg else [""]
                
                for fov in fov_list:
                    if callback: callback(f"ASTAP: Suche Sterne ({fov}°)..." if fov else "Löse mit ASTAP...", True)
                    if os.path.exists(wcs_path):
                        try: os.remove(wcs_path)
                        except: pass
                        
                    astap_cmd = [astap_exe, "-f", temp_solve_fits, "-r", "180"]
                    if fov: astap_cmd.extend(["-fov", fov])
                    
                    res = subprocess.run(astap_cmd, capture_output=True, text=True, timeout=120)
                    if res.returncode == 0 and os.path.exists(wcs_path):
                        solved = True
                        break
                        
                if not solved:
                    logging.warning(f"ASTAP fehlgeschlagen für {file_path}. Starte Astrometry Cloud-Fallback.")
                    api_key = self.get_astrometry_key()
                    if not api_key:
                        if callback: callback("ASTAP gescheitert (Kein API-Key für Cloud)", False)
                        return
                        
                    try:
                        from logic_astrometry import AstrometryClient
                        client = AstrometryClient(api_key)
                        
                        if callback: callback("Cloud: Logge ein...", True)
                        success, msg = client.login()
                        
                        if success:
                            if callback: callback("Cloud: Lade Bild hoch...", True)
                            sub_id, msg = client.upload_file(temp_solve_fits)
                            
                            if sub_id:
                                if callback: callback(f"Cloud: Warte auf Job (Sub: {sub_id})...", True)
                                job_id = client.wait_for_job(sub_id, timeout=300)
                                
                                if job_id:
                                    if callback: callback(f"Cloud rechnet (Job: {job_id})...", True)
                                    is_solved = client.wait_for_calibration(job_id, timeout=600)
                                    
                                    if is_solved:
                                        if callback: callback("Cloud: Lösung gefunden! Lade WCS...", True)
                                        wcs_res = requests.get(f"https://nova.astrometry.net/wcs_file/{job_id}")
                                        with open(wcs_path, "wb") as f:
                                            f.write(wcs_res.content)
                                        solved = True
                                    else:
                                        logging.error("Cloud: Calibration failed.")
                                else:
                                    logging.error("Cloud: Timeout waiting for job.")
                            else:
                                logging.error(f"Cloud: Upload failed: {msg}")
                        else:
                            logging.error(f"Cloud: Login failed: {msg}")
                            
                    except ImportError:
                        logging.error("logic_astrometry.py fehlt!")
                    except Exception as e:
                        logging.error(f"Cloud Fehler: {e}\n{traceback.format_exc()}")
                        
                if not solved:
                    if callback: callback("Weder ASTAP noch Cloud konnten lösen!", False)
                    return
                
                if callback: callback("Erstelle Aladin Ebenen...", True)
                is_color = False
                try:
                    clean_head = fits.Header()
                    try:
                        with fits.open(wcs_path, ignore_missing_end=True) as h:
                            for k, v in h[0].header.items():
                                if k not in ['COMMENT', 'HISTORY', 'SIMPLE', 'BITPIX', 'NAXIS', 'NAXIS1', 'NAXIS2', 'NAXIS3'] and not k.startswith('WARN'):
                                    clean_head[k] = v
                    except:
                        with open(wcs_path, "r", encoding="ascii", errors="ignore") as f:
                            for line in f:
                                l = line.strip('\r\n')
                                if "=" not in l or l.startswith(("COMMENT", "WARNING", "HISTORY", "SIMPLE", "BITPIX", "NAXIS")): continue
                                try: clean_head.append(fits.Card.fromstring(l.ljust(80)[:80]))
                                except: pass
                                
                    if is_jpg:
                        img_data = np.array(img_color)
                        fits.PrimaryHDU(data=np.flip(img_data[:,:,0], axis=0), header=clean_head).writeto(temp_r, overwrite=True)
                        fits.PrimaryHDU(data=np.flip(img_data[:,:,1], axis=0), header=clean_head).writeto(temp_g, overwrite=True)
                        fits.PrimaryHDU(data=np.flip(img_data[:,:,2], axis=0), header=clean_head).writeto(temp_b, overwrite=True)
                        is_color = True
                    else:
                        with fits.open(file_path, mode='readonly') as hdul:
                            data_found = None
                            for hdu in hdul:
                                if hdu.data is not None and len(hdu.data.shape) >= 2:
                                    data_found = hdu.data
                                    break
                            
                            if data_found is not None and len(data_found.shape) == 3 and data_found.shape[0] == 3:
                                fits.PrimaryHDU(data=data_found[0], header=clean_head).writeto(temp_r, overwrite=True)
                                fits.PrimaryHDU(data=data_found[1], header=clean_head).writeto(temp_g, overwrite=True)
                                fits.PrimaryHDU(data=data_found[2], header=clean_head).writeto(temp_b, overwrite=True)
                                is_color = True
                            else:
                                fits.PrimaryHDU(data=data_found, header=clean_head).writeto(temp_r, overwrite=True)
                                is_color = False

                except Exception as e:
                    logging.error(f"Fehler nach Solve: {e}\n{traceback.format_exc()}")
                    if callback: callback("Fehler beim Erstellen der Ebenen!", False)
                    return

                macro_content = "reset\n"
                if coords_str and "---" not in coords_str:
                    clean_c = coords_str.replace('RA:', '').replace('DEC:', '').replace('|', '').strip()
                    macro_content += f"{clean_c}\n"
                
                if is_color:
                    macro_content += f'load "{temp_r.replace("\\", "/")}"\n'
                    macro_content += f'load "{temp_g.replace("\\", "/")}"\n'
                    macro_content += f'load "{temp_b.replace("\\", "/")}"\n'
                    macro_content += "sync\n" 
                    macro_content += "pause 1\n"
                    macro_content += 'rgb Red Green Blue\n'
                    macro_content += 'rm Red\n'
                    macro_content += 'rm Green\n'
                    macro_content += 'rm Blue\n'
                else:
                    macro_content += f'load "{temp_r.replace("\\", "/")}"\n'
                
                try:
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write(macro_content)
                except PermissionError:
                    script_path = os.path.join(temp_dir, f"temp_aladin_macro_{random.randint(100,999)}.ajs")
                    with open(script_path, "w", encoding="utf-8") as f:
                        f.write(macro_content)
                
                if callback: callback("Starte Aladin...", True)
                subprocess.Popen([aladin_exe, "-exec", script_path])
                if callback: callback("Bild an Aladin übergeben!", True)
                
            except Exception as e:
                import traceback
                logging.error(f"KRITISCHER FEHLER:\n{traceback.format_exc()}")
                if callback: callback(f"Absturz: {e}", False) 

        import threading
        threading.Thread(target=task, daemon=True).start()
        
    def get_export_path(self):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        return data.get("export_path", "")

    def set_export_path(self, path):
        data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f: data = json.load(f)
        data["export_path"] = path
        with open(self.config_file, "w") as f: json.dump(data, f)
        
    def get_location(self):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        return data.get("latitude", 47.8), data.get("longitude", 10.8)

    def set_location(self, lat, lon):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
        data["latitude"] = float(lat)
        data["longitude"] = float(lon)
        with open(self.config_file, "w") as f: json.dump(data, f, indent=4)    

    def load_config(self):
        self.sort_settings = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.sort_settings = data.get("sort_settings", {})
                    return data.get("base_folder", "")
            except: return ""
        return ""

    def save_config(self, folder_path):
        self.base_folder = folder_path
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: data = json.load(f)
            except: pass
            
        data["base_folder"] = self.base_folder
        data["sort_settings"] = self.sort_settings
        
        with open(self.config_file, "w") as f: json.dump(data, f)

    def save_sort_state(self, catalog_name, column, reverse):
        self.sort_settings[catalog_name] = {"col": column, "rev": reverse}
        self.save_config(self.base_folder)

    def load_catalogs(self):
        if os.path.exists(self.catalog_file):
            try:
                with open(self.catalog_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.caldwell_map = data.get("caldwell", {})
                    self.common_names = data.get("common_names", {})
                    self.constellation_names = data.get("constellations", {})
                    self.includes_map = data.get("includes", {})
            except: pass
        self.reverse_caldwell_map = {}
        for c_num, ngc_name in self.caldwell_map.items():
            clean_ngc = normalize_string(ngc_name)
            self.reverse_caldwell_map[clean_ngc] = c_num

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f: self.coord_cache = json.load(f)
            except: self.coord_cache = {}

    def save_to_cache(self, obj_name, ra_dec_str, ra_deg, dec_deg):
        clean_key = normalize_string(obj_name)
        if not clean_key:
            clean_key = obj_name.lower().strip()
            
        self.coord_cache[clean_key] = {"coords_str": ra_dec_str, "ra": ra_deg, "dec": dec_deg}
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f: json.dump(self.coord_cache, f, indent=4)
        except: pass
    
    def delete_from_cache(self, obj_name):
        clean_key = normalize_string(obj_name)
        keys_to_delete = [k for k in self.coord_cache.keys() if k == clean_key]
        if not keys_to_delete:
            if clean_key.startswith("m") or clean_key.startswith("c"):
                alt_key = clean_key[1:]
                keys_to_delete = [k for k in self.coord_cache.keys() if k == alt_key]
        if keys_to_delete:
            for k in keys_to_delete:
                del self.coord_cache[k]
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f: 
                    json.dump(self.coord_cache, f, indent=4)
                return True
            except: return False
        return False

    def _get_clean_key(self, name):
        match = re.search(r'((?:NGC|M|IC|C)[_\s-]*\d+)', name, re.IGNORECASE)
        if match: return normalize_string(re.sub(r'[_\s-]', '', match.group(1)))
        return normalize_string(name.split("(")[0])

    def _get_all_aliases(self, clean_key):
        valid_keys = set([clean_key])
        for c_num, ngc_name in self.caldwell_map.items():
            c_key = f"c{c_num}"
            norm_ngc = normalize_string(ngc_name)
            if c_key == clean_key or norm_ngc == clean_key:
                valid_keys.add(c_key)
                valid_keys.add(norm_ngc)
                
        current_keys = list(valid_keys)
        for k in current_keys:
            for common_k, common_v in self.common_names.items():
                norm_k = normalize_string(common_k)
                norm_v = normalize_string(common_v)
                if norm_k == k: valid_keys.add(norm_v)
                if norm_v == k: valid_keys.add(norm_k)
                
        return list(valid_keys)

    def load_notes(self):
        if os.path.exists(self.notes_file):
            try:
                with open(self.notes_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.user_notes = {}
                    for k, v in raw.items():
                        # --- FIX: Altlasten heilen ---
                        clean_k = normalize_string(k)
                        if isinstance(v, dict):
                            if "tags" not in v: v["tags"] = []
                            self.user_notes[clean_k] = v
                        else:
                            self.user_notes[clean_k] = {"note": v, "todo": False, "tags": []}
            except: self.user_notes = {}

    def _save_notes_file(self):
        try:
            with open(self.notes_file, "w", encoding="utf-8") as f: json.dump(self.user_notes, f, indent=4)
            return True
        except: return False

    def save_note(self, obj_name, note_text):
        k = self._get_clean_key(obj_name)
        if k not in self.user_notes: self.user_notes[k] = {"note": "", "todo": False, "tags": []}
        self.user_notes[k]["note"] = note_text
        return self._save_notes_file()

    def get_note(self, obj_name):
        return self.user_notes.get(self._get_clean_key(obj_name), {}).get("note", "")

    def set_todo_status(self, obj_name, status):
        clean_key = self._get_clean_key(obj_name)
        valid_keys = self._get_all_aliases(clean_key)
            
        for k in valid_keys:
            if k not in self.user_notes: 
                if status: 
                    self.user_notes[k] = {"note": "", "todo": True, "tags": []}
            else:
                self.user_notes[k]["todo"] = status
                
        if "todo" in self.list_cache: del self.list_cache["todo"]
        return self._save_notes_file()

    def get_todo_status(self, obj_name):
        clean_key = self._get_clean_key(obj_name)
        valid_keys = self._get_all_aliases(clean_key)
            
        for k in valid_keys:
            if self.user_notes.get(k, {}).get("todo", False):
                return True
        return False

    def parse_wims_csv(self, filepath):
        wims_objects = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_name = row.get("Name", "").strip()
                    alt_name = row.get("Alt Name", "").strip()
                    clean_name = re.sub(r'\s+', ' ', raw_name)
                    matched_key = None
                    found_locally = False
                    search_keys = [self._get_clean_key(clean_name)]
                    if alt_name:
                        match_alt = re.search(r'((?:NGC|IC|C)\s*\d+)', alt_name, re.IGNORECASE)
                        if match_alt:
                            search_keys.append(self._get_clean_key(match_alt.group(1)))
                            
                    for sk in search_keys:
                        for idx_key, idx_data in self.index.items():
                            if self._get_clean_key(idx_data["original_name"]) == sk:
                                matched_key = idx_key
                                found_locally = True
                                break
                        if matched_key: break
                        
                    if not matched_key:
                        # --- FIX: Wir nehmen direkt den normierten Key ---
                        matched_key = self._get_clean_key(clean_name)
                        
                    wims_objects.append({
                        "wims_name": clean_name,
                        "alt_name": alt_name,
                        "score": row.get("Score", "0"),
                        "mag": row.get("Magnitude", "---"),
                        "type": row.get("Type", "---"),
                        "ra": float(row["RA"]) if row.get("RA", "").strip() else None,
                        "dec": float(row["Dec"]) if row.get("Dec", "").strip() else None,
                        "matched_key": matched_key,
                        "found": found_locally
                    })
        except Exception as e:
            print(f"WIMS Parse Error: {e}")
        return wims_objects

    def import_wims_objects(self, selected_objs):
        count = 0
        for obj in selected_objs:
            key = obj["matched_key"]
            if key not in self.user_notes:
                self.user_notes[key] = {"note": "", "todo": False, "tags": [], "type": "Auto"}
            self.user_notes[key]["todo"] = True
            
            if obj.get("ra") is not None and obj.get("dec") is not None:
                try:
                    from astropy.coordinates import SkyCoord
                    import astropy.units as u
                    c = SkyCoord(ra=obj["ra"]*u.deg, dec=obj["dec"]*u.deg)
                    c_str = f"RA: {c.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {c.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                    self.save_to_cache(key, c_str, obj["ra"], obj["dec"])
                except: pass
            
            count += 1
            
        self._save_notes_file()
        if "todo" in self.list_cache:
            del self.list_cache["todo"]
        return count
    
    def _get_auto_tags(self, key):
        tags = []
        data = None
        
        if key in self.index:
            data = self.index[key]
        else:
            for idx_key, idx_data in self.index.items():
                norm_idx = normalize_string(idx_key)
                if norm_idx.startswith(key):
                    suffix = norm_idx[len(key):]
                    if not suffix or not suffix[0].isdigit():
                        data = idx_data
                        break
        
        if not data: return tags
        
        pretty = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
        
        otype = self.determine_object_type(pretty)
        if otype and otype != "Other": tags.append(otype)
        
        if "parent" in data and data["parent"]:
             parent_name = self.constellation_names.get(data["parent"], data["parent"].title())
             tags.append(parent_name)
             
        tel = format_telescope(data["telescope"])
        if tel and tel != "Anderes": tags.append(tel)

        match = re.search(r'\bM\s*(\d+)', pretty)
        if match: 
             tags.append("Messier")
             tags.append(f"M {match.group(1)}")
        
        match = re.search(r'\bNGC\s*(\d+)', pretty)
        if match: 
             tags.append("NGC")
             tags.append(f"NGC {match.group(1)}")
        
        match = re.search(r'\bIC\s*(\d+)', pretty)
        if match: 
             tags.append("IC")
             tags.append(f"IC {match.group(1)}")

        match = re.search(r'\bC\s*(\d+)', pretty)
        if match:
             tags.append("Caldwell")
             tags.append(f"C {match.group(1)}")

        if " - " in pretty:
            parts = pretty.split(" - ", 1) 
            if len(parts) > 1:
                names_part = parts[1]
                name_list = names_part.split(",")
                for n in name_list:
                    clean_n = n.strip()
                    if clean_n and "(" not in clean_n:
                        tags.append(clean_n)

        return list(set(tags))

    def get_tags(self, obj_name):
        k = self._get_clean_key(obj_name)
        manual_tags = self.user_notes.get(k, {}).get("tags", [])
        auto_tags = self._get_auto_tags(obj_name) 
        
        return {"auto": auto_tags, "manual": manual_tags}

    def add_tag(self, obj_name, tag):
        k = self._get_clean_key(obj_name)
        if not tag: return False
        auto_tags = self._get_auto_tags(k)
        if tag in auto_tags: return False 
        
        if k not in self.user_notes: 
            self.user_notes[k] = {"note": "", "todo": False, "type": "Auto", "tags": []}
        if "tags" not in self.user_notes[k]: 
            self.user_notes[k]["tags"] = []
            
        if tag not in self.user_notes[k]["tags"]:
            self.user_notes[k]["tags"].append(tag)
            self.list_cache = {} 
            return self._save_notes_file()
        return True

    def remove_tag(self, obj_name, tag):
        k = self._get_clean_key(obj_name)
        if k in self.user_notes and "tags" in self.user_notes[k]:
            if tag in self.user_notes[k]["tags"]:
                self.user_notes[k]["tags"].remove(tag)
                self.list_cache = {}
                return self._save_notes_file()
        return False

    def set_object_type(self, obj_name, new_type):
        k = self._get_clean_key(obj_name)
        if k not in self.user_notes: self.user_notes[k] = {"note": "", "todo": False, "tags": []}
        if new_type == "Auto":
            if "type" in self.user_notes[k]: del self.user_notes[k]["type"]
        else:
            self.user_notes[k]["type"] = new_type
        self.list_cache = {} 
        return self._save_notes_file()

    def get_saved_type(self, obj_name):
        k = self._get_clean_key(obj_name)
        return self.user_notes.get(k, {}).get("type", "Auto")

    def is_date_in_range(self, date_str, start_str, end_str):
        if not date_str or "---" in date_str: return False 
        try:
            obj_date = datetime.strptime(date_str, '%d.%m.%Y')
            if start_str:
                start_date = datetime.strptime(start_str, '%d.%m.%Y')
                if obj_date < start_date: return False
            if end_str:
                end_date = datetime.strptime(end_str, '%d.%m.%Y')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                if obj_date > end_date: return False
            return True
        except ValueError:
            return False 

    def determine_object_type(self, obj_name, common_name=""):
        clean_k = self._get_clean_key(obj_name)
        if clean_k in self.user_notes:
            saved_type = self.user_notes[clean_k].get("type")
            if saved_type and saved_type != "Auto": return saved_type
        
        name_lower = (obj_name + " " + common_name).lower()
        m_match = re.search(r'M\s*(\d+)', obj_name, re.IGNORECASE)
        if m_match:
            num = int(m_match.group(1))
            for type_key, nums in MESSIER_TYPES.items():
                if num in nums: return type_key
        c_match = re.search(r'C\s*(\d+)', obj_name, re.IGNORECASE)
        if not c_match:
            if clean_k in self.reverse_caldwell_map: c_match = re.search(r'\d+', str(self.reverse_caldwell_map[clean_k]))
        if c_match:
            try:
                num = int(c_match.group(1) if isinstance(c_match, re.Match) else c_match.group())
                for type_key, nums in CALDWELL_TYPES.items():
                    if num in nums: return type_key
            except: pass
        for type_key, keywords in KEYWORD_MAPPING.items():
            for kw in keywords:
                if kw in name_lower: return type_key
        return "Other"

    def get_extended_stats(self):
        stats = {
            "cameras": {"Seestar S50": 0, "Seestar S30": 0, "Dwarf II/3": 0, "Unknown": 0},
            "types": {"Galaxy": 0, "Nebula": 0, "Cluster": 0, "Comet": 0, "Other": 0}
        }
        for data in self.index.values():
            tel = data["telescope"]
            if tel == "seestar": stats["cameras"]["Seestar S50"] += 1
            elif tel == "s30": stats["cameras"]["Seestar S30"] += 1
            elif tel == "dwarf": stats["cameras"]["Dwarf II/3"] += 1
            else: stats["cameras"]["Unknown"] += 1
            pretty = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
            otype = self.determine_object_type(pretty, pretty) 
            if otype in stats["types"]: stats["types"][otype] += 1
            else: stats["types"]["Other"] += 1
        return stats

    def get_random_object(self):
        if not self.index: return None
        keys = list(self.index.keys())
        random_key = random.choice(keys)
        data = self.index[random_key]
        return generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)

    def generate_html_report(self, save_path, filter_mode="Alle", filter_value=None, as_gallery=False, date_start=None, date_end=None):
        return self.exporter.generate_report(save_path, filter_mode, filter_value, as_gallery, date_start, date_end)
        
    def export_mobile(self, save_path):
        return self.mobile_exporter.generate(save_path)

    def get_map_objects_filtered(self, date_start=None, date_end=None):
        map_objects = []
        for key, data in self.index.items():
            if date_start or date_end:
                c, dt, _ = get_fits_stats(data["path"])
                if not self.is_date_in_range(dt, date_start, date_end): continue
            
            coords_ok = False
            ra_dec = None; dec_dec = None
            if data["fits_sample"]:
                _, r, d, ok = read_fits_coords(data["fits_sample"])
                if ok: ra_dec = r; dec_dec = d; coords_ok = True
            
            if not coords_ok:
                pretty = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                search_clean = pretty
                match_id = re.search(r'((?:NGC|M|IC|C)\s*\d+)', pretty, re.IGNORECASE)
                if match_id: search_clean = match_id.group(1)
                else: search_clean = pretty.split("-")[0].split("(")[0].strip()
                clean_k = normalize_string(search_clean)
                if clean_k in self.coord_cache:
                    cached = self.coord_cache[clean_k]
                    ra_dec = cached["ra"]; dec_dec = cached["dec"]; coords_ok = True
            
            if coords_ok:
                p_name = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                short_name = p_name.split("-")[0].split("(")[0].strip()
                map_objects.append({"ra": ra_dec, "dec": dec_dec, "name": short_name, "full_id": key})
        return map_objects

    def get_todo_objects(self):
        if "todo" in self.list_cache: return self.list_cache["todo"]
        results = []
        seen_keys = set() 
        
        lat, lon = self.get_location() 
        try:
            from astropy.time import Time
            from astropy.coordinates import EarthLocation
            import astropy.units as u
            loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
            lst = Time.now().sidereal_time('apparent', longitude=loc.lon).hour
        except Exception:
            lst = None
        
        for note_key, data in self.user_notes.items():
            if data.get("todo", False):
                valid_keys = self._get_all_aliases(note_key)
                
                if any(vk in seen_keys for vk in valid_keys): continue
                seen_keys.update(valid_keys)
                
                obj_display_name = generate_pretty_name(note_key, self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                telescope = "Geplant"; fits_count = 0; date_str = "---"; found = False; path = None; img = None; internal_id = note_key 
                images = []
                fits_sample = None
                
                for idx_key, idx_data in self.index.items():
                    if self._get_clean_key(idx_data["original_name"]) in valid_keys:
                        found = True; telescope = format_telescope(idx_data["telescope"]); path = idx_data["path"]; img = idx_data["image"]
                        images = idx_data.get("images", [])
                        c, dt, ts = get_fits_stats(path); fits_count = c; date_str = dt
                        obj_display_name = generate_pretty_name(idx_data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                        internal_id = idx_key
                        fits_sample = idx_data.get("fits_sample")
                        break 
                        
                otype = self.determine_object_type(obj_display_name, obj_display_name)
                
                ra_val = None
                dec_val = None 
                
                if fits_sample:
                    try:
                        from utils import read_fits_coords
                        _, r, d, ok = read_fits_coords(fits_sample)
                        if ok: ra_val = r; dec_val = d
                    except: pass
                
                clean_k = self._get_clean_key(obj_display_name)
                if ra_val is None:
                    for vk in valid_keys:
                        if vk in self.coord_cache:
                            ra_val = self.coord_cache[vk]["ra"]
                            dec_val = self.coord_cache[vk]["dec"]
                            break
                    if ra_val is None and clean_k in self.coord_cache:
                        ra_val = self.coord_cache[clean_k]["ra"]
                        dec_val = self.coord_cache[clean_k]["dec"]

                time_to_transit = 99
                score = 0 
                
                if ra_val is not None and dec_val is not None:
                    if lst is not None:
                        ra_h = ra_val / 15.0
                        time_to_transit = (ra_h - lst) % 24

                    max_alt = 90 - abs(lat - dec_val)
                    alt_score = max(0, min(50, (max_alt - 15) / 65 * 50))

                    moon_sep, moon_phase = self.get_moon_info(ra_val, dec_val)
                    if moon_sep is not None:
                        dist_factor = max(0, (90 - moon_sep) / 90)
                        penalty = (moon_phase / 100) * dist_factor * 50
                        moon_score = 50 - penalty
                    else:
                        moon_score = 25 

                    score = int(round(alt_score + moon_score))

                results.append({
                    "name": obj_display_name, "sort_key": obj_display_name, "found": found, 
                    "type": otype, "telescope": telescope, "path": path, "image": img, 
                    "images": images, "fits_count": fits_count, "date": date_str, 
                    "raw_date": 0, "internal_id": internal_id, "time_to_transit": time_to_transit,
                    "score": score 
                })
                
        results.sort(key=lambda x: x.get("sort_key", ""))
        self.list_cache["todo"] = results
        return results

    def scan_library(self):
        self.list_cache = {}
        self.index, self.constellations, msg = self.scanner.scan(self.base_folder)
        return msg

    def get_library_stats(self):
        found_ids = set()
        for key in self.index.keys():
            norm = normalize_string(key)
            m_match = re.search(r'm(\d+)', norm)
            if m_match: found_ids.add(f"m{m_match.group(1)}")
            
            c_match = re.search(r'c(\d+)', norm) 
            if c_match: found_ids.add(f"c{c_match.group(1)}")
            
            ngc_match = re.search(r'ngc(\d+)', norm) 
            if ngc_match: found_ids.add(f"ngc{ngc_match.group(1)}")
            
        m_count = 0
        for i in range(1, 111):
            m_id = f"m{i}"
            if m_id in found_ids: 
                m_count += 1
            else:
                for k, v in self.common_names.items():
                    if normalize_string(v) == m_id and normalize_string(k) in found_ids:
                        m_count += 1; break
                    if normalize_string(k) == m_id and normalize_string(v) in found_ids:
                        m_count += 1; break
                        
        c_count = 0
        for i in range(1, 110):
            c_id = f"c{i}"
            if c_id in found_ids: c_count += 1
            elif str(i) in self.caldwell_map:
                ngc_alias = normalize_string(self.caldwell_map[str(i)])
                if ngc_alias in found_ids: c_count += 1
        return {"messier": {"count": m_count, "total": 110, "pct": m_count/110 if m_count > 0 else 0}, "caldwell": {"count": c_count, "total": 109, "pct": c_count/109 if c_count > 0 else 0}}

    def get_missing_objects(self, catalog_name):
        found_ids = set()
        for key in self.index.keys():
            norm = normalize_string(key)
            m_match = re.search(r'm(\d+)', norm); 
            if m_match: found_ids.add(f"m{m_match.group(1)}")
            c_match = re.search(r'c(\d+)', norm); 
            if c_match: found_ids.add(f"c{c_match.group(1)}")
            ngc_match = re.search(r'ngc(\d+)', norm); 
            if ngc_match: found_ids.add(f"ngc{ngc_match.group(1)}")
            
        missing_list = []
        if catalog_name == "Messier":
            for i in range(1, 111):
                m_id = f"m{i}"
                is_found = False
                
                if m_id in found_ids: 
                    is_found = True
                else:
                    for k, v in self.common_names.items():
                        if normalize_string(v) == m_id and normalize_string(k) in found_ids:
                            is_found = True; break
                        if normalize_string(k) == m_id and normalize_string(v) in found_ids:
                            is_found = True; break
                            
                if not is_found:
                    missing_list.append(generate_pretty_name(f"M {i}", self.caldwell_map, self.reverse_caldwell_map, self.common_names))
                    
        elif catalog_name == "Caldwell":
            for i in range(1, 110):
                c_id = f"c{i}"
                is_found = False
                
                if c_id in found_ids: 
                    is_found = True
                elif str(i) in self.caldwell_map:
                    alias_name = normalize_string(self.caldwell_map[str(i)])
                    if alias_name in found_ids: 
                        is_found = True
                
                if not is_found:
                    name = generate_pretty_name(f"C {i}", self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                    missing_list.append(name)
                    
        return missing_list

    def open_system_folder(self, path): open_system_folder(path)
    def open_url(self, url): open_url(url)

    def get_available_constellations(self):
        if not self.constellations: return []
        return sorted([self.constellation_names.get(k, k.title()) for k in self.constellations.keys()])

    def open_legacy_survey(self, ra, dec):
        if ra is None or dec is None: return
        open_url(f"https://www.legacysurvey.org/viewer/?ra={ra:.4f}&dec={dec:.4f}&layer=unwise-neo6&zoom=10")
    
    def open_aladin(self, ra, dec):
        if ra is None or dec is None: return
        open_url(f"https://aladin.u-strasbg.fr/AladinLite/?target={ra:.4f}+{dec:.4f}&fov=1.0&survey=P%2FDSS2%2Fcolor")
    
    def get_constellation_objects(self, const_name):
        cache_key = f"const_{const_name}"
        if cache_key in self.list_cache: return self.list_cache[cache_key]
        results = []
        c_key = const_name.lower() 
        for internal, display in self.constellation_names.items():
            if const_name == display: c_key = internal; break
        if c_key not in self.constellations: return []
        for item in self.constellations[c_key]:
            obj_name_lower = item['name'].lower().strip()
            if obj_name_lower in self.index:
                data = self.index[obj_name_lower]
                fits_count, latest_date, ts = get_fits_stats(data["path"])
                pretty_name = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                display_name = f"{pretty_name} ({format_telescope(data['telescope'])})"
                otype = self.determine_object_type(pretty_name, pretty_name)
                results.append({
                    "name": display_name, "sort_key": pretty_name, "found": True, "type": otype, 
                    "telescope": format_telescope(data["telescope"]), "path": data["path"], 
                    "image": data["image"], "images": data.get("images", []), 
                    "fits_count": fits_count, "date": latest_date, "raw_date": ts, "internal_id": obj_name_lower
                })
        results.sort(key=lambda x: x["name"])
        self.list_cache[cache_key] = results
        return results

    def get_catalog_objects(self, catalog_filter):
        if catalog_filter in self.list_cache: return self.list_cache[catalog_filter]
        results = []
        found_map = {}
        for key, data in self.index.items():
            norm = normalize_string(key)
            if norm.startswith("m"):
                m = re.match(r'^m(\d+)', norm)
                if m: found_map[f"m{m.group(1)}"] = (key, data) 
            elif norm.startswith("c"):
                c = re.match(r'^c(\d+)', norm)
                if c and 1 <= int(c.group(1)) <= 109: found_map[f"c{int(c.group(1))}"] = (key, data)
            elif norm.startswith("ngc"):
                n = re.match(r'^ngc(\d+)', norm)
                if n: found_map[f"ngc{n.group(1)}"] = (key, data)
            elif norm.startswith("ic"):
                i_match = re.match(r'^ic(\d+)', norm)
                if i_match: found_map[f"ic{i_match.group(1)}"] = (key, data)

        def build_entry(pretty, sort_val, found_data=None, internal_id=None):
            base = {
                "name": pretty, "sort_key": sort_val, "found": False, "type": "---", 
                "telescope": "---", "path": None, "image": None, "images": [], "fits_count": 0, "date": "---", "raw_date": 0, "internal_id": internal_id
            }
            base["type"] = self.determine_object_type(pretty, pretty)
            if found_data:
                k, d = found_data
                c, dt, ts = get_fits_stats(d["path"])
                base.update({
                    "name": f"{pretty} ({format_telescope(d['telescope'])})", 
                    "found": True, 
                    "telescope": format_telescope(d["telescope"]), 
                    "path": d["path"], 
                    "image": d["image"], 
                    "images": d.get("images", []),
                    "fits_count": c, 
                    "date": dt, 
                    "raw_date": ts, 
                    "internal_id": k
                })
            return base

        if catalog_filter == "Messier":
            for i in range(1, 111):
                found_entry = None
                m_id = f"m{i}"
                if m_id in found_map: found_entry = found_map[m_id]
                else:
                    for k, v in self.common_names.items():
                        if normalize_string(v) == m_id and normalize_string(k) in found_map:
                            found_entry = found_map[normalize_string(k)]; break
                        if normalize_string(k) == m_id and normalize_string(v) in found_map:
                            found_entry = found_map[normalize_string(v)]; break
                
                pretty = f"M {i}"
                found_common = []
                for name, cat_id in self.common_names.items():
                    if normalize_string(cat_id) == m_id: found_common.append(name.title().replace(")", ""))
                if found_common:
                    pretty += " - " + ", ".join(sorted(list(set(found_common))))
                            
                results.append(build_entry(pretty, i, found_entry, internal_id=m_id))
                
        elif catalog_filter == "Caldwell":
            for i in range(1, 110):
                found_entry = None
                c_id = f"c{i}"
                if c_id in found_map: found_entry = found_map[c_id]
                else:
                    if str(i) in self.caldwell_map:
                        alias = normalize_string(self.caldwell_map[str(i)])
                        if alias in found_map: found_entry = found_map[alias]
                            
                pretty = f"C {i}"
                if str(i) in self.caldwell_map:
                    alias_db = str(self.caldwell_map[str(i)]).replace(")", "").replace("(", "")
                    if alias_db.isdigit(): pretty += f" (NGC {alias_db})"
                    else: pretty += f" ({alias_db})"
                    
                found_common = []
                for name, cat_id in self.common_names.items():
                    if normalize_string(cat_id) == c_id: found_common.append(name.title().replace(")", ""))
                if found_common:
                    pretty += " - " + ", ".join(sorted(list(set(found_common))))
                            
                results.append(build_entry(pretty, i, found_entry, internal_id=c_id))
        
        elif catalog_filter == "NGC":
            for k, d in self.index.items(): 
                norm = normalize_string(k)
                if norm.startswith("ngc"):
                    m = re.search(r'\d+', k)
                    num = int(m.group()) if m else 0
                    pretty = generate_pretty_name(d["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                    results.append(build_entry(pretty, num, (k, d)))
            results.sort(key=lambda x: x["sort_key"])
        
        elif catalog_filter == "Alle":
            for k, d in self.index.items():
                def natural_sort_key(s): return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
                pretty = generate_pretty_name(d["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                results.append(build_entry(pretty, natural_sort_key(d["original_name"]), (k, d)))
            results.sort(key=lambda x: x["sort_key"])
        
        self.list_cache[catalog_filter] = results
        return results

    def get_object_data(self, search_term, filter_mode="Alle", show_seestar=True, show_dwarf=True, show_s30=True, exact_match=False):
        clean_search_key = search_term.lower().strip()
        if clean_search_key in self.index:
            best = self.index[clean_search_key]
            pretty_n = generate_pretty_name(best["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
            search_name_clean = pretty_n 
            match_id = re.search(r'((?:NGC|M|IC|C)\s*\d+)', pretty_n, re.IGNORECASE)
            if match_id: search_name_clean = match_id.group(1)
            else: search_name_clean = pretty_n.split("-")[0].split("(")[0].strip()
            
            coords = "RA: --- | DEC: ---"; ra_dec = None; dec_dec = None; status_txt = "Im Archiv gefunden."
            if best["fits_sample"]:
                c_str, r_d, d_d, ok = read_fits_coords(best["fits_sample"])
                if ok: coords = c_str; ra_dec = r_d; dec_dec = d_d; status_txt = "Koordinaten aus FITS (lokal)."
            
            if "---" in coords:
                try:
                    clean_cache_key = normalize_string(search_name_clean)
                    if clean_cache_key in self.coord_cache:
                        cached = self.coord_cache[clean_cache_key]
                        coords = cached["coords_str"]; ra_dec = cached["ra"]; dec_dec = cached["dec"]; status_txt = "Koordinaten aus Cache."
                    else:
                        coord = SkyCoord.from_name(search_name_clean)
                        ra_dec = coord.ra.deg; dec_dec = coord.dec.deg
                        coords = f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                        status_txt = "Koordinaten online abgerufen."
                        self.save_to_cache(search_name_clean, coords, ra_dec, dec_dec)
                except: pass

            note = self.get_note(best["original_name"])
            todo = self.get_todo_status(best["original_name"]) 
            
            result = {"found_locally": True, "internal_id": clean_search_key, "constellation_content": [], "is_constellation": False, "path": best["path"], "image": best["image"], "images": best.get("images", []), "name": pretty_n, "parent_constellation": self.constellation_names.get(best["parent"], best["parent"].title()), "wiki_url": clean_name_for_wiki(best["original_name"]), "status_text": status_txt, "user_note": note, "todo_status": todo, "coords": coords, "ra_decimal": ra_dec, "dec_decimal": dec_dec}
            return result

        target_direct_key = None
        search_norm = normalize_string(search_term)
        for key, data in self.index.items():
            pretty = generate_pretty_name(data["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
            tel_suffix = f" ({format_telescope(data['telescope'])})"
            full_display_name = pretty + tel_suffix
            display_norm = normalize_string(full_display_name)
            if display_norm == search_norm: target_direct_key = key; break
        if target_direct_key: return self.get_object_data(target_direct_key)

        raw_search = search_term.lower().strip()
        norm_search = normalize_string(search_term)
        search_candidates = []
        strict_prefix = None
        if raw_search.isdigit():
            if filter_mode == "Messier": strict_prefix = "m" + raw_search
            elif filter_mode == "NGC": strict_prefix = "ngc" + raw_search
            elif filter_mode == "Caldwell": strict_prefix = "c" + raw_search
        
        c_num = None
        if filter_mode == "Caldwell" and raw_search.isdigit(): c_num = raw_search
        elif norm_search.startswith("c") and norm_search[1:].isdigit(): c_num = norm_search[1:]
        if c_num and c_num in self.caldwell_map: search_candidates.append(normalize_string(self.caldwell_map[c_num]))
        if norm_search in self.reverse_caldwell_map: search_candidates.append(f"c{self.reverse_caldwell_map[norm_search]}")
        for common, cid in self.common_names.items():
            c_low = common.lower()
            norm_c = normalize_string(common)
            if c_low == raw_search or norm_c == norm_search or fnmatch.fnmatch(c_low, raw_search):
                search_candidates.append(normalize_string(cid))
            elif raw_search in c_low:
                search_candidates.append(normalize_string(cid))
            elif c_low in raw_search:
                if len(c_low) > 3 or re.search(r'\b' + re.escape(c_low) + r'\b', raw_search):
                    search_candidates.append(normalize_string(cid))

        pretty_fallback_name = generate_pretty_name(search_term, self.caldwell_map, self.reverse_caldwell_map, self.common_names)
        
        result = {"found_locally": False, "path": None, "image": None, "images": [], "coords": "RA: --- | DEC: ---", "ra_decimal": None, "dec_decimal": None, "wiki_url": "", "name": pretty_fallback_name, "status_text": "", "is_constellation": False, "constellation_content": [], "parent_constellation": None, "user_note": "", "todo_status": False}
        
        found_const = None
        if not exact_match and filter_mode in ["Sternbild", "Alle"]:
            if raw_search in self.constellations: found_const = raw_search
            else:
                for internal, display in self.constellation_names.items():
                    if raw_search in display.lower(): found_const = internal; break
        if found_const:
            result.update({"found_locally": True, "is_constellation": True, "name": self.constellation_names.get(found_const, found_const.title()), "status_text": "Sternbild gefunden.", "wiki_url": f"https://de.wikipedia.org/wiki/{found_const.capitalize()}"})
            raw_c = self.constellations.get(found_const, []) 
            result["constellation_content"] = [item["name"] for item in raw_c if (item["type"] == "seestar" and show_seestar) or (item["type"] == "dwarf" and show_dwarf) or (item["type"] == "s30" and show_s30)]
            if raw_c: result["path"] = os.path.dirname(self.index[raw_c[0]["name"].lower()]["path"])
            else: result["status_text"] = "Sternbild bekannt, aber keine lokalen Dateien."; result["found_locally"] = False 
            return result

        is_id_search = re.search(r'^[a-zA-Z]+\s*\d+$', raw_search) is not None
        possible = []
        for key, data in self.index.items():
            match = False 
            tag_match = False
            idx_clean_key = normalize_string(key)
            all_tags_dict = self.get_tags(key)
            combined_tags = all_tags_dict["auto"] + all_tags_dict["manual"]
            for t in combined_tags:
                if raw_search in t.lower():
                    tag_match = True
                    break
            
            check = True
            if search_candidates: check = False
            
            if tag_match:
                match = True 
            
            if not match: 
                if filter_mode == "Messier" and not key.startswith("m"): continue
                if filter_mode == "NGC" and not key.startswith("ngc"): continue
                if filter_mode == "Caldwell" and not key.startswith("c"): continue
                
                norm_k = normalize_string(key)
                
                if exact_match:
                    for alias in search_candidates:
                        if alias == norm_k: match = True; break
                        if norm_k.startswith(alias):
                            suffix = norm_k[len(alias):]
                            if not suffix or not suffix[0].isdigit(): match = True; break
                    
                    if not match:
                        if norm_k.startswith(norm_search):
                            suffix = norm_k[len(norm_search):]
                            if not suffix or not suffix[0].isdigit(): match = True
                else:
                    if strict_prefix and norm_k.startswith(strict_prefix):
                        suffix = norm_k[len(strict_prefix):]
                        if not suffix or not suffix[0].isdigit(): match = True
                    elif fnmatch.fnmatch(key, raw_search): match = True
                    elif is_id_search:
                        if norm_k == norm_search: 
                            match = True
                        elif norm_k.startswith(norm_search):
                            suffix = norm_k[len(norm_search):]
                            if not suffix or not suffix[0].isdigit(): match = True
                    else:
                        if norm_search in norm_k: match = True
                    
                    if not match:
                        for alias in search_candidates:
                            if alias == norm_k: match = True; break 
                            if norm_k.startswith(alias) and (len(norm_k) == len(alias) or not norm_k[len(alias)].isdigit()): match = True; break

            if match:
                skip = False
                if data["telescope"] == "seestar" and not show_seestar: skip = True
                if data["telescope"] == "dwarf" and not show_dwarf: skip = True
                if data["telescope"] == "s30" and not show_s30: skip = True
                if not skip: possible.append(key)

        if possible:
            result["found_locally"] = True
            final_candidates = list(possible)
            if len(possible) > 1:
                telescope_found_in_search = False
                filtered_candidates = []
                for k in possible:
                    tel_str = format_telescope(self.index[k]["telescope"]).lower()
                    if tel_str in raw_search: filtered_candidates.append(k); telescope_found_in_search = True
                if telescope_found_in_search and filtered_candidates: final_candidates = filtered_candidates
            content_list = []
            for k in final_candidates:
                base_name = generate_pretty_name(self.index[k]["original_name"], self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                tel_suffix = f" ({format_telescope(self.index[k]['telescope'])})"
                content_list.append(base_name + tel_suffix)
            result["constellation_content"] = sorted(content_list)
            unique_paths = set()
            for k in final_candidates: p = self.index[k]["path"]; unique_paths.add(os.path.normpath(p).lower())
            paths_match = len(unique_paths) == 1
            target_key = None
            if len(final_candidates) == 1: 
                target_key = final_candidates[0]
            elif paths_match: 
                target_key = final_candidates[0]

            if len(final_candidates) > 1 and not target_key: 
                result.update({"is_constellation": True, "status_text": f"{len(final_candidates)} Treffer gefunden.", "name": f"Suche: '{search_term}'"})
            else:
                if not target_key: target_key = final_candidates[0]
                return self.get_object_data(target_key)
        
        if not result["coords"] or "---" in result["coords"]:
            try:
                s_for = search_term
                match_id = re.search(r'^((?:NGC|IC|M|C)\s*\d+)', search_term, re.IGNORECASE)
                if match_id:
                    s_for = match_id.group(1).upper()
                else:
                    if " - " in s_for: s_for = s_for.split(" - ")[0].strip()
                    if "(" in s_for: s_for = s_for.split("(")[0].strip()

                c_check = normalize_string(s_for)
                c_num_match = re.match(r'^c(\d+)$', c_check)
                if c_num_match:
                    c_num = c_num_match.group(1)
                    if c_num in self.caldwell_map: s_for = self.caldwell_map[c_num] 
                clean_search_key = normalize_string(s_for)
                
                if clean_search_key in self.coord_cache:
                    cached = self.coord_cache[clean_search_key]
                    result["coords"] = cached["coords_str"]; result["ra_decimal"] = cached["ra"]; result["dec_decimal"] = cached["dec"]; result["status_text"] = "Koordinaten aus Cache (schnell)."
                else:
                    coord = None
                    try:
                        coord = SkyCoord.from_name(s_for)
                    except:
                        pass
                        
                    if not coord and not result["found_locally"]:
                        for com, cid in self.common_names.items():
                            c_low = com.lower()
                            s_low = search_term.lower()
                            is_match = False
                            
                            if c_low == s_low: is_match = True
                            elif c_low in s_low:
                                if len(c_low) > 3 or re.search(r'\b' + re.escape(c_low) + r'\b', s_low):
                                    is_match = True
                                    
                            if is_match:
                                s_for = cid
                                result["name"] = generate_pretty_name(cid, self.caldwell_map, self.reverse_caldwell_map, self.common_names)
                                if cid.startswith("M "): result["wiki_url"] = f"https://de.wikipedia.org/wiki/Messier_{cid.split(' ')[1]}"
                                try:
                                    coord = SkyCoord.from_name(s_for)
                                except: pass
                                break

                    if coord:
                        result["ra_decimal"] = coord.ra.deg; result["dec_decimal"] = coord.dec.deg
                        result["coords"] = f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                        if not result["status_text"]: result["status_text"] = "Koordinaten online abgerufen."
                        self.save_to_cache(s_for, result["coords"], result["ra_decimal"], result["dec_decimal"])
                    else:
                        raise Exception("Keine Koordinaten gefunden")
                        
                result["user_note"] = self.get_note(search_term)
                result["todo_status"] = self.get_todo_status(search_term) 
            except:
                result["coords"] = "Keine Koordinaten gefunden."
                if not result["found_locally"]: result["status_text"] = "Nichts gefunden."

        if not result["wiki_url"] and result["name"] != "---":
            name_check = result["name"]
            m_match = re.search(r'M\s*(\d+)', name_check, re.IGNORECASE)
            if m_match: result["wiki_url"] = f"https://de.wikipedia.org/wiki/Messier_{m_match.group(1)}"
            elif "NGC" in name_check:
                ngc_match = re.search(r'NGC\s*(\d+)', name_check, re.IGNORECASE)
                if ngc_match: result["wiki_url"] = f"https://de.wikipedia.org/wiki/NGC_{ngc_match.group(1)}"
            elif "IC" in name_check:
                ic_match = re.search(r'IC\s*(\d+)', name_check, re.IGNORECASE)
                if ic_match: result["wiki_url"] = f"https://de.wikipedia.org/wiki/IC_{ic_match.group(1)}"
            else:
                clean_n = re.sub(r'\(.*?\)', '', name_check).strip()
                result["wiki_url"] = clean_name_for_wiki(clean_n)
        return result

    def solve_image_astrometry(self, file_path, status_callback):
        try:
            from logic_astrometry import AstrometryClient
        except ImportError:
            status_callback("Fehler: 'logic_astrometry.py' nicht gefunden!")
            return None

        key = self.get_astrometry_key()
        if not key:
            status_callback("Fehler: Kein API Key in Einstellungen!")
            return None

        client = AstrometryClient(key)
        
        status_callback("Logge ein...")
        success, msg = client.login()
        if not success:
            status_callback(msg)
            return None
            
        status_callback("Lade Bild hoch...")
        sub_id, msg = client.upload_file(file_path)
        if not sub_id:
            status_callback(msg)
            return None
        
        try:
            status_url = f"https://nova.astrometry.net/status/{sub_id}"
            open_url(status_url)
        except: pass 
            
        status_callback(f"Warte auf Job (Sub: {sub_id})...")
        
        job_id = client.wait_for_job(sub_id, timeout=600)
        
        if not job_id:
            status_callback("Timeout: Warteschlange > 10 Min. Siehe Browser!")
            return None
            
        status_callback(f"Solve läuft (Job: {job_id})...")
        
        is_solved = client.wait_for_calibration(job_id, timeout=600)
        
        if is_solved:
            status_callback("Hole Ergebnisse...")
            res = client.get_results(job_id)
            return res
        else:
            status_callback("Konnte Bild nicht solven (Failure).")
            return None
            
    def get_best_observation_time(self, ra_deg, dec_deg):
        latitude, longitude = self.get_location()

        if ra_deg is None or dec_deg is None:
            return "Unbekannt"
            
        max_alt = 90 - abs(latitude - dec_deg)
        
        if max_alt < 10: 
            return f"Zu tief am Horizont / unsichtbar (Max: {int(max_alt)}°)"
            
        is_circumpolar = dec_deg > (90 - latitude)
            
        ra_hours = ra_deg / 15.0
        month_idx = int((8.5 + (ra_hours / 2)) % 12) 
        
        months = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", 
                  "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
        
        prev_month = months[(month_idx - 1) % 12]
        next_month = months[(month_idx + 1) % 12]
        period = f"{prev_month} bis {next_month}"
        
        days_offset = ra_hours * (365.24 / 24.0)
        base_date = datetime(2025, 9, 22)
        best_date = base_date + timedelta(days=days_offset)
        best_day_str = f"{best_date.day}. {months[best_date.month - 1]}"

        time_offset_min = (15.0 - longitude) * 4.0
        is_dst = 4 <= best_date.month <= 10

        transit_hour = 1 if is_dst else 0
        transit_min = int(round(time_offset_min))

        if transit_min < 0:
            transit_min += 60
            transit_hour -= 1
            if transit_hour < 0: transit_hour = 23

        time_str = f"{transit_hour:02d}:{transit_min:02d} Uhr"
        
        current_status = ""
        try:
            target = SkyCoord(ra=ra_deg*u.deg, dec=dec_deg*u.deg)
            loc = EarthLocation(lat=latitude*u.deg, lon=longitude*u.deg)
            now = Time.now()
            
            altaz_now = target.transform_to(AltAz(obstime=now, location=loc))
            alt_now = altaz_now.alt.deg
            
            future = now + timedelta(minutes=5)
            altaz_future = target.transform_to(AltAz(obstime=future, location=loc))
            trend = "↗" if altaz_future.alt.deg > alt_now else "↘"
            
            if alt_now < 0:
                current_status = f" | Jetzt: Unter Horizont ({int(alt_now)}°)"
            elif alt_now < 20:
                current_status = f" | Jetzt: Sehr tief ({int(alt_now)}° {trend})"
            else:
                current_status = f" | Jetzt: Gut sichtbar ({int(alt_now)}° {trend})"
        except Exception:
            pass 
            
        alt_str = f"Max: {int(max_alt)}°"
        opt_str = f"Optimum: {best_day_str} um {time_str}"
        
        if is_circumpolar:
            return f"Ganzjährig (Beste Zeit: {period}) | {alt_str} | {opt_str}{current_status}"
        else:
            return f"{period} | {alt_str} | {opt_str}{current_status}"

    def get_altitude_curve(self, ra_deg, dec_deg):
        if ra_deg is None or dec_deg is None:
            return [], []
            
        lat, lon = self.get_location()
        loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
        now = Time.now()
        
        times = now + TimeDelta(np.linspace(0, 24, 48)*u.hour) 
        
        target = SkyCoord(ra=ra_deg*u.deg, dec=dec_deg*u.deg)
        altaz_frame = AltAz(obstime=times, location=loc)
        altaz_objs = target.transform_to(altaz_frame)
        
        return times.datetime, altaz_objs.alt.deg

    def get_moon_info(self, ra_deg, dec_deg):
        if ra_deg is None or dec_deg is None:
            return None, None
            
        lat, lon = self.get_location()
        loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
        now = Time.now()
        
        moon = get_body("moon", now)
        target = SkyCoord(ra=ra_deg*u.deg, dec=dec_deg*u.deg)
        sep = target.separation(moon).deg
        
        sun = get_sun(now)
        moon_sun_sep = moon.separation(sun).deg
        phase = (1 - np.cos(np.radians(moon_sun_sep))) / 2 * 100
        
        return sep, phase
    
    def create_aladin_lite_atlas(self, callback=None):
        return self.atlas_exporter.generate_atlas(callback)