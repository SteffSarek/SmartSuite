import os
import pathlib
from datetime import datetime
from utils import generate_pretty_name

class HTMLExporter:
    def __init__(self, main_logic):
        self.ml = main_logic

    def generate_report(self, save_path, filter_mode="Alle", filter_value=None, as_gallery=False, date_start=None, date_end=None):
        style_list = """
        .card { background: white; padding: 15px; margin-bottom: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); display: flex; align-items: center; }
        .thumb { width: 100px; height: 100px; object-fit: cover; border-radius: 4px; margin-right: 20px; background: #eee; }
        .info { flex: 1; }
        """
        style_gallery = """
        .grid-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px; }
        .grid-item { background: #222; border-radius: 8px; overflow: hidden; position: relative; aspect-ratio: 1 / 1; }
        .grid-thumb { width: 100%; height: 100%; object-fit: cover; opacity: 0.8; transition: opacity 0.3s; }
        .grid-item:hover .grid-thumb { opacity: 1; }
        .grid-label { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.7); color: white; padding: 5px; text-align: center; font-weight: bold; font-size: 0.9em; }
        .status-badge { position: absolute; top: 5px; right: 5px; width: 20px; height: 20px; border-radius: 50%; border: 2px solid #fff; }
        .found { background-color: #2ecc71; }
        .missing { background-color: #e74c3c; display: none; }
        .placeholder { width: 100%; height: 100%; background: #111; display: flex; align-items: center; justify-content: center; color: #444; font-size: 2em; }
        """
        html = f"""
        <html><head><meta charset='utf-8'><style>
        body {{ font-family: sans-serif; background: {'#f0f0f0' if not as_gallery else '#1a1a1a'}; color: {'#333' if not as_gallery else '#eee'}; padding: 20px; }}
        h2 {{ margin: 0 0 5px 0; color: {'#2c3e50' if not as_gallery else '#eee'}; }}
        .meta {{ color: #7f8c8d; font-size: 0.9em; }}
        .tag {{ display: inline-block; background: #3498db; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; margin-top: 5px; }}
        .tag.galaxy {{ background: #f1c40f; color: #333; }}
        .tag.nebula {{ background: #e74c3c; }}
        .tag.cluster {{ background: #2ecc71; }}
        .tag.comet {{ background: #9b59b6; }}
        {style_gallery if as_gallery else style_list}
        </style></head><body>
        """
        title = "Gesamtes Archiv"
        if filter_mode == "Messier": title = "Messier Katalog"
        elif filter_mode == "Caldwell": title = "Caldwell Katalog"
        elif filter_mode == "NGC": title = "NGC Katalog"
        elif filter_mode == "Sternbild": title = f"Sternbild: {filter_value}"
        
        date_info = ""
        if date_start or date_end:
            date_info = f" | Zeitraum: {date_start if date_start else 'Anfang'} bis {date_end if date_end else 'Heute'}"

        html += f"<h1>AstroArchive {'Gallery' if as_gallery else 'Report'}: {title}</h1>"
        html += f"<p>Erstellt am: {datetime.now().strftime('%d.%m.%Y')}{date_info}</p>"

        # 1. Daten zielsicher aus der zentralen Logik der App holen
        if filter_mode in ["Messier", "Caldwell", "NGC", "Alle"]:
            raw_objects = self.ml.get_catalog_objects(filter_mode)
        elif filter_mode == "Sternbild":
            raw_objects = self.ml.get_constellation_objects(filter_value)
        else:
            raw_objects = []

        # 2. Zeitraum-Filter anwenden
        objects_to_show = []
        for obj in raw_objects:
            is_found = obj["found"]
            
            if is_found and (date_start or date_end):
                if not self.ml.is_date_in_range(obj["date"], date_start, date_end):
                    is_found = False # Für Platzhalter in der Galerie
                    
            if as_gallery:
                if filter_mode in ["Messier", "Caldwell"]:
                    obj["found"] = is_found
                    objects_to_show.append(obj)
                else:
                    if is_found:
                        obj["found"] = is_found
                        objects_to_show.append(obj)
            else:
                if is_found:
                    obj["found"] = is_found
                    objects_to_show.append(obj)

        # 3. HTML Rendern
        if as_gallery:
            html += '<div class="grid-container">'
            for obj in objects_to_show:
                if filter_mode in ["Messier", "Caldwell"]:
                    prefix = "M" if filter_mode == "Messier" else "C"
                    label = f"{prefix}{obj['sort_key']}"
                    if obj["found"]:
                        img_src = pathlib.Path(obj["image"]).as_uri() if obj["image"] else ""
                        html += f"""<div class="grid-item"><img src="{img_src}" class="grid-thumb" loading="lazy" onerror="this.style.opacity='0'"><div class="status-badge found" title="Gefunden"></div><div class="grid-label">{label}</div></div>"""
                    else:
                        html += f"""<div class="grid-item"><div class="placeholder">?</div><div class="grid-label" style="color: #666;">{label}</div></div>"""
                else:
                    img_src = pathlib.Path(obj["image"]).as_uri() if obj["image"] else ""
                    name_short = obj["name"].split(" (Seestar")[0].split(" (Dwarf")[0].split(" (S30")[0]
                    if len(name_short) > 20: name_short = name_short[:17] + "..."
                    html += f"""<div class="grid-item"><img src="{img_src}" class="grid-thumb" loading="lazy" onerror="this.style.opacity='0'"><div class="grid-label">{name_short}</div></div>"""

            html += '</div></body></html>'

        else: # LIST MODE
            if not objects_to_show:
                 html += "<p>Keine Objekte für diesen Filter (und Zeitraum) gefunden.</p></body></html>"
            else:
                for obj in objects_to_show:
                    internal_id = obj["internal_id"]
                    if internal_id and internal_id in self.ml.index:
                        raw_data = self.ml.index[internal_id]
                        name = generate_pretty_name(raw_data["original_name"], self.ml.caldwell_map, self.ml.reverse_caldwell_map, self.ml.common_names)
                        parent = raw_data.get("parent", "").title()
                    else:
                        name = obj["name"].split(" (")[0]
                        parent = "Unbekannt"
                        
                    otype = obj["type"]
                    tel = obj["telescope"]
                    img_src = pathlib.Path(obj["image"]).as_uri() if obj["image"] else ""
                    stats_txt = f"{obj['fits_count']} Dateien | Letzte: {obj['date']}"

                    ra_deg = None; dec_deg = None
                    if internal_id and internal_id in self.ml.index:
                        if raw_data.get("fits_sample"):
                            try:
                                from utils import read_fits_coords
                                _, r, d, ok = read_fits_coords(raw_data["fits_sample"])
                                if ok: ra_deg, dec_deg = r, d
                            except: pass
                        if ra_deg is None:
                            clean_k = self.ml._get_clean_key(raw_data["original_name"])
                            if clean_k in self.ml.coord_cache:
                                ra_deg = self.ml.coord_cache[clean_k]["ra"]
                                dec_deg = self.ml.coord_cache[clean_k]["dec"]

                    planning_html = ""
                    if ra_deg is not None:
                        obs_info = self.ml.get_best_observation_time(ra_deg, dec_deg)
                        moon_sep, moon_phase = self.ml.get_moon_info(ra_deg, dec_deg)
                        
                        moon_style = "color: #2ecc71;" 
                        if moon_sep < 20: moon_style = "color: #e74c3c; font-weight: bold;" 
                        elif moon_sep < 40: moon_style = "color: #f39c12;" 

                        planning_html = f"""
                        <div style="margin-top: 10px; font-size: 0.9em; border-top: 1px solid #eee; padding-top: 5px;">
                            <div style="color: #2980b9;">🔭 {obs_info}</div>
                            <div style="{moon_style}">🌙 Mond-Distanz: {int(moon_sep)}° (Phase: {int(moon_phase)}%)</div>
                        </div>
                        """
                    
                    html += f"""
                    <div class="card">
                        <img src="{img_src}" class="thumb" onerror="this.style.display='none'">
                        <div class="info">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                <h2>{name}</h2>
                                <span class="tag {otype.lower()}">{otype}</span>
                            </div>
                            <div class="meta">{tel} | {parent}</div>
                            <div class="meta">{stats_txt}</div>
                            {planning_html}
                        </div>
                    </div>
                    """
            html += "</body></html>"
        
        try:
            with open(save_path, "w", encoding="utf-8") as f: f.write(html)
            return True
        except: return False