import os
import glob
import subprocess
import json
import numpy as np
import cv2  
import matplotlib.pyplot as plt

import warnings
from astropy.wcs import FITSFixedWarning
warnings.simplefilter('ignore', category=FITSFixedWarning)

from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u

from astroquery.simbad import Simbad
from astroquery.astrometry_net import AstrometryNet 
from astroquery.vizier import Vizier

from photutils.centroids import centroid_com
from photutils.aperture import CircularAperture, CircularAnnulus, aperture_photometry, ApertureStats
from astropy.timeseries import LombScargle
from astropy.stats import sigma_clip

class AstroBackend:
    def __init__(self):
        self.current_image_data = None
        self.current_header = None
        self.current_filepath = None 
        self.wcs = None 
        self.current_image_data = None
        
        self.target_star_initial = None 
        self.comp_star_initial = None
        self.target_star_current = None
        self.comp_star_current = None
        
        self.target_star_name = "Unbekannt"
        self.comp_star_name = "na"
        self.comp_star_mag = "na"
        
        self.global_template = None
        self.tpl_x1 = 0
        self.tpl_y1 = 0
        
        self.tracking_data = [] 
        
        self.file_list = []
        self.results_time_raw = [] 
        self.results_delta_mag = []
        self.plot_times = [] 
        self.known_variables = []
        
        # --- NEU: Schalter für statisches Tracking ---
        self.use_static_tracking = False
        
        # --- NEU: Einstellbare Photometrie-Radien ---
        self.aperture_r = 6
        self.annulus_in = 10
        self.annulus_out = 15
        
    def export_bav_format_c(self, filepath, var_name, bav_obs, filter_band, comp_name="na", comp_mag="na", remarks="na"):
        if not self.results_time_raw or not self.results_delta_mag:
            return False, "Keine Daten zum Exportieren."
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("#TYPE=Extended\n")
                f.write("#DELIM=|\n")
                f.write(f"#BAVOBS={bav_obs}\n")
                f.write("#OBSCODE=\n")
                f.write("#OBSTYPE=CCD\n")
                f.write("#DATE=HJD\n")
                f.write("#SOFTWARE=VStar Analyzer v1.0\n")
                f.write("#BAVCAT=\n")

                for t, mag in zip(self.results_time_raw, self.results_delta_mag):
                    calc_mag = mag
                    if comp_mag != "na":
                        try:
                            calc_mag = mag + float(comp_mag.replace(',', '.'))
                        except ValueError:
                            pass
                    
                    line = f"{var_name}|{t:.5f}|{calc_mag:.3f}|na|{filter_band}|no|dif|{comp_name}|{comp_mag}|na|na|na|na|na|{remarks}\n"
                    f.write(line)
            return True, "BAV Format C erfolgreich exportiert."
        except Exception as e:
            return False, f"Fehler beim Export: {e}"

    def export_bav_report(self, filepath, filter_band):
        if not self.results_time_raw or not self.results_delta_mag:
            return False, "Keine Daten zum Exportieren."
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("#BAV-Report\n")
                f.write(f"#Rem = Filter: {filter_band}\n")
                for t, mag in zip(self.results_time_raw, self.results_delta_mag):
                    f.write(f"{t:.5f} {mag:.3f}\n")
            return True, "BAV Report erfolgreich exportiert."
        except Exception as e:
            return False, f"Fehler beim Export: {e}"    

    def export_bav_lightcurve_png(self, filepath, var_name, bav_obs, filter_band, comp_name, comp_mag, extremum="min", remarks="na"):
        if not self.results_time_raw or not self.results_delta_mag:
            return False, "Keine Daten für den Plot."
        
        try:
            # Wir zwingen Matplotlib für diesen Export in den Standard-Modus (weiß)
            with plt.style.context('default'):
                # DIN A5 Hochformat-Proportionen
                fig = plt.figure(figsize=(8.27, 11.69))
                fig.patch.set_facecolor('white')
                
                # Graphen-Bereich in der oberen Hälfte
                ax = fig.add_axes([0.15, 0.45, 0.75, 0.4])
                ax.set_facecolor('white')
                
                t = np.array(self.results_time_raw)
                y = np.array(self.results_delta_mag)
                
                # Scatter-Plot der rohen Messpunkte
                ax.plot(t, y, marker='d', markersize=4, linestyle='', color='black', alpha=0.5, label='Messwerte')
                
                # --- NEU: Trendlinie berechnen und zeichnen ---
                if len(t) > 5:
                    try:
                        # Ausreißer filtern (1. und 99. Perzentil) für robusteren Fit
                        p1, p99 = np.percentile(y, 1), np.percentile(y, 99)
                        mask = (y >= p1) & (y <= p99)
                        
                        # FIX für RankWarning: Große JD-Zahlen für die Mathematik verkleinern
                        t_offset = t - t[0] 
                        
                        z = np.polyfit(t_offset[mask], y[mask], 4)
                        p = np.poly1d(z)
                        
                        t_trend = np.linspace(min(t), max(t), 200)
                        t_trend_offset = t_trend - t[0] # Den gleichen Offset beim Auswerten nutzen
                        y_trend = p(t_trend_offset)
                        
                        # Als gestrichelte schwarze Linie plotten
                        ax.plot(t_trend, y_trend, color='black', linestyle='--', linewidth=1.5, alpha=0.9, label='Trend (Poly 4)')
                    except Exception: 
                        pass
                # ----------------------------------------------
                
                ax.invert_yaxis()  # Helligkeit: kleinerer Wert = heller (weiter oben)
                ax.set_ylabel(f"delta mag ({filter_band}) instr", weight='bold', color='black')
                ax.set_xlabel("JD heliozentrisch (UTC)", weight='bold', color='black')
                ax.tick_params(colors='black')
                ax.grid(True, linestyle=':', color='gray', alpha=0.5)
                
                # Legende anzeigen
                ax.legend(loc="best", frameon=True, facecolor="white", edgecolor="black", fontsize=8)
                
                for spine in ax.spines.values():
                    spine.set_edgecolor('black')
                
                # Finde Extremum (Min oder Max)
                if extremum == "min":
                    idx = np.argmax(y) # Schwächster Punkt in Magnitude
                else:
                    idx = np.argmin(y) # Hellster Punkt in Magnitude
                    
                ex_t = t[idx]
                ex_y = y[idx]
                
                # Pfeil-Markierung
                arrow_y = ex_y + 0.15 * (np.max(y) - np.min(y)) if extremum == "min" else ex_y - 0.15 * (np.max(y) - np.min(y))
                ax.annotate('', xy=(ex_t, ex_y), xytext=(ex_t, arrow_y),
                            arrowprops=dict(facecolor='black', shrink=0.05, width=1.5, headwidth=6))
                
                # Kopfbereich (Header)
                date_str = Time(t[0], format='jd').isot.split('T')[0]
                fig.text(0.15, 0.88, f"{var_name}", fontsize=14, weight='bold', ha='left', color='black')
                fig.text(0.9, 0.88, f"{date_str}", fontsize=14, ha='right', color='black')
                
                # Metadaten-Block (Tabelle unterhalb)
                text_x_col1 = 0.15
                text_x_col2 = 0.40
                start_y = 0.38
                line_step = 0.025
                
                ex_label = "Minimum" if extremum == "min" else "Maximum"
                
                lines = [
                    (f"{ex_label}:", f"{ex_t:.4f} HJD"), # <-- HIER: JD in HJD ändern
                    ("Vergl.-Sterne:", f"C = {comp_name} (mag = {comp_mag})"),
                    ("Fotometer, Filter:", f"CCD mit {filter_band}-Filter"),
                    ("Fotometrie mit:", "VStar Analyzer v1.0"),
                    ("Auswertung:", f"Polynom 4. Grades"),
                    ("Luftmasse X =", "Optionale Angabe"),
                    (f"n = {len(t)}", ""),
                    ("Beobachter:", f"{bav_obs}"),
                    ("Bemerkungen:", f"{remarks}")
                ]
                
                for i, (col1, col2) in enumerate(lines):
                    y_pos = start_y - (i * line_step)
                    fig.text(text_x_col1, y_pos, col1, fontsize=10, weight='bold' if i == 0 else 'normal', color='black')
                    fig.text(text_x_col2, y_pos, col2, fontsize=10, color='black')
                
                # Unterer Rand
                fig.text(0.15, start_y - (len(lines) + 1) * line_step, "Generiert mit VStar Analyzer für BAV", fontsize=8, color='gray')
                
                fig.savefig(filepath, dpi=200, bbox_inches='tight', facecolor='white')
                plt.close(fig)
                return True, "BAV Lichtkurvenblatt (PNG) erfolgreich erstellt."
        except Exception as e:
            return False, f"Fehler bei Lichtkurvenblatt-Erstellung: {e}"

    def load_fits_file(self, filepath):
        try:
            with fits.open(filepath) as hdul:
                self.current_image_data = hdul[0].data
                self.current_header = hdul[0].header
                self.current_filepath = filepath
                
                # --- NEU: SIP Header Fix (repariert Astrometry/ASTAP Ungenauigkeiten) ---
                if 'A_ORDER' in self.current_header and 'CTYPE1' in self.current_header:
                    if not self.current_header['CTYPE1'].endswith('-SIP'):
                        self.current_header['CTYPE1'] += '-SIP'
                    if not self.current_header['CTYPE2'].endswith('-SIP'):
                        self.current_header['CTYPE2'] += '-SIP'
                # ------------------------------------------------------------------------
                
                try:
                    self.wcs = WCS(self.current_header)
                except:
                    self.wcs = None

            self.target_star_initial = None
            self.comp_star_initial = None
            self.target_star_current = None
            self.comp_star_current = None
            
            self.target_star_name = "Unbekannt"
            self.comp_star_name = "na"
            self.comp_star_mag = "na"
            
            self.global_template = None
            self.tracking_data = []
            self.known_variables = [] 
            return True, "FITS erfolgreich geladen."
        except Exception as e:
            return False, f"Fehler beim Laden: {e}"

    def load_folder(self, folderpath):
        search_path_1 = os.path.join(folderpath, "*.fit")
        search_path_2 = os.path.join(folderpath, "*.fits")
        self.file_list = sorted(glob.glob(search_path_1) + glob.glob(search_path_2))
        
        if not self.file_list:
            return False, "Keine FITS in diesem Ordner."
        return self.load_fits_file(self.file_list[0])

    def run_plate_solve(self, solver_type, astap_path="", api_key=""):
        if not self.current_filepath:
            return False, "Kein Bild geladen."

        if solver_type == "ASTAP":
            if not astap_path or not os.path.exists(astap_path):
                return False, "ASTAP Pfad ungültig."
            try:
                cmd = [astap_path, '-f', self.current_filepath, '-fov', '1.5']
                subprocess.run(cmd, capture_output=True, text=True)
                wcs_file = self.current_filepath.rsplit('.', 1)[0] + '.wcs'
                
                if os.path.exists(wcs_file):
                    header = fits.Header.fromtextfile(wcs_file)
                    
                    # --- NEU: SIP Header Fix ---
                    if 'A_ORDER' in header and 'CTYPE1' in header:
                        if not header['CTYPE1'].endswith('-SIP'):
                            header['CTYPE1'] += '-SIP'
                        if not header['CTYPE2'].endswith('-SIP'):
                            header['CTYPE2'] += '-SIP'
                    # ---------------------------
                    
                    self.wcs = WCS(header)
                    os.remove(wcs_file)
                    return True, "ASTAP Solving erfolgreich!"
                else:
                    return False, "ASTAP konnte das Bild nicht lösen."
            except Exception as e:
                return False, f"ASTAP Fehler: {e}"

        elif solver_type == "Astrometry.net":
            if not api_key:
                return False, "Kein API-Key eingegeben."
            try:
                ast = AstrometryNet()
                ast.api_key = api_key
                wcs_header = ast.solve_from_image(self.current_filepath, force_image_upload=True, solve_timeout=120)
                if wcs_header:
                    self.wcs = WCS(wcs_header)
                    return True, "Astrometry.net Solving erfolgreich!"
                else:
                    return False, "Astrometry.net Timeout oder fehlgeschlagen."
            except Exception as e:
                return False, f"Astrometry.net Fehler: {e}"
        return False, "Unbekannter Solver."

    def identify_star(self, x, y):
        if self.wcs is None or not self.wcs.has_celestial:
            return None, "Astrometrie fehlt! Bitte erst 'Plate-Solve' ausführen."

        coord_str = "Unbekannt"
        try:
            ra, dec = self.wcs.pixel_to_world_values(x, y)
            coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg), frame='icrs')
            coord_str = coord.to_string('hmsdms')
            
            custom_simbad = Simbad()
            custom_simbad.add_votable_fields('otype', 'flux(V)') 
            result = custom_simbad.query_region(coord, radius=2.0 * u.arcmin)
            
            if result is not None and len(result) > 0:
                name_col = 'MAIN_ID' if 'MAIN_ID' in result.colnames else next((c for c in result.colnames if 'ID' in c.upper() or 'NAME' in c.upper()), result.colnames[0])
                otype_col = next((c for c in result.colnames if 'OTYPE' in c.upper()), None)
                name = result[name_col][0]
                if np.ma.is_masked(name): name = "Unknown"
                otype = result[otype_col][0] if otype_col else "Unknown"
                if np.ma.is_masked(otype): otype = "Unknown"
                if isinstance(name, bytes): name = name.decode('utf-8')
                if isinstance(otype, bytes): otype = otype.decode('utf-8')
                return coord_str, f"{name} ({otype})"
            else:
                return coord_str, "Kein bekannter Stern im engen Umkreis."
        except Exception as e:
            return coord_str, f"SIMBAD Fehler: {e}"

    def find_all_variables(self):
        if self.wcs is None or not self.wcs.has_celestial:
            return False, "Astrometrie fehlt!", []
        try:
            h, w = self.current_image_data.shape
            ra_cen, dec_cen = self.wcs.pixel_to_world_values(w/2, h/2)
            center_coord = SkyCoord(ra=ra_cen, dec=dec_cen, unit=(u.deg, u.deg), frame='icrs')

            try:
                v = Vizier(row_limit=5000) 
                results = v.query_region(center_coord, radius=0.8 * u.deg, catalog='B/vsx/vsx')
            except Exception:
                v = Vizier(row_limit=5000, vizier_server='vizier.cfa.harvard.edu')
                results = v.query_region(center_coord, radius=0.8 * u.deg, catalog='B/vsx/vsx')
            
            if results is None or len(results) == 0:
                return False, "Keine Variablen gefunden.", []

            vsx_table = results[0] 
            self.known_variables = []
            name_col = 'Name' if 'Name' in vsx_table.colnames else vsx_table.colnames[0]
            type_col = 'Type' if 'Type' in vsx_table.colnames else None
            ra_col = '_RAJ2000' if '_RAJ2000' in vsx_table.colnames else 'RAJ2000'
            dec_col = '_DEJ2000' if '_DEJ2000' in vsx_table.colnames else 'DEJ2000'
            spam_prefixes = ('Gaia DR', 'ZTF J', 'CRTS J', 'ATO J', 'ASASSN', 'WISE J', 'CSS J', 'TIC ')

            for row in vsx_table:
                name = row[name_col]
                if np.ma.is_masked(name): continue
                if isinstance(name, bytes): name = name.decode('utf-8')
                if any(prefix in name for prefix in spam_prefixes): continue
                
                otype = row[type_col] if type_col else "Var"
                if np.ma.is_masked(otype): otype = "Var"
                if isinstance(otype, bytes): otype = otype.decode('utf-8')

                ra_val = row[ra_col]
                dec_val = row[dec_col]

                if isinstance(ra_val, str) or isinstance(ra_val, bytes):
                    if isinstance(ra_val, bytes): ra_val = ra_val.decode('utf-8')
                    if isinstance(dec_val, bytes): dec_val = dec_val.decode('utf-8')
                    c_coord = SkyCoord(ra=ra_val, dec=dec_val, unit=(u.hourangle, u.deg))
                else:
                    c_coord = SkyCoord(ra=ra_val, dec=dec_val, unit=(u.deg, u.deg), frame='icrs')

                px, py = self.wcs.world_to_pixel(c_coord)
                
                if 0 <= px < w and 0 <= py < h:
                    # --- NEU: Auto-Snap korrigiert den WCS-Versatz ---
                    snap_pos, is_ok = self._micro_centroid(self.current_image_data, (px, py), box=60)
                    if is_ok:
                        px, py = snap_pos
                    # -------------------------------------------------
                    
                    self.known_variables.append((float(px), float(py), name, otype))

            if len(self.known_variables) > 0:
                return True, f"{len(self.known_variables)} Variablen gefunden!", self.known_variables
            else:
                return False, "Nur Survey-Variablen gefunden.", []

        except Exception as e:
            return False, f"Fehler: {e}", []

    def find_smart_comparison_star(self, target_x, target_y):
        if self.wcs is None or not self.wcs.has_celestial:
            return False, None, "Astrometrie fehlt!"

        try:
            ra, dec = self.wcs.pixel_to_world_values(target_x, target_y)
            t_coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg), frame='icrs')
            target_mag = None

            try:
                custom_simbad = Simbad()
                custom_simbad.add_votable_fields('flux(V)', 'flux(G)')
                target_res = custom_simbad.query_region(t_coord, radius=2.0 * u.arcmin)
                
                if target_res is not None:
                    v_col = next((c for c in target_res.colnames if 'FLUX' in c.upper() and '_V' in c.upper()), None)
                    g_col = next((c for c in target_res.colnames if 'FLUX' in c.upper() and '_G' in c.upper()), None)
                    
                    for row in target_res:
                        if v_col and not np.ma.is_masked(row[v_col]):
                            try: target_mag = float(row[v_col])
                            except: pass
                        if target_mag is None and g_col and not np.ma.is_masked(row[g_col]):
                            try: target_mag = float(row[g_col])
                            except: pass
            except: pass

            if target_mag is None:
                try:
                    v = Vizier(columns=['max'], row_limit=3)
                    vsx_res = v.query_region(t_coord, radius=2.0*u.arcmin, catalog='B/vsx/vsx')
                    if vsx_res and len(vsx_res) > 0:
                        for row in vsx_res[0]:
                            if not np.ma.is_masked(row['max']):
                                m_str = str(row['max']).replace('V', '').replace('p', '').replace('<', '').replace('>', '').replace('(', '').replace(')', '').strip()
                                try: target_mag = float(m_str)
                                except: pass
                except: pass

            if target_mag is None:
                return False, None, "Helligkeit des Zielsterns nicht ermittelbar."

            try:
                v_gaia = Vizier(columns=['Source', '_RAJ2000', '_DEJ2000', 'Gmag'], 
                                column_filters={"Gmag": f"{target_mag-2.0}..{target_mag+2.0}"},
                                row_limit=300)
                
                try:
                    neighbors_res = v_gaia.query_region(t_coord, radius=25 * u.arcmin, catalog='I/355/gaiadr3')
                except:
                    v_gaia.vizier_server = 'vizier.cfa.harvard.edu'
                    neighbors_res = v_gaia.query_region(t_coord, radius=25 * u.arcmin, catalog='I/355/gaiadr3')
                
                if not neighbors_res or len(neighbors_res) == 0:
                    return False, None, "Keine passenden Sterne im Gaia-Katalog gefunden."

                gaia_table = neighbors_res[0]
                best_candidate = None
                min_mag_diff = 999.0

                for row in gaia_table:
                    if np.ma.is_masked(row['Gmag']): continue
                    cand_mag = float(row['Gmag'])
                    mag_diff = abs(cand_mag - target_mag)

                    ra_val = row['_RAJ2000']
                    dec_val = row['_DEJ2000']
                    c_coord = SkyCoord(ra=ra_val, dec=dec_val, unit=(u.deg, u.deg), frame='icrs')
                    px, py = self.wcs.world_to_pixel(c_coord)

                    if 25 <= px < self.current_image_data.shape[1]-25 and 25 <= py < self.current_image_data.shape[0]-25:
                        
                        # --- NEU: Auto-Snap für den Vergleichsstern ---
                        snap_pos, is_ok = self._micro_centroid(self.current_image_data, (px, py), box=60)
                        if is_ok:
                            px, py = snap_pos
                        # ----------------------------------------------
                        
                        if abs(px - target_x) > 40 or abs(py - target_y) > 40:
                            is_known_var = False
                            for var_star in self.known_variables:
                                vx, vy, vname, vtype = var_star
                                if abs(px - vx) < 5 and abs(py - vy) < 5:
                                    is_known_var = True
                                    break
                            if not is_known_var and mag_diff < min_mag_diff:
                                min_mag_diff = mag_diff
                                gaia_id = row['Source'] if 'Source' in gaia_table.colnames else "Unbekannt"
                                best_candidate = (float(px), float(py), f"Gaia DR3 {gaia_id}", cand_mag, mag_diff)

                if best_candidate:
                    x, y, name, mag, diff = best_candidate
                    self.comp_star_name = name
                    self.comp_star_mag = f"{mag:.3f}"
                    return True, (x, y), f"Zielstern: ca. {target_mag:.2f} mag\nVergleichsstern gefunden:\n{mag:.2f} mag (Diff: {diff:.2f} mag)"
                else:
                    return False, None, "Kein geeigneter, konstanter Stern im Gaia-Katalog gefunden."

            except Exception as e:
                return False, None, f"Fehler bei Gaia-Abfrage: {e}"

        except Exception as e:
            return False, None, f"Fehler bei Smart-Comp: {e}"

    def _micro_centroid(self, data, pos, box=14):
        x, y = pos
        hx = box // 2
        
        # --- KORREKTUR: Ausdrückliche Umwandlung in float ---
        xi, yi = int(round(float(x))), int(round(float(y)))
        # ----------------------------------------------------
        
        y1, y2 = max(0, yi - hx), min(data.shape[0], yi + hx)
        x1, x2 = max(0, xi - hx), min(data.shape[1], xi + hx)
        cutout = data[y1:y2, x1:x2].astype(float)

        if cutout.size < 9: return pos, False

        bkg = np.median(cutout)
        clean = cutout - bkg
        
        peak = np.max(clean)
        if peak <= 0: return pos, False
        clean[clean < 0.2 * peak] = 0

        if np.sum(clean) > 0:
            try:
                xc, yc = centroid_com(clean)
                final_x = x1 + xc
                final_y = y1 + yc
                return (final_x, final_y), True
            except: pass
        return pos, False

    def _measure_star(self, data, pos):
        try:
            aperture = CircularAperture(pos, r=self.aperture_r)
            annulus = CircularAnnulus(pos, r_in=self.annulus_in, r_out=self.annulus_out)
            stats = ApertureStats(data, annulus)
            bkg_median = stats.median
            phot_table = aperture_photometry(data, aperture)
            raw_flux = phot_table['aperture_sum'][0]
            final_flux = raw_flux - (bkg_median * aperture.area)
            return final_flux if final_flux > 0 else -1
        except:
            return -1

    def analyze_single_file(self, filepath, fallback_index):
        try:
            with fits.open(filepath) as hdul:
                data, header = hdul[0].data, hdul[0].header
                
                obs_time = None
                for key in ['DATE-OBS', 'JD', 'MJD-OBS']:
                    if key in header:
                        try:
                            obs_time = Time(header[key]).jd
                            break
                        except: pass
                if obs_time is None: obs_time = fallback_index
                
                if fallback_index == 0:
                    tx, ty = int(self.target_star_initial[0]), int(self.target_star_initial[1])
                    h_size = 120
                    self.tpl_y1 = max(0, ty - h_size)
                    self.tpl_y2 = min(data.shape[0], ty + h_size)
                    self.tpl_x1 = max(0, tx - h_size)
                    self.tpl_x2 = min(data.shape[1], tx + h_size)
                    
                    self.global_template = data[self.tpl_y1:self.tpl_y2, self.tpl_x1:self.tpl_x2].astype(np.float32)
                    self.target_star_current = self.target_star_initial
                    self.comp_star_current = self.comp_star_initial
                    
                    t_flux = self._measure_star(data, self.target_star_current)
                    c_flux = self._measure_star(data, self.comp_star_current)
                    
                    is_valid = t_flux > 0 and c_flux > 0
                    delta_mag = -2.5 * np.log10(t_flux / c_flux) if is_valid else 0
                    
                    self.tracking_data.append({
                        "filepath": filepath, "obs_time": obs_time, 
                        "t_pos": self.target_star_current, "c_pos": self.comp_star_current, 
                        "valid": is_valid, "delta_mag": delta_mag
                    })
                    return is_valid, obs_time, delta_mag

                # ... (oberhalb bleibt alles gleich, inkl. dem if fallback_index == 0 Block) ...

                # --- NEU: Tracking-Weiche ---
                if self.use_static_tracking:
                    # ROCK SOLID MODE: Wir nehmen für jedes Bild stur die exakten Klicks vom 1. Bild
                    self.target_star_current = self.target_star_initial
                    self.comp_star_current = self.comp_star_initial
                    t_ok, c_ok = True, True
                    
                else:
                    # CLASSIC MODE: Template Matching & Micro Centroiding
                    tx, ty = int(self.target_star_initial[0]), int(self.target_star_initial[1])
                    s_size = 350
                    sy1 = max(0, ty - s_size)
                    sy2 = min(data.shape[0], ty + s_size)
                    sx1 = max(0, tx - s_size)
                    sx2 = min(data.shape[1], tx + s_size)
                    
                    search_area = data[sy1:sy2, sx1:sx2].astype(np.float32)
                    
                    t_ok, c_ok = False, False
                    if search_area.shape[0] >= self.global_template.shape[0] and search_area.shape[1] >= self.global_template.shape[1]:
                        res = cv2.matchTemplate(search_area, self.global_template, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)

                        if max_val >= 0.2:
                            match_full_x = sx1 + max_loc[0]
                            match_full_y = sy1 + max_loc[1]
                            drift_x = match_full_x - self.tpl_x1
                            drift_y = match_full_y - self.tpl_y1

                            t_rough = (self.target_star_initial[0] + drift_x, self.target_star_initial[1] + drift_y)
                            c_rough = (self.comp_star_initial[0] + drift_x, self.comp_star_initial[1] + drift_y)

                            t_pos, t_ok = self._micro_centroid(data, t_rough)
                            c_pos, c_ok = self._micro_centroid(data, c_rough)

                    self.target_star_current = t_pos if t_ok else self.target_star_current
                    self.comp_star_current = c_pos if c_ok else self.comp_star_current
                # ------------------------------

                t_flux = self._measure_star(data, self.target_star_current)
                c_flux = self._measure_star(data, self.comp_star_current)
                
                is_valid = t_ok and c_ok and t_flux > 0 and c_flux > 0
                delta_mag = -2.5 * np.log10(t_flux / c_flux) if is_valid else 0
                
                self.tracking_data.append({
                    "filepath": filepath, "obs_time": obs_time, 
                    "t_pos": self.target_star_current, "c_pos": self.comp_star_current, 
                    "valid": is_valid, "delta_mag": delta_mag
                })
                
                if is_valid: return True, obs_time, delta_mag
                return False, obs_time, 0
                
        except Exception as e:
            self.tracking_data.append({
                "filepath": filepath, "obs_time": fallback_index, 
                "t_pos": self.target_star_initial, "c_pos": self.comp_star_initial, 
                "valid": False, "delta_mag": 0
            })
            return False, 0, str(e)

    def remeasure_frame(self, index, t_pos, c_pos):
        if 0 <= index < len(self.tracking_data):
            frame = self.tracking_data[index]
            try:
                with fits.open(frame["filepath"]) as hdul:
                    data = hdul[0].data
                    t_pos_refined, _ = self._micro_centroid(data, t_pos, box=14)
                    c_pos_refined, _ = self._micro_centroid(data, c_pos, box=14)
                    
                    frame["t_pos"] = t_pos_refined
                    frame["c_pos"] = c_pos_refined
                    
                    t_flux = self._measure_star(data, t_pos_refined)
                    c_flux = self._measure_star(data, c_pos_refined)
                    
                    if t_flux > 0 and c_flux > 0:
                        frame["valid"] = True
                        frame["delta_mag"] = -2.5 * np.log10(t_flux / c_flux)
                    else:
                        frame["valid"] = False
                        frame["delta_mag"] = 0
            except:
                frame["valid"] = False

    def recalculate_from_tracking_data(self):
        raw_times = []
        raw_mags = []
        
        # Koordinaten des Zielsterns für die HJD-Korrektur ermitteln
        target_coord = None
        if self.wcs and self.wcs.has_celestial and self.target_star_initial:
            try:
                ra, dec = self.wcs.pixel_to_world_values(*self.target_star_initial)
                target_coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg), frame='icrs')
            except:
                pass

        for frame in self.tracking_data:
            if frame["valid"]:
                obs_time = frame["obs_time"]
                
                # Automatische HJD-Konvertierung (Lichtlaufzeitkorrektur)
                if target_coord and obs_time > 2000000:
                    try:
                        t = Time(obs_time, format='jd')
                        ltt = t.light_travel_time(target_coord, kind='heliocentric')
                        obs_time = (t + ltt).jd
                    except:
                        pass
                        
                raw_times.append(obs_time)
                raw_mags.append(frame["delta_mag"])
                
        # Sigma Clipping für Ausreißer (entfernt Werte > 3 Standardabweichungen)
        if len(raw_mags) > 10:
            clipped = sigma_clip(raw_mags, sigma=3.0, maxiters=3)
            # FIX: getmaskarray garantiert ein Array, auch wenn 0 Ausreißer gefunden wurden
            mask = ~np.ma.getmaskarray(clipped) 
            
            self.results_time_raw = np.array(raw_times)[mask].tolist()
            self.results_delta_mag = np.array(raw_mags)[mask].tolist()
        else:
            self.results_time_raw = raw_times
            self.results_delta_mag = raw_mags
            
        return self.calculate_statistics()

    def calculate_statistics(self):
        if len(self.results_delta_mag) < 5:
            return False, "Zu wenige Messpunkte."
        
        y = np.array(self.results_delta_mag)
        t = np.array(self.results_time_raw)
        
        mag_faintest = np.percentile(y, 99) 
        mag_brightest = np.percentile(y, 1) 
        amplitude = mag_faintest - mag_brightest
        
        period_str = "N/A"
        try:
            ls = LombScargle(t, y)
            frequency, power = ls.autopower()
            best_frequency = frequency[np.argmax(power)]
            best_period = 1.0 / best_frequency
            if t[0] > 2000000:
                hours = best_period * 24
                period_str = f"{hours:.2f} Stunden" if hours >= 2 else f"{hours * 60:.1f} Min"
            else:
                period_str = f"{best_period:.1f} Bilder"
        except: pass

        return True, {
            "min_mag": mag_faintest,
            "max_mag": mag_brightest,
            "amplitude": amplitude,
            "period": period_str
        }