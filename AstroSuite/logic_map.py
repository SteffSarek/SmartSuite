import numpy as np
import re
from utils import read_fits_coords, generate_pretty_name, normalize_string
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.utils.iers import conf
conf.auto_max_age = None
from astropy.time import Time
import astropy.units as u

# --- KONSTANTEN IMPORTIEREN ---
from constants import OBJ_TYPE_COLORS, COLOR_OTHER
# ------------------------------

class MapLogic:
    def __init__(self, main_logic):
        self.logic = main_logic

    def get_milky_way_path(self):
        l_vals = np.linspace(0, 360, 360)
        mw_ra = []; mw_dec = []
        for l in l_vals:
            c = SkyCoord(l=l*u.deg, b=0*u.deg, frame='galactic')
            icrs = c.transform_to('icrs')
            ra_rad = icrs.ra.rad
            ra_plot = -1 * (ra_rad - np.pi)
            mw_ra.append(ra_plot)
            mw_dec.append(icrs.dec.rad)
        points = sorted(zip(mw_ra, mw_dec), key=lambda x: x[0])
        return zip(*points)

    def get_plot_data(self, filter_constellation=None):
        found_ra = []; found_dec = []; found_names = []; found_sizes = []; found_colors = []
        raw_ra = []; raw_dec = [] # Neu: Für schnelle Bulk-Berechnung
        
        base_size = 30; size_factor = 2; max_size = 300
        
        for key, data in self.logic.index.items():
            if filter_constellation and filter_constellation != "Alle":
                c_name = self.logic.constellation_names.get(data.get("parent", ""), "")
                if c_name != filter_constellation: continue
            
            ra = None; dec = None
            
            # 1. Aus Cache
            search_clean = generate_pretty_name(data["original_name"], self.logic.caldwell_map, self.logic.reverse_caldwell_map, self.logic.common_names)
            match_id = re.search(r'((?:NGC|M|IC|C)\s*\d+)', search_clean, re.IGNORECASE)
            if match_id: search_clean = match_id.group(1)
            else: search_clean = search_clean.split("-")[0].split("(")[0].strip()
            clean_k = normalize_string(search_clean)
            
            if clean_k in self.logic.coord_cache:
                cached = self.logic.coord_cache[clean_k]
                ra = cached["ra"]; dec = cached["dec"]
            
            # 2. Aus FITS
            if (ra is None or dec is None) and data.get("fits_sample"):
                try:
                    _, r_deg, d_deg, ok = read_fits_coords(data["fits_sample"])
                    if ok: ra = r_deg; dec = d_deg
                except: pass

            if ra is None or dec is None: continue

            # Für die Karte transformieren (Mollweide-Projektion zentriert)
            ra_rad = np.deg2rad(ra)
            ra_plot = -1 * (ra_rad - np.pi)
            dec_rad = np.deg2rad(dec)

            found_ra.append(ra_plot)
            found_dec.append(dec_rad)
            found_names.append(data["original_name"])
            
            # Unveränderte Grad-Werte speichern
            raw_ra.append(ra)
            raw_dec.append(dec)
            
            img_count = len(data.get("images", []))
            bubble_size = min(base_size + (img_count * size_factor), max_size)
            found_sizes.append(bubble_size)
            
            pretty = generate_pretty_name(data["original_name"], self.logic.caldwell_map, self.logic.reverse_caldwell_map, self.logic.common_names)
            otype = self.logic.determine_object_type(pretty, pretty)
            found_colors.append(OBJ_TYPE_COLORS.get(otype, COLOR_OTHER))

        # --- NEU: Bulk-Berechnung der Horizonthöhe (WIMS Transit-Feature) ---
        alt_colors = []
        if raw_ra and raw_dec:
            try:
                lat, lon = self.logic.get_location()
                loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)
                now = Time.now()
                
                # Array-Transformation: Berechnet alle Objekte in wenigen Millisekunden!
                coords = SkyCoord(ra=np.array(raw_ra)*u.deg, dec=np.array(raw_dec)*u.deg)
                altaz = coords.transform_to(AltAz(obstime=now, location=loc))
                alts = altaz.alt.deg
                
                for a in alts:
                    if a < 0: alt_colors.append('#34495e')    # Unter Horizont (Grau-Blau)
                    elif a < 20: alt_colors.append('#e74c3c') # Zu tief (Rot)
                    elif a < 40: alt_colors.append('#f39c12') # Mittel (Orange)
                    else: alt_colors.append('#2ecc71')        # Optimal (Grün)
            except Exception as e:
                print(f"Fehler bei der AltAz-Berechnung: {e}")
                alt_colors = found_colors # Fallback bei Fehler
        # --------------------------------------------------------------------

        return found_ra, found_dec, found_names, found_sizes, found_colors, alt_colors