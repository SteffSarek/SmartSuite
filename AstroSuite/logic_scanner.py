import os
import re
from utils import normalize_string

class LibraryScanner:
    def __init__(self, includes_map):
        self.includes_map = includes_map
        self.index = {}
        self.constellations = {}

    def scan(self, base_folder):
        """Scannt den Ordner und gibt (index, constellations, count) zurück."""
        self.index = {}
        self.constellations = {}
        count = 0
        
        if not base_folder or not os.path.exists(base_folder):
            return {}, {}, "Pfad ungültig."

        try:
            # 1. Physischer Scan
            with os.scandir(base_folder) as const_it:
                for const_entry in const_it:
                    if not const_entry.is_dir() or const_entry.name.startswith(('.', '$')):
                        continue
                        
                    const_name = const_entry.name
                    const_path = const_entry.path
                    
                    with os.scandir(const_path) as obj_it:
                        for obj_entry in obj_it:
                            if not obj_entry.is_dir(): continue
                            
                            obj_name = obj_entry.name
                            obj_path = obj_entry.path
                            
                            c_key = const_name.lower().replace("_", " ")
                            if c_key not in self.constellations: self.constellations[c_key] = []
                            
                            obj_name_lower = obj_name.lower().strip()
                            telescope_type = "other"
                            if "s30" in obj_name_lower: telescope_type = "s30"
                            elif "seestar" in obj_name_lower: telescope_type = "seestar"
                            elif "dwarf" in obj_name_lower: telescope_type = "dwarf"
                            
                            image_files = [] 
                            fits_file = None
                            
                            for root, dirs, files in os.walk(obj_path):
                                for file in files:
                                    lower_file = file.lower()
                                    if lower_file.endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')): 
                                        image_files.append(os.path.join(root, file))
                                    if not fits_file and lower_file.endswith(('.fit', '.fits')): 
                                        fits_file = os.path.join(root, file)
                            
                            # --- SMARTE SORTIERUNG ---
                            def image_sort_key(filepath):
                                filename = os.path.basename(filepath).lower()
                                ext = os.path.splitext(filename)[1]
                                priority = 2
                                if ext in ['.jpg', '.jpeg', '.png']: priority = 0
                                elif ext in ['.tif', '.tiff']: priority = 1
                                return (priority, filename)

                            image_files.sort(key=image_sort_key)

                            preview_image = image_files[0] if image_files else None
                            
                            entry_data = {
                                "path": obj_path, 
                                "image": preview_image, 
                                "images": image_files, 
                                "fits_sample": fits_file, 
                                "original_name": obj_name, 
                                "parent": c_key, 
                                "telescope": telescope_type
                            }
                            
                            # Das Hauptobjekt eintragen
                            self.index[obj_name_lower] = entry_data
                            self.constellations[c_key].append({"name": obj_name, "type": telescope_type})
                            count += 1

                            # --- NEU: MULTIPLE IDs IM ORDNERNAMEN ERKENNEN ---
                            # Findet z.B. "M 89" und "M 90" in "M_89_M_90_Seestar_S50"
                            all_ids = re.findall(r'(?:^|[^a-zA-Z])(M|NGC|IC|C)[_\s-]*(\d+)(?![0-9])', obj_name, re.IGNORECASE)
                            
                            seen_ids = set()
                            unique_ids = []
                            for prefix, num in all_ids:
                                ident = f"{prefix.lower()}{num}"
                                if ident not in seen_ids:
                                    seen_ids.add(ident)
                                    unique_ids.append((prefix, num))

                            # Wenn mehr als eine Katalog-ID gefunden wurde, legen wir virtuelle Zwillinge an
                            if len(unique_ids) > 1:
                                for cat_prefix, num in unique_ids[1:]:
                                    virt_key = f"{cat_prefix.lower()}{num}"
                                    # Nur anlegen, wenn es nicht ohnehin schon als Hauptordner existiert
                                    if virt_key not in self.index:
                                        virt_data = entry_data.copy()
                                        virt_data["original_name"] = f"{cat_prefix.upper()} {num} (in {obj_name})"
                                        self.index[virt_key] = virt_data
                                        self.constellations[c_key].append({"name": f"{cat_prefix.upper()} {num} (via {obj_name})", "type": telescope_type})
                                        count += 1
                            # --------------------------------------------------

                            # Virtuelle Einträge für Ranges (M31-33)
                            range_match = re.search(r'^([M|NGC|IC]+)[_\s]*(\d+)\s*-\s*(\d+)', obj_name, re.IGNORECASE)
                            if range_match:
                                cat_prefix = range_match.group(1).upper()
                                start_num = int(range_match.group(2))
                                end_num = int(range_match.group(3))
                                
                                if start_num < end_num and (end_num - start_num) <= 10:
                                    for i in range(start_num, end_num + 1):
                                        virt_key = f"{cat_prefix.lower()}{i}"
                                        if virt_key not in self.index:
                                            virt_data = entry_data.copy()
                                            virt_data["original_name"] = f"{cat_prefix} {i} (in {obj_name})"
                                            self.index[virt_key] = virt_data
                                            self.constellations[c_key].append({"name": f"{cat_prefix} {i} (via {obj_name})", "type": telescope_type})
                                            count += 1
            
            # 2. Includes anwenden (Für fest definierte Gruppen wie M 31 & M 32)
            count += self._apply_includes()
            return self.index, self.constellations, f"Index aktualisiert! {count} Objekte gefunden."
            
        except Exception as e:
            return {}, {}, f"Fehler beim Scannen: {e}"

    def _apply_includes(self):
        added_count = 0
        existing_keys = list(self.index.keys())
        
        def extract_clean_id(name_str):
            clean = name_str.replace("_", " ").replace("-", " ")
            match = re.search(r'((?:NGC|IC|M|C)\s*\d+)', clean, re.IGNORECASE)
            if match: return match.group(1).upper().replace(" ", "")
            return name_str.upper().replace(" ", "").replace("_", "").replace("-", "")
            
        norm_includes = {}
        for p, children in self.includes_map.items():
            p_clean = p.upper().replace(" ", "")
            c_clean_list = [c.upper().replace(" ", "") for c in children]
            norm_includes[p_clean] = {"original_p": p, "children": c_clean_list, "orig_children": children}
            
        for key in existing_keys:
            current_data = self.index[key]
            my_id = extract_clean_id(current_data["original_name"]) 
            
            # Fall A: Ich bin ein Parent (habe Kinder im JSON)
            if my_id in norm_includes:
                entry = norm_includes[my_id]
                for i, child_clean in enumerate(entry["children"]):
                    child_orig_name = entry["orig_children"][i]
                    child_lower = child_orig_name.lower().strip()
                    if child_lower not in self.index:
                        self.index[child_lower] = current_data.copy()
                        self.index[child_lower]["original_name"] = child_orig_name
                        if current_data["parent"] in self.constellations: 
                            self.constellations[current_data["parent"]].append({"name": child_orig_name + " (via " + entry["original_p"] + ")", "type": current_data["telescope"]})
                        added_count += 1
            
            # Fall B: Ich bin ein Kind (stehe bei jemand anderem im JSON)
            parent_found = None
            parent_orig_name = None
            for p_clean, entry in norm_includes.items():
                if my_id in entry["children"]: 
                    parent_found = p_clean; parent_orig_name = entry["original_p"]; break
            
            if parent_found:
                p_lower = parent_orig_name.lower().strip()
                if p_lower not in self.index:
                    self.index[p_lower] = current_data.copy()
                    self.index[p_lower]["original_name"] = parent_orig_name
                    if current_data["parent"] in self.constellations: 
                        self.constellations[current_data["parent"]].append({"name": parent_orig_name + " (via " + current_data["original_name"] + ")", "type": current_data["telescope"]})
                    added_count += 1
                    
        return added_count