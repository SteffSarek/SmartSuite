import os
import json
import re
from datetime import datetime, timedelta
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u
from utils import generate_pretty_name, normalize_string

class MobileExporter:
    def __init__(self, logic):
        self.logic = logic

    # --- NEU: Übersetzt Grad in Himmelsrichtung (z.B. "S", "SW", "NNO") ---
    def az_to_compass(self, az):
        dirs = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = int((az + 11.25) / 22.5) % 16
        return dirs[idx]
    # ----------------------------------------------------------------------

    def generate(self, save_path):
        notes = self.logic.user_notes
        cache = self.logic.coord_cache
        
        # Standort aus deinen Einstellungen holen
        lat, lon = self.logic.get_location()
        loc = EarthLocation(lat=lat*u.deg, lon=lon*u.deg)

        # Geplante Objekte finden
        todo_keys = [k for k, v in notes.items() if v.get("todo")]
        if not todo_keys:
            return False, "Beobachtungsliste ist leer!"

        # Zeitfenster (18:00 bis 06:00) der aktuellen/nächsten Nacht
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

        cards_html = ""
        scripts_js = ""
        chart_id = 0
        seen_keys = set() 
        exported_count = 0 

        for key in todo_keys:
            valid_keys = self.logic._get_all_aliases(key)
            if any(vk in seen_keys for vk in valid_keys):
                continue
            seen_keys.update(valid_keys)
            
            cache_entry = None
            for vk in valid_keys:
                if vk in cache:
                    cache_entry = cache[vk]
                    break
            
            if not cache_entry:
                search_name = generate_pretty_name(key, self.logic.caldwell_map, self.logic.reverse_caldwell_map, self.logic.common_names)
                s_for = search_name
                
                match_id = re.search(r'^((?:NGC|IC|M|C)\s*\d+)', search_name, re.IGNORECASE)
                if match_id:
                    s_for = match_id.group(1).upper()
                else:
                    if "-" in s_for: s_for = s_for.split("-")[0].strip()
                    if "(" in s_for: s_for = s_for.split("(")[0].strip()

                c_check = normalize_string(s_for)
                c_num_match = re.match(r'^c(\d+)$', c_check)
                if c_num_match:
                    c_num = c_num_match.group(1)
                    if c_num in self.logic.caldwell_map: 
                        s_for = self.logic.caldwell_map[c_num] 

                try:
                    coord = SkyCoord.from_name(s_for)
                    ra = coord.ra.deg
                    dec = coord.dec.deg
                    coords_str = f"RA: {coord.ra.to_string(unit=u.hour, sep=' ', pad=True, precision=0)} | DEC: {coord.dec.to_string(sep=' ', pad=True, alwayssign=True, precision=0)}"
                    self.logic.save_to_cache(key, coords_str, ra, dec)
                    cache_entry = {"ra": ra, "dec": dec, "coords_str": coords_str}
                except:
                    pass

            if cache_entry:
                ra = cache_entry["ra"]
                dec = cache_entry["dec"]
                coords_str = cache_entry["coords_str"]
                
                target = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
                altaz = target.transform_to(frame)
                alts = [round(a, 1) for a in altaz.alt.deg]
                azs = altaz.az.deg
                
                max_alt = max(alts)
                max_idx = alts.index(max_alt)
                best_time_tonight = time_labels[max_idx]
                best_az = azs[max_idx]
                compass_dir = self.az_to_compass(best_az)
                
                if max_alt < 0:
                    tonight_str = "❌ Heute Nacht unter dem Horizont"
                else:
                    tonight_str = f"⭐ Heute Nacht: Am höchsten um {best_time_tonight} Uhr ({max_alt}° in Richtung {compass_dir})"
                
                general_info = self.logic.get_best_observation_time(ra, dec)
                if " | Jetzt:" in general_info:
                    general_info = general_info.split(" | Jetzt:")[0]
                
                # --- WIMS: Live-Mondwarnung für Handy-Sync ---
                moon_html = ""
                try:
                    moon_sep, moon_phase = self.logic.get_moon_info(ra, dec)
                    if moon_sep is not None:
                        if moon_sep < 20:
                            moon_html = f'<p class="moon-danger">⚠️ Mond stört! (Distanz: {int(moon_sep)}°, Phase: {int(moon_phase)}%)</p>'
                        elif moon_sep < 40:
                            moon_html = f'<p class="moon-warn">🌙 Mond nah (Distanz: {int(moon_sep)}°, Phase: {int(moon_phase)}%)</p>'
                        else:
                            moon_html = f'<p class="moon-ok">🌑 Mond OK (Distanz: {int(moon_sep)}°)</p>'
                except Exception:
                    pass
                # ---------------------------------------------
                
                pretty = generate_pretty_name(key, self.logic.caldwell_map, self.logic.reverse_caldwell_map, self.logic.common_names)
                
                note_text = ""
                for vk in valid_keys:
                    if vk in notes and notes[vk].get("note"):
                        note_text = notes[vk]["note"].strip()
                        break
                        
                note_html = ""
                if note_text:
                    note_text_html = note_text.replace('\n', '<br>')
                    note_html = f'<div class="note-box">📝 {note_text_html}</div>'
                
                # HTML Karte zusammenbauen inkl. Mondwarnung
                card = f"""
                <div class="card">
                    <h2>{pretty}</h2>
                    <p class="coords">{coords_str}</p>
                    <p class="obs-info">🔭 {general_info}</p>
                    <p class="tonight-info">{tonight_str}</p>
                    {moon_html}
                    {note_html}
                    <div class="chart-container">
                        <canvas id="chart_{chart_id}"></canvas>
                    </div>
                </div>
                """
                cards_html += card
                
                scripts_js += f"""
                new Chart(document.getElementById('chart_{chart_id}'), {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(time_labels)},
                        datasets: [{{
                            data: {json.dumps(alts)},
                            borderColor: '#e74c3c',
                            backgroundColor: 'rgba(231, 76, 60, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            borderWidth: 2
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
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
                exported_count += 1

        if exported_count == 0:
            return False, "Konnte keine Koordinaten für die Objekte abrufen. Internet prüfen!"

        sync_time_str = now.strftime('%d.%m.%Y, %H:%M')
        
        # HTML Grundgerüst inkl. CSS für die Mondwarnungen
        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>AstroArchive Mobile</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background-color: #121212; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 15px; padding-bottom: 50px; }}
        h1 {{ text-align: center; color: #3498db; margin-bottom: 5px; font-size: 24px; }}
        .subtitle {{ text-align: center; color: #888; font-size: 14px; margin-bottom: 25px; line-height: 1.4; }}
        .sync-time {{ font-size: 11px; color: #555; }}
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
    <h1>🔭 Beobachtungsliste ({exported_count} Objekte)</h1>
    <div class="subtitle">
        Nacht vom {start_time.strftime('%d.%m.')} auf {(start_time + timedelta(days=1)).strftime('%d.%m.')}<br>
        <span class="sync-time">Letzter Sync: {sync_time_str} Uhr</span>
    </div>
    {cards_html}
    <script>
        Chart.defaults.color = '#888';
        {scripts_js}
    </script>
</body>
</html>"""

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html)
            return True, "Erfolgreich exportiert!"
        except Exception as e:
            return False, f"Fehler beim Speichern: {e}"