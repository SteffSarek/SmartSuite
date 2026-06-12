import os
import json
import logging
import webbrowser
import traceback
import re
from utils import generate_pretty_name

class AtlasExporter:
    def __init__(self, logic_instance):
        self.logic = logic_instance

    def generate_atlas(self, callback=None):
        try:
            # 1. Sammle alle Objekte und GRUPPIERE Bilder desselben Objekts
            atlas_objects_dict = {}
            date_pattern = re.compile(r'(202\d)[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])')
            
            for key, data in self.logic.index.items():
                pretty_name = generate_pretty_name(
                    data["original_name"], 
                    self.logic.caldwell_map, 
                    self.logic.reverse_caldwell_map, 
                    self.logic.common_names
                )
                
                # --- DIE ATLAS-BREMSE ---
                ignore_names = [
                    "bilder", "sonstiges", "export", "test", "misc", "allgemein", 
                    "mond", "moon", "jupiter", "saturn", "mars", "venus", "sonne", "sun"
                ]
                if pretty_name.lower().strip() in ignore_names:
                    continue
                    
                if data.get("path") and "xxx_" in data.get("path").lower():
                    continue
                # -----------------------------
                
                obj_data = self.logic.get_object_data(key, exact_match=True)
                
                # Echte Cache-Koordinaten bevorzugen
                ra = None
                dec = None
                clean_k = self.logic._get_clean_key(pretty_name)
                
                if clean_k in self.logic.coord_cache:
                    ra = self.logic.coord_cache[clean_k]["ra"]
                    dec = self.logic.coord_cache[clean_k]["dec"]
                else:
                    ra = obj_data.get("ra_decimal")
                    dec = obj_data.get("dec_decimal")
                
                if ra is not None and dec is not None:
                    # --- BLITZSCHNELLER DATUM-SCANNER ---
                    obj_dates = []
                    if data.get("path") and os.path.isdir(data["path"]):
                        try:
                            for file in os.listdir(data["path"]):
                                match = date_pattern.search(file)
                                if match:
                                    obj_dates.append(f"{match.group(1)}-{match.group(2)}-{match.group(3)}")
                        except:
                            pass
                    
                    # Fallback auf das Index-Zentraldatum, falls keine Einzeldaten im Ordner gefunden wurden
                    if not obj_dates and obj_data.get("date") and obj_data["date"] != "---":
                        try:
                            parts = obj_data["date"].split('.')
                            if len(parts) == 3:
                                obj_dates.append(f"{parts[2]}-{parts[1]}-{parts[0]}")
                        except:
                            pass
                    # ------------------------------------

                    imgs = obj_data.get("images", [])
                    if not imgs and obj_data.get("image"):
                        imgs = [obj_data.get("image")]
                        
                    # Nur Browser-kompatible Formate zulassen
                    valid_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                    clean_imgs = []
                    for p in imgs:
                        if os.path.exists(p):
                            ext = os.path.splitext(p)[1].lower()
                            if ext in valid_exts:
                                clean_imgs.append(f"file:///{p.replace('\\', '/')}")
                    
                    if not clean_imgs: continue
                    
                    if pretty_name not in atlas_objects_dict:
                        atlas_objects_dict[pretty_name] = {
                            "name": pretty_name,
                            "ra": float(ra),
                            "dec": float(dec),
                            "images": clean_imgs,
                            "dates": obj_dates,
                            "wiki_url": obj_data.get("wiki_url", "")
                        }
                    else:
                        for img in clean_imgs:
                            if img not in atlas_objects_dict[pretty_name]["images"]:
                                atlas_objects_dict[pretty_name]["images"].append(img)
                        atlas_objects_dict[pretty_name]["dates"].extend(obj_dates)

            # Gefundene Datums-Arrays konsolidieren und formatieren
            for obj in atlas_objects_dict.values():
                if obj["dates"]:
                    unique_dates = sorted(list(set(obj["dates"])))
                    p_first = unique_dates[0].split('-')
                    p_last = unique_dates[-1].split('-')
                    obj["first_obs"] = f"{p_first[2]}.{p_first[1]}.{p_first[0]}"
                    obj["last_obs"] = f"{p_last[2]}.{p_last[1]}.{p_last[0]}"
                else:
                    obj["first_obs"] = "---"
                    obj["last_obs"] = "---"
                del obj["dates"]

            atlas_objects = list(atlas_objects_dict.values())

            # Aladin Layer Sortierungs-Reihenfolge (Messier nach oben)
            def sort_importance(obj):
                score = len(obj["images"]) * 100
                if "M " in obj["name"]: score += 50
                elif "NGC " in obj["name"]: score += 20
                return score
            atlas_objects.sort(key=sort_importance)

            if not atlas_objects:
                if callback: callback(False, "Keine aufgelösten Bilder im Archiv gefunden!")
                return False

            export_dir = self.logic.get_export_path()
            if not export_dir or not os.path.isdir(export_dir):
                export_dir = self.logic.app_path
                
            output_html_path = os.path.join(export_dir, "Mein_Himmelsatlas.html")

            # 3. Das HTML/JavaScript-Template (Mit Custom-Sidebar & Advanced Links)
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Mein Persönlicher Himmelsatlas</title>
    <link rel="stylesheet" href="https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.css" />
    <style>
        body, html {{
            margin: 0; padding: 0; width: 100%; height: 100%;
            background-color: #111; color: #fff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            overflow: hidden;
        }}
        #aladin-lite-div {{
            width: 100%; height: 100vh;
        }}
        
        #atlas-title {{
            position: absolute; top: 15px; left: 50%; transform: translateX(-50%); z-index: 1000;
            background: rgba(20, 20, 20, 0.85); padding: 10px 20px;
            border-radius: 8px; border: 1px solid #3498db;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5); pointer-events: none;
            text-align: center;
        }}
        h1 {{ margin: 0; font-size: 18px; color: #3498db; font-weight: bold; }}
        #atlas-title span {{ font-size: 12px; color: #aaa; }}
        
        #side-panel {{
            position: absolute; top: 0; right: -450px;
            width: 400px; height: 100vh; background: rgba(15, 15, 15, 0.95);
            border-left: 2px solid #3498db; box-shadow: -5px 0 25px rgba(0,0,0,0.8);
            z-index: 2000; transition: right 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            overflow-y: auto; padding: 25px; box-sizing: border-box; color: #fff;
        }}
        #close-panel {{
            float: right; background: none; border: none; color: #888; font-size: 24px; cursor: pointer; margin-top: -5px;
        }}
        #close-panel:hover {{ color: #e74c3c; }}
        #panel-title {{ margin-top: 0; color: #3498db; font-size: 22px; margin-bottom: 5px; }}
        #panel-coords {{ font-size: 14px; color: #aaa; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #333; line-height: 1.5; }}
        #panel-coords b {{ color: #ddd; }}
        
        /* Styling für die neuen Info-Links */
        .panel-link-container {{ margin-top: 12px; margin-bottom: 5px; }}
        .atlas-btn {{
            display: inline-block; padding: 5px 10px; margin-right: 8px; margin-bottom: 5px;
            border-radius: 4px; border: 1px solid #3498db; color: #3498db;
            text-decoration: none; font-size: 12px; font-weight: bold; transition: all 0.2s;
        }}
        .atlas-btn:hover {{ background: #3498db; color: #fff; }}
        
        .panel-img-container {{ margin-bottom: 20px; text-align: center; }}
        .panel-img {{
            max-width: 100%; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.6);
            cursor: pointer; transition: transform 0.2s; border: 1px solid #333;
        }}
        .panel-img:hover {{ transform: scale(1.02); border-color: #3498db; }}
    </style>
</head>
<body>

    <div id="atlas-title">
        <h1>Mein Himmelsatlas</h1>
        <span>Erstellt mit {len(atlas_objects)} Himmelskoordinaten</span>
    </div>

    <div id="side-panel">
        <button id="close-panel" onclick="document.getElementById('side-panel').style.right = '-450px';">✖</button>
        <h2 id="panel-title">Objektname</h2>
        <div id="panel-coords"></div>
        <div id="panel-images"></div>
    </div>

    <div id="aladin-lite-div"></div>

    <script src="https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js" charset="utf-8"></script>
    <script>
        const myPhotos = {json.dumps(atlas_objects, indent=4)};

        A.init.then(() => {{
            const aladin = A.aladin('#aladin-lite-div', {{
                survey: "P/DSS2/color", 
                fov: 60, 
                target: "00 42 44.3 +41 16 09", 
                cooFrame: "ICRS"
            }});

            const markerLayer = A.catalog({{
                name: 'Meine Astrofotos', 
                color: '#3498db', 
                shape: 'circle', 
                sourceSize: 14
            }});
            aladin.addCatalog(markerLayer);

            myPhotos.forEach(function(photo) {{
                const source = A.source(photo.ra, photo.dec, photo);
                markerLayer.addSources([source]);
            }});

            aladin.on('objectClicked', function(object) {{
                if (object) {{
                    const data = object.data;
                    
                    document.getElementById('panel-title').innerText = data.name;
                    
                    // --- STRUKTURIERTE INFO-BOX BAUEN ---
                    let coordsHtml = '<b>RA:</b> ' + data.ra.toFixed(4) + '° | <b>DEC:</b> ' + data.dec.toFixed(4) + '°<br>';
                    coordsHtml += '<span style="font-size:12px; color:#999; display:block; margin-top:6px;">';
                    coordsHtml += '📅 <b>Erste Aufnahme:</b> ' + data.first_obs + '<br>';
                    coordsHtml += '📅 <b>Letzte Aufnahme:</b> ' + data.last_obs + '</span>';
                    
                    // --- NEU: Schnelle und exakte Link-Generierung für Stellarium & AstroBin ---
                    let searchName = '';
                    let matchNGC = data.name.match(/NGC\s*(\d+)/i);
                    let matchM = data.name.match(/M\s*(\d+)/i);
                    let matchIC = data.name.match(/IC\s*(\d+)/i);
                    
                    // Priorität: NGC > M > IC, da Stellarium damit am besten umgeht
                    if (matchNGC) searchName = 'NGC' + matchNGC[1];
                    else if (matchM) searchName = 'M' + matchM[1];
                    else if (matchIC) searchName = 'IC' + matchIC[1];
                    
                    let linksHtml = '<div class="panel-link-container">';
                    if (data.wiki_url) {{
                        linksHtml += '<a href="' + data.wiki_url + '" target="_blank" class="atlas-btn">🌐 Wikipedia</a>';
                    }}
                    if (searchName) {{
                        linksHtml += '<a href="https://stellarium-web.org/skysource/' + searchName + '" target="_blank" class="atlas-btn">✨ Stellarium</a>';
                        linksHtml += '<a href="https://www.astrobin.com/search/?q=' + searchName + '" target="_blank" class="atlas-btn">📷 AstroBin</a>';
                    }}
                    linksHtml += '</div>';
                    
                    document.getElementById('panel-coords').innerHTML = coordsHtml + linksHtml;
                    // ------------------------------------
                    
                    let imgsHtml = '';
                    data.images.forEach(function(imgUrl, index) {{
                        imgsHtml += '<div class="panel-img-container">';
                        if (data.images.length > 1) {{
                            imgsHtml += '<span style="font-size:12px; color:#777;">Version ' + (index+1) + '</span><br>';
                        }}
                        imgsHtml += '<a href="' + imgUrl + '" target="_blank">';
                        imgsHtml += '<img src="' + imgUrl + '" class="panel-img" />';
                        imgsHtml += '</a></div>';
                    }});
                    document.getElementById('panel-images').innerHTML = imgsHtml;
                    document.getElementById('side-panel').style.right = '0px';
                }} else {{
                    document.getElementById('side-panel').style.right = '-450px';
                }}
            }});
        }});
    </script>
</body>
</html>
"""
            with open(output_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            webbrowser.open(f"file:///{output_html_path.replace('\\', '/')}")
            
            if callback: callback(True, "Himmelsatlas erfolgreich im Browser geöffnet!")
            return True
            
        except Exception as e:
            logging.error(f"Fehler beim Erstellen des Atlas: {e}\n{traceback.format_exc()}")
            if callback: callback(False, f"Kritischer Fehler: {e}")
            return False