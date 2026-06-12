import os
import platform
import subprocess
import webbrowser
import re
import datetime
import urllib.request
import logging  
from astropy.coordinates import SkyCoord
from astropy.io import fits
import astropy.units as u

def open_system_folder(path):
    if not path or not os.path.exists(path): return
    sys_plat = platform.system()
    try:
        if sys_plat == "Windows": os.startfile(path)
        elif sys_plat == "Darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])
    except Exception as e: 
        logging.error(f"Konnte Ordner nicht öffnen ({path}): {e}")

def open_url(url):
    try: webbrowser.open(url)
    except Exception as e: 
        logging.error(f"Konnte URL nicht öffnen ({url}): {e}")

def clean_name_for_wiki(raw_name):
    name = raw_name.replace("_", " ")
    name = re.sub(r'\([^)]*\)', '', name)
    name = re.sub(r'(?i)dwarf\s*\d*', '', name)
    name = re.sub(r'(?i)seestar\s*\w*', '', name)
    name = re.sub(r'(?i)s30\s*\w*', '', name)
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)
    return f"https://de.wikipedia.org/wiki/{name.replace(' ', '_')}"

def read_fits_coords(fits_path):
    try:
        with fits.open(fits_path, ignore_missing_end=True, memmap=True) as hdul:
            ra = None
            dec = None
            for hdu in hdul:
                header = hdu.header
                ra = header.get('RA') or header.get('OBJCTRA')
                dec = header.get('DEC') or header.get('OBJCTDEC')
                if ra is not None and dec is not None:
                    break
            
            if ra and dec:
                if isinstance(ra, (float, int)):
                    c = SkyCoord(ra=ra*u.degree, dec=dec*u.degree)
                else:
                    c = SkyCoord(ra, dec, unit=(u.hourangle, u.deg))
                    
                ra_str = c.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)
                dec_str = c.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)
                return f"RA: {ra_str} | DEC: {dec_str}", c.ra.deg, c.dec.deg, True
    except Exception as e:
        logging.warning(f"Konnte FITS Koordinaten nicht lesen ({fits_path}): {e}")
        
    return None, 0.0, 0.0, False

def normalize_string(s):
    return s.lower().replace(" ", "").replace("_", "").replace("-", "")

def get_fits_stats(folder_path):
    count = 0
    latest_dt_obj = None 
    all_fits = []
    
    search_path = folder_path
    lights_path = os.path.join(folder_path, "lights")
    if os.path.exists(lights_path):
        search_path = lights_path

    try:
        with os.scandir(search_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(('.fit', '.fits')):
                    count += 1
                    all_fits.append((entry.path, entry.stat().st_mtime))
    except Exception as e: 
        logging.error(f"Fehler beim Scannen von {search_path}: {e}")

    if count == 0:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(('.fit', '.fits')):
                    count += 1
                    fp = os.path.join(root, file)
                    all_fits.append((fp, os.path.getmtime(fp)))

    all_fits.sort(key=lambda x: x[1], reverse=True)
    fits_candidates = [x[0] for x in all_fits[:5]]

    for fp in fits_candidates:
        dt_found = None
        try:
            with fits.open(fp, ignore_missing_end=True, memmap=True) as hdul:
                for hdu in hdul:
                    date_obs = hdu.header.get('DATE-OBS')
                    if date_obs:
                        date_str_raw = str(date_obs).split("T")[0]
                        dt_found = datetime.datetime.strptime(date_str_raw, '%Y-%m-%d')
                        break 
        except Exception: 
            pass

        if dt_found is None:
            try:
                ts = os.path.getmtime(fp)
                dt_found = datetime.datetime.fromtimestamp(ts)
                if dt_found.year > datetime.datetime.now().year + 1: 
                    dt_found = None
            except Exception as e:
                logging.error(f"Fehler beim Lesen des Dateidatums ({fp}): {e}")

        if dt_found:
            if latest_dt_obj is None or dt_found > latest_dt_obj:
                latest_dt_obj = dt_found

    date_str = "---"
    raw_ts = 0
    if latest_dt_obj:
        date_str = latest_dt_obj.strftime('%d.%m.%Y')
        raw_ts = latest_dt_obj.timestamp()

    return count, date_str, raw_ts

def format_telescope(raw_type):
    if raw_type == "s30": return "Seestar S30 (Pro)"
    if raw_type == "seestar": return "Seestar S50"
    if raw_type == "dwarf": return "Dwarf 3"
    return "Anderes"

def generate_pretty_name(folder_name, caldwell_map, reverse_caldwell_map, common_names):
    norm_folder = normalize_string(folder_name)
    
    # --- Reverse-Lookup für Eigennamen ---
    for c_name, c_id in common_names.items():
        if normalize_string(c_name) == norm_folder:
            folder_name = c_id
            break

    # --- FIX: Jetzt werden auch Sh2, vdB, Barnard, Collinder und Melotte erkannt! ---
    match = re.search(r'(ngc|m|ic|c|sh2|sh\s*2|b|vdb|cr|mel)[_\s-]*(\d+)', folder_name, re.IGNORECASE)
    if not match: 
        if folder_name.islower() and not folder_name.isdigit():
            return folder_name.title()
        return folder_name

    # Katalog-Typ und Nummer extrahieren
    raw_cat = match.group(1).upper().replace(" ", "")
    number = match.group(2)
    
    # Schöne Formatierung für die "Exoten"
    if raw_cat == "SH2": cat_type = "Sh2"
    elif raw_cat == "VDB": cat_type = "vdB"
    elif raw_cat == "CR": cat_type = "Cr"
    elif raw_cat == "MEL": cat_type = "Mel"
    else: cat_type = raw_cat
    
    # Haupt-ID zusammenbauen (Sh2 und vdB haben traditionell einen Bindestrich, die anderen ein Leerzeichen)
    if cat_type in ["Sh2", "vdB"]:
        main_id = f"{cat_type}-{number}"
    else:
        main_id = f"{cat_type} {number}"
        
    norm_id = f"{cat_type.lower()}{number}"
    
    display_parts = [main_id]

    # Caldwell-Logik
    if cat_type == "C":
        if number in caldwell_map: 
            alias = str(caldwell_map[number]).replace(")", "") 
            if alias.isdigit(): alias = f"NGC {alias}" 
            display_parts.append(f"({alias})")
    else:
        if norm_id in reverse_caldwell_map:
            c_num = reverse_caldwell_map[norm_id]
            display_parts.append(f"(C {c_num})")

    # Alle bekannten Eigennamen zu dieser ID suchen
    found_common = []
    for name, cat_id in common_names.items():
        if normalize_string(cat_id) == norm_id: 
            clean_name = name.title().replace(")", "") 
            found_common.append(clean_name)
    
    # Eigennamen anhängen
    if found_common:
        unique_common = sorted(list(set(found_common)))
        display_parts.append("- " + ", ".join(unique_common))

    return " ".join(display_parts)

def get_remote_version(version_url):
    try:
        with urllib.request.urlopen(version_url, timeout=3) as response:
            content = response.read().decode('utf-8').strip()
            return content
    except Exception as e: 
        logging.warning(f"Konnte Update-Server nicht erreichen: {e}")
        return None