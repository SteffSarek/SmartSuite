# ==============================================================================
# SMART_UTILS.PY - Logik und Hilfsfunktionen (V1.0.0)
# ==============================================================================
import os
import json
import platform
import re
import webbrowser
import logging
import sys
from astropy.io import fits
from astropy.coordinates import SkyCoord
import astropy.units as u
import urllib.request 

# --- LOGGER SETUP ---
def setup_logger():
    logger = logging.getLogger("SmartSuite")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        
        # Datei-Handler für persistentes Logging
        try:
            file_handler = logging.FileHandler('smartsuite.log', encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Konnte Log-Datei nicht erstellen: {e}")
            
        # Konsolen-Handler für direkte Fehlerausgabe
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

log = setup_logger()

# --- KONFIGURATION ---
CONFIG_FILE = "smartsuite_config.json"
VERSION_FILE_URL = "https://drive.google.com/uc?export=download&id=1OGcf3RoHc6meVa4YP593j-bV2dpD7Cxy"
UPDATE_FOLDER_URL = "https://drive.google.com/drive/folders/1jlE5gaClIDqibH2HbMKIfiXzKq9CF1Tg"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: 
                data = json.load(f)
                
                # --- NEU: KUGELSICHERER KOMMA-CHECK ---
                # Falls sich in der JSON noch ein Komma eingeschlichen hat, 
                # wird es beim Laden direkt "on the fly" in einen Punkt verwandelt.
                if "default_lat" in data and isinstance(data["default_lat"], str):
                    data["default_lat"] = data["default_lat"].replace(",", ".")
                if "default_lon" in data and isinstance(data["default_lon"], str):
                    data["default_lon"] = data["default_lon"].replace(",", ".")
                # ----------------------------------------
                    
                return data
        except Exception as e:
            log.error(f"Fehler beim Laden der Config-Datei: {e}")
    return {}

def save_config(key, value):
    data = load_config()
    
    # --- NEU: KUGELSICHERER KOMMA-CHECK ---
    # Falls der Nutzer in den Einstellungen ein Komma tippt, 
    # korrigieren wir das sofort, bevor es gespeichert wird!
    if key in ["default_lat", "default_lon"] and isinstance(value, str):
        value = value.replace(",", ".")
    # ----------------------------------------
        
    data[key] = value
    try:
        with open(CONFIG_FILE, 'w') as f: json.dump(data, f)
    except Exception as e:
        log.error(f"Fehler beim Speichern der Config-Datei (Key: {key}): {e}")
        
def get_data_dir():
    """Erstellt und liefert den Pfad zum AstroData-Ordner für Caches und Ephemeriden."""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    
    d = os.path.join(base, "AstroData")
    os.makedirs(d, exist_ok=True)
    return d

# --- SIRIL ---
def find_siril_path():
    cfg = load_config()
    custom_path = cfg.get("custom_siril_path", "")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    system = platform.system()
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Siril\bin\siril-cli.exe",
            r"C:\Program Files\Siril\bin\siril.exe"
        ]
    elif system == "Linux":
        candidates = ["/usr/bin/siril-cli", "/usr/bin/siril"]
    else:
        candidates = ["/Applications/Siril.app/Contents/MacOS/siril"]

    for p in candidates:
        if os.path.exists(p): return p
    return ""

def get_all_script_paths():
    """Sammelt alle potenziellen Ordner, in denen Siril Skripte ablegt."""
    cfg = load_config()
    custom_dir = cfg.get("custom_scripts_path", "")
    paths_to_scan = []
    
    # 1. Custom Ordner (falls in Einstellungen gesetzt)
    if custom_dir and os.path.exists(custom_dir):
        paths_to_scan.append(custom_dir)
        
    # 2. Standard System- & User-Ordner
    system = platform.system()
    user_home = os.path.expanduser("~")
    
    if system == "Windows":
        paths_to_scan.append(os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Siril", "scripts"))
        paths_to_scan.append(os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(user_home, "AppData", "Local")), "siril", "scripts"))
        paths_to_scan.append(os.path.join(os.environ.get("APPDATA", os.path.join(user_home, "AppData", "Roaming")), "siril", "scripts"))
    elif system == "Linux":
        paths_to_scan.append("/usr/share/siril/scripts")
        paths_to_scan.append(os.path.join(user_home, ".local", "share", "siril", "scripts"))
    else: # Mac
        paths_to_scan.append("/Applications/Siril.app/Contents/Resources/share/siril/scripts")
        paths_to_scan.append(os.path.join(user_home, "Library", "Application Support", "org.free-astro.Siril", "scripts"))
        
    return paths_to_scan

def scan_siril_scripts(log_func=None):
    scripts = {}
    if log_func: log_func("Suche Siril Skripte (.ssf)...")
    
    for path in get_all_script_paths():
        if path and os.path.exists(path):
            try:
                for f in os.listdir(path):
                    if f.lower().endswith(".ssf"): 
                        scripts[f] = os.path.join(path, f)
            except Exception as e:
                log.warning(f"Konnte Skripte in '{path}' nicht scannen: {e}")
    return scripts

def scan_siril_python_scripts(log_func=None):
    scripts = {}
    if log_func: log_func("Suche Siril Python-Skripte (.py)...")
    
    for path in get_all_script_paths():
        if path and os.path.exists(path):
            try:
                for f in os.listdir(path):
                    if f.lower().endswith(".py"): 
                        scripts[f] = os.path.join(path, f)
            except Exception as e:
                log.warning(f"Konnte Python-Skripte in '{path}' nicht scannen: {e}")
    return scripts

# --- FITS HEADER ---
def analyze_header(path):
    try:
        with fits.open(path) as h:
            hdr = h[0].header
            t = hdr.get('OBJECT', 'Unknown')
            
            dev = str(hdr.get('TELESCOP', 'Unknown'))
            dev_up = dev.upper()
            
            if "S50" in dev_up: dev = "Seestar_S50"
            elif "S30" in dev_up: dev = "Seestar_S30" 
            elif "DWARF" in dev_up: dev = "Dwarf_3" if "3" in dev_up else "Dwarf_II"
            
            ra = hdr.get('RA'); dec = hdr.get('DEC')
            c = "Unknown"
            if ra and dec:
                try: 
                    c = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg)).get_constellation()
                except Exception as e:
                    log.debug(f"Konnte Sternbild für Koordinaten {ra}/{dec} nicht ermitteln: {e}")
            
            t = re.sub(r'[<>:"/\\|?*]', '', str(t)).strip().replace(" ", "_")
            return t, c, dev
    except Exception as e:
        log.warning(f"Konnte Header von {os.path.basename(path)} nicht auslesen: {e}")
        return None, None, None

def apply_nina_fix(filepath):
    try:
        with fits.open(filepath, mode='update', ignore_missing_end=True) as hdul:
            header = hdul[0].header
            
            instrume = str(header.get('INSTRUME', '')).upper()
            creator = str(header.get('CREATOR', '')).upper()
            telescop = str(header.get('TELESCOP', '')).upper()
            
            is_seestar = ('SEESTAR' in instrume) or ('SEESTAR' in creator) or ('S50' in telescop) or ('S30' in telescop)
            
            if is_seestar:
                header['BAYERPAT'] = 'GRBG'
                hdul.flush()
                return True
    except Exception as e:
        log.error(f"N.I.N.A. Fix fehlgeschlagen für {os.path.basename(filepath)}: {e}")
        return False
    return False

# --- UPDATE LOGIK (GITHUB INTEGRATION) ---
GITHUB_USER = "SteffSarek" # <-- HIER DEINEN GITHUB NAMEN EINTRAGEN (z.B. "StefanAstro")
GITHUB_REPO = "SmartSuite"     # Der Name deines Repositories auf Github

def get_remote_version():
    """Lädt die Versionsnummer vom aktuellsten GitHub Release."""
    import json
    import urllib.request
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
    try:
        # GitHub API verlangt einen User-Agent Header, sonst wird die Anfrage blockiert
        req = urllib.request.Request(url, headers={'User-Agent': 'SmartSuite-App'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("tag_name", "") # Liefert den Namen deines Tags, z.B. "v1.1" oder "1.1"
    except Exception as e:
        log.error(f"GitHub Update-Check Fehler: Konnte externe Version nicht abrufen. Grund: {e}")
        return None

def open_update_folder():
    """Öffnet die Release-Seite auf GitHub im Standard-Browser."""
    import webbrowser
    url = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
    webbrowser.open(url)