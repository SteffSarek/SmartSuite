import customtkinter as ctk
from PIL import Image, ImageTk
import os
import webbrowser 
import sys 
import re 
import logging
import threading
import json                            # <--- NEU
from tkinter import ttk, messagebox    # <--- NEU
from utils import get_remote_version
from version import VERSION 

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ImageViewerWindow(ctk.CTkToplevel):
    def __init__(self, parent, image_input, start_index=0, obj_name=""):
        super().__init__(parent)
        
        if isinstance(image_input, str):
            self.image_list = [image_input]
            self.current_index = 0
        else:
            self.image_list = image_input
            self.current_index = start_index

        self.obj_name = obj_name
        self.is_playing = False
        self.is_fullscreen = False
        self.slideshow_job = None
        
        self.title(f"Ansicht: {obj_name}")
        self.geometry("1100x850") 
        self.minsize(800, 600)
        
        # --- DER FOKUS FIX ---
        self.lift()
        self.attributes('-topmost', True)
        self.after(500, lambda: self.attributes('-topmost', False))
        self.after(600, self.focus_force)
        # ---------------------
        
        self._init_ui()
        self._bind_keys()
        
        self.after(250, lambda: self.show_image(self.current_index))

    def iconbitmap(self, bitmap=None, default=None):
        try:
            super().iconbitmap(bitmap=bitmap, default=default)
        except Exception:
            pass

    def _init_ui(self):
        self.controls_frame = ctk.CTkFrame(self, height=70, fg_color="#222222", corner_radius=0)
        self.controls_frame.pack(fill="x", side="bottom")
        
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, side="top")
        
        self.img_label = ctk.CTkLabel(self.main_frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=0, pady=0)
        
        btn_opts = {"width": 40, "height": 40, "corner_radius": 20, "fg_color": "#444", "hover_color": "#666"}
        
        self.btn_fullscreen = ctk.CTkButton(self.controls_frame, text="⛶", command=self.toggle_fullscreen, **btn_opts)
        self.btn_fullscreen.pack(side="right", padx=10, pady=10)

        self.btn_next = ctk.CTkButton(self.controls_frame, text="▶", command=self.next_image, **btn_opts)
        self.btn_next.pack(side="right", padx=(10, 20), pady=10)
        
        self.btn_prev = ctk.CTkButton(self.controls_frame, text="◀", command=self.prev_image, **btn_opts)
        self.btn_prev.pack(side="left", padx=(20, 10), pady=10)
        
        self.lbl_counter = ctk.CTkLabel(self.controls_frame, text="0 / 0", font=("Arial", 14))
        self.lbl_counter.pack(side="left", padx=10)
        
        self.btn_play = ctk.CTkButton(self.controls_frame, text="▶ Play", command=self.toggle_slideshow, width=70, height=30, fg_color="#2ecc71", hover_color="#27ae60")
        self.btn_play.pack(side="left", padx=20)

        self.solve_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.solve_frame.pack(side="left", fill="x", expand=True, padx=20)
        
        self.btn_solve = ctk.CTkButton(self.solve_frame, text="🧩 Solve", width=100, height=30, 
                                       fg_color="#D35400", hover_color="#A04000",
                                       command=self.start_solving)
        self.btn_solve.pack(side="left")
        
        self.lbl_solve_status = ctk.CTkLabel(self.solve_frame, text="", text_color="orange", font=("Arial", 11))
        self.lbl_solve_status.pack(side="left", padx=10)

    def _bind_keys(self):
        self.bind("<Left>", lambda e: self.prev_image())
        self.bind("<Right>", lambda e: self.next_image())
        self.bind("<space>", lambda e: self.toggle_slideshow())
        self.bind("<Escape>", lambda e: self.exit_fullscreen_or_close())
        self.bind("<f>", lambda e: self.toggle_fullscreen())
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        if event.widget == self:
            if hasattr(self, "_resize_job") and self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(300, lambda: self.show_image(self.current_index))

    def start_solving(self):
        current_key = self.master.logic.get_astrometry_key()
        if not current_key: return
        current_img_path = self.image_list[self.current_index]
        self.btn_solve.configure(state="disabled", text="⏳")
        self.lbl_solve_status.configure(text="Starte...", text_color="yellow")
        threading.Thread(target=self._run_solve_thread, args=(current_img_path,), daemon=True).start()

    def _run_solve_thread(self, img_path):
        def update_gui(text, color="yellow"):
            self.lbl_solve_status.configure(text=text, text_color=color)
        def logic_callback(msg):
            update_gui(msg)
        result = self.master.logic.solve_image_astrometry(img_path, logic_callback)
        if result:
            update_gui("✅ Gelöst!", "green")
            self.btn_solve.configure(state="normal", text="✅ Solved", fg_color="green")
        else:
            self.btn_solve.configure(state="normal", text="🧩 Solve")

    def show_image(self, index):
        if index != self.current_index:
             self.lbl_solve_status.configure(text="")
             self.btn_solve.configure(state="normal", text="🧩 Solve", fg_color="#D35400")

        if not self.image_list: return
        self.current_index = index % len(self.image_list)
        img_path = self.image_list[self.current_index]
        self.lbl_counter.configure(text=f"{self.current_index + 1} / {len(self.image_list)}")
        self.title(f"{self.obj_name} ({self.current_index + 1}/{len(self.image_list)}) - {os.path.basename(img_path)}")

        try:
            from PIL import Image
            pil_img = Image.open(img_path)
            
            win_w = self.main_frame.winfo_width()
            win_h = self.main_frame.winfo_height()
            
            if win_w < 100: win_w = 1000
            if win_h < 100: win_h = 740

            img_ratio = pil_img.width / pil_img.height
            win_ratio = win_w / win_h
            
            if img_ratio > win_ratio:
                new_w = win_w
                new_h = int(win_w / img_ratio)
            else:
                new_h = win_h
                new_w = int(win_h * img_ratio)
            
            new_w = max(1, new_w)
            new_h = max(1, new_h)

            self.ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
            self.img_label.configure(image=self.ctk_img, text="")

        except Exception as e:
            # --- FIX: Unlesbare Bilder (z.B. 32bit TIF) elegant überspringen ---
            self.img_label.configure(image=None, text=f"Überspringe unlesbares Bild...\n{os.path.basename(img_path)}")
            
            if len(self.image_list) > 1:
                # 1. Defektes Bild aus der aktuellen Wiedergabeliste werfen
                self.image_list.pop(self.current_index)
                
                # 2. Timer abbrechen, falls die Slideshow läuft
                if getattr(self, 'is_playing', False) and self.slideshow_job:
                    self.after_cancel(self.slideshow_job)
                
                # 3. Funktion: Lädt das nächste Bild und führt die Slideshow weiter
                def skip_and_resume():
                    self.show_image(self.current_index) # Lädt das nachgerückte Bild
                    if getattr(self, 'is_playing', False):
                        self.slideshow_job = self.after(2000, self._slideshow_step)
                        
                # 4. Zeigt den Hinweis 0.8 Sekunden an und springt dann automatisch weiter
                self.after(800, skip_and_resume)
            else:
                # Falls es das allerletzte/einzige Bild war, beende die Slideshow
                if getattr(self, 'is_playing', False):
                    self.stop_slideshow_and_close()
            # -------------------------------------------------------------------

    def next_image(self):
        self.show_image(self.current_index + 1)

    def prev_image(self):
        self.show_image(self.current_index - 1)

    def toggle_slideshow(self):
        if self.is_playing:
            self.is_playing = False
            self.btn_play.configure(text="▶ Play", fg_color="#2ecc71", hover_color="#27ae60")
            if self.slideshow_job:
                self.after_cancel(self.slideshow_job)
                self.slideshow_job = None
        else:
            self.is_playing = True
            self.btn_play.configure(text="⏸ Pause", fg_color="#e74c3c", hover_color="#c0392b")
            self._slideshow_step()

    def _slideshow_step(self):
        if self.is_playing:
            self.next_image()
            self.slideshow_job = self.after(2000, self._slideshow_step)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen: 
            self.controls_frame.pack_forget()
            self.attributes("-fullscreen", True)
        else: 
            self.attributes("-fullscreen", False)
            self.controls_frame.pack(fill="x", side="bottom")
        
        self.after(100, lambda: self.show_image(self.current_index))

    def exit_fullscreen_or_close(self):
        if self.is_fullscreen: self.toggle_fullscreen()
        else: self.stop_slideshow_and_close()

    def stop_slideshow_and_close(self):
        if self.slideshow_job: self.after_cancel(self.slideshow_job)
        self.destroy()

class ConstellationSelectionDialog(ctk.CTkToplevel):
    def __init__(self, parent, const_list, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("Sternbild auswählen")
        self.geometry("400x220") 
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        try: self.after(100, self.focus_force)
        except: pass
        ctk.CTkLabel(self, text="Bitte Sternbild wählen:", font=ctk.CTkFont(size=16)).pack(pady=(25, 15))
        self.const_var = ctk.StringVar(value=const_list[0] if const_list else "")
        self.combo = ctk.CTkOptionMenu(self, values=const_list, variable=self.const_var, width=250)
        self.combo.pack(pady=10)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Anzeigen", width=100, command=self.on_confirm).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Abbrechen", width=100, fg_color="gray", command=self.destroy).pack(side="left", padx=10)
    def on_confirm(self):
        selection = self.const_var.get()
        if selection:
            self.destroy()
            self.master.after(50, lambda: self.callback(selection))

class ReportSelectionDialog(ctk.CTkToplevel):
    def __init__(self, parent, const_list, callback):
        super().__init__(parent)
        self.callback = callback
        self.constellations = const_list
        self.title("Report Exportieren")
        self.geometry("450x550") 
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        try: self.after(100, self.focus_force)
        except: pass
        ctk.CTkLabel(self, text="Welche Daten sollen exportiert werden?", font=ctk.CTkFont(size=16)).pack(pady=(20, 10))
        self.radio_var = ctk.StringVar(value="Alle")
        modes = [("Gesamtes Archiv", "Alle"), ("Nur Messier", "Messier"), ("Nur Caldwell", "Caldwell"), ("Nach Sternbild", "Sternbild")]
        for text, mode in modes:
            ctk.CTkRadioButton(self, text=text, variable=self.radio_var, value=mode, command=self.toggle_combo).pack(pady=5, padx=40, anchor="w")
        self.combo_const = ctk.CTkComboBox(self, values=self.constellations, state="disabled")
        self.combo_const.pack(pady=5, padx=40, fill="x")
        ctk.CTkLabel(self, text="Zeitraum filtern (Format TT.MM.JJJJ):").pack(pady=(15, 5))
        self.date_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.date_frame.pack(fill="x", padx=40)
        self.entry_start = ctk.CTkEntry(self.date_frame, placeholder_text="Von (z.B. 01.01.2025)")
        self.entry_start.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_end = ctk.CTkEntry(self.date_frame, placeholder_text="Bis (z.B. 31.12.2026)")
        self.entry_end.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.gallery_var = ctk.BooleanVar(value=False)
        self.chk_gallery = ctk.CTkCheckBox(self, text="Als Galerie (Grid) anzeigen", variable=self.gallery_var)
        self.chk_gallery.pack(pady=(15, 5), padx=40, anchor="w")
        ctk.CTkButton(self, text="HTML Erstellen", fg_color="green", command=self.on_confirm).pack(pady=20)
    def toggle_combo(self):
        mode = self.radio_var.get()
        if mode == "Sternbild":
            self.combo_const.configure(state="normal")
            self.chk_gallery.configure(state="disabled") 
            self.gallery_var.set(False)
        elif mode == "Alle":
            self.combo_const.configure(state="disabled")
            self.chk_gallery.configure(state="disabled") 
            self.gallery_var.set(False)
        else:
            self.combo_const.configure(state="disabled")
            self.chk_gallery.configure(state="normal") 
    def on_confirm(self):
        mode = self.radio_var.get()
        val = None
        if mode == "Sternbild": val = self.combo_const.get()
        d_start = self.entry_start.get().strip()
        d_end = self.entry_end.get().strip()
        if not d_start: d_start = None
        if not d_end: d_end = None
        self.callback(mode, val, self.gallery_var.get(), d_start, d_end)
        self.destroy()

class MissingObjectsWindow(ctk.CTkToplevel):
    def __init__(self, parent, catalog_name, missing_list):
        super().__init__(parent)
        self.title(f"Fehlende Objekte ({catalog_name})")
        self.geometry("500x600")
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()
        
        ctk.CTkLabel(self, text=f"Dir fehlen noch {len(missing_list)} Objekte:", font=("Arial", 16, "bold")).pack(pady=10)
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        text_data = "\n".join(missing_list)
        lbl = ctk.CTkLabel(scroll, text=text_data, justify="left", anchor="nw")
        lbl.pack(fill="both", expand=True)

class AboutWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Über AstroArchive")
        self.geometry("400x600") 
        self.resizable(False, False)
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.current_version = VERSION
        self.drive_folder_url = "https://drive.google.com/drive/folders/1fYalfxFzPj7KB07GwEpmagPglJXit5Mi?usp=sharing"
        self.version_file_url = "https://drive.google.com/uc?export=download&id=1jBAAEC3WE5jh9OROUJgpt_44snknWqSu" 
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(expand=True, fill="both", padx=20, pady=20)
        img_path = resource_path("astroarchive.png")
        if os.path.exists(img_path):
            try:
                pil_img = Image.open(img_path)
                self.logo_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(150, 150))
                self.lbl_logo = ctk.CTkLabel(self.container, text="", image=self.logo_img)
                self.lbl_logo.pack(pady=(10, 20))
            except Exception as e: print(f"Fehler beim Laden des Logos: {e}")
        ctk.CTkLabel(self.container, text="AstroArchive Explorer", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(0, 5))
        ctk.CTkLabel(self.container, text=f"Version {self.current_version}", font=ctk.CTkFont(size=16)).pack(pady=(0, 20))
        desc_text = "Verwalte deine Seestar S50, S30 und\nDwarf II/3 Aufnahmen."
        ctk.CTkLabel(self.container, text=desc_text, font=ctk.CTkFont(size=14), text_color="gray80").pack(pady=(0, 20))
        ctk.CTkLabel(self.container, text="Copyright © 2026 Stefan Raphael", font=ctk.CTkFont(size=12), text_color="gray60").pack(pady=(0, 5))
        ctk.CTkLabel(self.container, text="This program comes with absolute no warranty.", font=ctk.CTkFont(size=12), text_color="gray60").pack(pady=(0, 0))
        license_lbl = ctk.CTkLabel(self.container, text="GNU General License Version 3", font=ctk.CTkFont(size=12, underline=True), text_color="#3B8ED0", cursor="hand2")
        license_lbl.pack(pady=(0, 15))
        license_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://www.gnu.org/licenses/gpl-3.0.html"))
        self.update_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.update_frame.pack(fill="x", pady=10)
        self.lbl_update_status = ctk.CTkLabel(self.update_frame, text="", font=ctk.CTkFont(size=12))
        self.lbl_update_status.pack(pady=(0, 5))
        self.btn_check_update = ctk.CTkButton(self.update_frame, text="☁  Auf Updates prüfen", fg_color="transparent", border_width=1, text_color="gray90", command=self.check_for_updates)
        self.btn_check_update.pack(pady=5)
        self.btn_download = ctk.CTkButton(self.update_frame, text="⬇  Zum Download Ordner", fg_color="green", text_color="white", command=lambda: webbrowser.open(self.drive_folder_url))
        ctk.CTkButton(self.container, text="Schließen", width=200, command=self.destroy).pack(side="bottom", pady=10)

    def check_for_updates(self):
        self.lbl_update_status.configure(text="Verbinde...", text_color="yellow")
        self.btn_check_update.configure(state="disabled")
        self.update() 
        remote_version = get_remote_version(self.version_file_url)
        if remote_version:
            clean_remote = remote_version.strip().replace("Version", "").strip()
            if clean_remote != self.current_version:
                self.lbl_update_status.configure(text=f"Neu: Version {clean_remote} verfügbar!", text_color="green")
                self.btn_check_update.pack_forget() 
                self.btn_download.pack(pady=5) 
            else:
                self.lbl_update_status.configure(text="Du bist auf dem neuesten Stand.", text_color="gray70")
                self.btn_check_update.configure(state="normal")
        else:
            self.lbl_update_status.configure(text="Fehler beim Abruf (Kein Internet?)", text_color="red")
            self.btn_check_update.configure(state="normal")
            
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, logic, on_save_callback=None):
        super().__init__(parent)
        self.logic = logic
        self.on_save_callback = on_save_callback
        
        self.title("Einstellungen")
        self.geometry("500x680") # Etwas höher gemacht für den neuen Platz
        self.resizable(False, False)
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()
        
        ctk.CTkLabel(self, text="Programm Einstellungen", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))
        
        loc_frame = ctk.CTkFrame(self)
        loc_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(loc_frame, text="Dein Standort (für Beobachtungszeit)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        coord_frame = ctk.CTkFrame(loc_frame, fg_color="transparent")
        coord_frame.pack(pady=(0, 10))
        
        ctk.CTkLabel(coord_frame, text="Breitengrad (Lat):").grid(row=0, column=0, padx=5, pady=5)
        self.entry_lat = ctk.CTkEntry(coord_frame, width=80)
        self.entry_lat.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(coord_frame, text="Längengrad (Lon):").grid(row=0, column=2, padx=5, pady=5)
        self.entry_lon = ctk.CTkEntry(coord_frame, width=80)
        self.entry_lon.grid(row=0, column=3, padx=5, pady=5)
        
        current_lat, current_lon = self.logic.get_location()
        self.entry_lat.insert(0, str(current_lat))
        self.entry_lon.insert(0, str(current_lon))
        
        api_frame = ctk.CTkFrame(self)
        api_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(api_frame, text="Astrometry.net API Key", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        self.entry_api = ctk.CTkEntry(api_frame, width=300)
        self.entry_api.pack(pady=(0, 10))
        current_api = self.logic.get_astrometry_key()
        if current_api: self.entry_api.insert(0, current_api)
        
        export_frame = ctk.CTkFrame(self)
        export_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(export_frame, text="Standard Export-Ordner (Google Drive etc.)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        path_frame = ctk.CTkFrame(export_frame, fg_color="transparent")
        path_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.entry_export = ctk.CTkEntry(path_frame)
        self.entry_export.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        btn_browse = ctk.CTkButton(path_frame, text="📂", width=40, command=self.browse_export_path)
        btn_browse.pack(side="right")
        
        current_export = self.logic.get_export_path()
        if current_export: self.entry_export.insert(0, current_export)
        
        # --- NEU: EXTERNE TOOLS (ASTAP & ALADIN) ---
        tools_frame = ctk.CTkFrame(self)
        tools_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(tools_frame, text="Lokale Tools (ASTAP & Aladin)", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5))
        
        astap_sub = ctk.CTkFrame(tools_frame, fg_color="transparent")
        astap_sub.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(astap_sub, text="ASTAP:", width=50, anchor="w").pack(side="left") # Festes Label
        self.entry_astap = ctk.CTkEntry(astap_sub, placeholder_text="Pfad zur astap.exe")
        self.entry_astap.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(astap_sub, text="📂", width=30, command=lambda: self.browse_exe(self.entry_astap)).pack(side="right")
        
        if hasattr(self.logic, 'get_astap_path'):
            self.entry_astap.insert(0, self.logic.get_astap_path())
        
        aladin_sub = ctk.CTkFrame(tools_frame, fg_color="transparent")
        aladin_sub.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkLabel(aladin_sub, text="Aladin:", width=50, anchor="w").pack(side="left") # Festes Label
        self.entry_aladin = ctk.CTkEntry(aladin_sub, placeholder_text="Pfad zur Aladin.exe")
        self.entry_aladin.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(aladin_sub, text="📂", width=30, command=lambda: self.browse_exe(self.entry_aladin)).pack(side="right")
        
        if hasattr(self.logic, 'get_aladin_path'):
            self.entry_aladin.insert(0, self.logic.get_aladin_path())
        # -------------------------------------------
        
        ctk.CTkButton(self, text="💾 Speichern", fg_color="green", hover_color="darkgreen", command=self.save_settings).pack(pady=20)
        
    def browse_export_path(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory()
        if folder:
            self.entry_export.delete(0, "end")
            self.entry_export.insert(0, folder)
            
    def browse_exe(self, entry_widget):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Programmdatei", "*.exe"), ("Alle Dateien", "*.*")])
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)
            
    def save_settings(self):
        try:
            lat = float(self.entry_lat.get().strip().replace(',', '.'))
            lon = float(self.entry_lon.get().strip().replace(',', '.'))
            self.logic.set_location(lat, lon)
        except ValueError:
            pass 
            
        self.logic.set_astrometry_key(self.entry_api.get().strip())
        self.logic.set_export_path(self.entry_export.get().strip())
        self.logic.set_astap_path(self.entry_astap.get().strip())
        self.logic.set_aladin_path(self.entry_aladin.get().strip())
        
        if self.on_save_callback:
            self.on_save_callback()
        self.destroy()

class WimsImportWindow(ctk.CTkToplevel):
    def __init__(self, parent, wims_objects, on_import_callback):
        super().__init__(parent)
        self.title("📥 WIMS Import")
        self.geometry("800x600")
        
        self.transient(parent) 
        self.grab_set()        
        
        self.wims_objects = wims_objects
        self.on_import_callback = on_import_callback
        self.checkboxes = []
        
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(self.top_frame, text="WIMS Planungs-Import", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        
        self.btn_toggle_all = ctk.CTkButton(self.top_frame, text="Alle an/abwählen", width=120, command=self.toggle_all)
        self.btn_toggle_all.pack(side="right")
        
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        for obj in self.wims_objects:
            row_frame = ctk.CTkFrame(self.scroll)
            row_frame.pack(fill="x", pady=2)
            
            var = ctk.BooleanVar(value=True) 
            self.checkboxes.append((var, obj))
            
            chk = ctk.CTkCheckBox(row_frame, text="", variable=var, width=30)
            chk.pack(side="left", padx=10, pady=10)
            
            status = "✅ Im Archiv" if obj["found"] else "❌ Neu (Geplant)"
            color = "#2ecc71" if obj["found"] else "#e74c3c"
            
            name_lbl = ctk.CTkLabel(row_frame, text=f"{obj['wims_name']}  ", font=ctk.CTkFont(weight="bold", size=14))
            name_lbl.pack(side="left")
            
            if obj['alt_name']:
                ctk.CTkLabel(row_frame, text=f"({obj['alt_name']})  ", text_color="gray").pack(side="left")
                
            ctk.CTkLabel(row_frame, text=f"|  Score: {obj['score']}  |  Mag: {obj['mag']}  |  Typ: {obj['type']}  |  ", text_color="#f39c12").pack(side="left")
            ctk.CTkLabel(row_frame, text=status, text_color=color).pack(side="left")
        
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(fill="x", padx=20, pady=10)
        
        self.btn_import = ctk.CTkButton(self.bottom_frame, text="📥 Ausgewählte importieren", font=ctk.CTkFont(weight="bold"), fg_color="#27ae60", hover_color="#2ecc71", command=self.do_import)
        self.btn_import.pack(side="right")
        
        self.btn_cancel = ctk.CTkButton(self.bottom_frame, text="Abbrechen", fg_color="gray", hover_color="#555", command=self.close_window)
        self.btn_cancel.pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.close_window)
        
    def toggle_all(self):
        any_false = any(not var.get() for var, _ in self.checkboxes)
        for var, _ in self.checkboxes:
            var.set(any_false)
            
    def close_window(self):
        self.grab_release()
        self.destroy()

    def do_import(self):
        selected = [obj for var, obj in self.checkboxes if var.get()]
        cb = self.on_import_callback
        
        self.grab_release()
        self.destroy()
        self.master.after(100, lambda: cb(selected))
      
class CatalogEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent, logic):
        super().__init__(parent)
        self.logic = logic
        self.title("Datenbank & Katalog Editor")
        self.geometry("850x650")
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        try: self.after(100, self.focus_force)
        except: pass

        self.catalog_path = self.logic.catalog_file
        
        # 1. Daten in den Arbeitsspeicher laden
        self.data = {
            "caldwell": {},
            "common_names": {},
            "constellations": {},
            "includes": {}
        }
        
        if os.path.exists(self.catalog_path):
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Datei nicht lesen: {e}")

        # 2. UI Aufbau
        ctk.CTkLabel(self, text="Eigene Datenbank-Einträge bearbeiten", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text="Das Programm kümmert sich automatisch um die korrekte JSON-Formatierung.", text_color="gray").pack()

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=10)

        # Tabs erstellen
        self._build_tab("Eigennamen", "common_names", "Suchbegriff (z.B. andromeda)", "Katalog-ID (z.B. M 31)")
        self._build_tab("Caldwell", "caldwell", "Caldwell-Nr. (z.B. 14)", "NGC/IC Alias (z.B. NGC 869)")
        self._build_tab("Sternbilder", "constellations", "Interner Name (z.B. orion)", "Anzeigename (z.B. Orion)")
        self._build_tab("Gruppen (Includes)", "includes", "Haupt-Objekt (z.B. M 31)", "Zugehörig (z.B. M 32, M 110)", is_list=True)

        # 3. Footer Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkButton(btn_frame, text="Abbrechen", fg_color="#c0392b", hover_color="#e74c3c", command=self.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="💾 Bulletproof Speichern", fg_color="#27ae60", hover_color="#2ecc71", command=self.save_data).pack(side="right")

    def _build_tab(self, tab_title, dict_key, col1_title, col2_title, is_list=False):
        tab = self.tabview.add(tab_title)
        
        # --- KORRIGIERTER STYLE ---
        style = ttk.Style()
        style.theme_use("default")
        
        # Wir modifizieren den Standard-Treeview-Style direkt, das ist ausfallsicher!
        style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b", rowheight=25, borderwidth=0)
        style.map("Treeview", background=[('selected', '#3498db')])
        style.configure("Treeview.Heading", background="#565b5e", foreground="white", font=('Arial', 10, 'bold'))
        # --------------------------

        # Tabelle (nutzt jetzt den Standard-Style)
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("col1", "col2"), show="headings")
        tree.heading("col1", text=col1_title)
        tree.heading("col2", text=col2_title)
        tree.column("col1", width=200)
        tree.column("col2", width=400)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        # Daten einfüllen
        def refresh_list():
            for item in tree.get_children():
                tree.delete(item)
            for k, v in self.data[dict_key].items():
                val_str = ", ".join(v) if is_list else v
                tree.insert("", "end", values=(k, val_str))

        refresh_list()

        # Eingabemaske
        input_frame = ctk.CTkFrame(tab, fg_color="transparent")
        input_frame.pack(fill="x", padx=5, pady=10)
        
        entry1 = ctk.CTkEntry(input_frame, width=200, placeholder_text=col1_title)
        entry1.pack(side="left", padx=(0, 5))
        
        entry2 = ctk.CTkEntry(input_frame, width=300, placeholder_text=col2_title)
        entry2.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Aktionen
        def add_or_update():
            k = entry1.get().strip()
            v = entry2.get().strip()
            if not k or not v:
                return
            
            if is_list:
                # Macht aus "M 32, M 110" eine saubere Python Liste -> ["M 32", "M 110"]
                v_list = [x.strip() for x in v.split(",") if x.strip()]
                self.data[dict_key][k] = v_list
            else:
                self.data[dict_key][k] = v
                
            entry1.delete(0, "end")
            entry2.delete(0, "end")
            refresh_list()

        def delete_selected():
            selected = tree.selection()
            if not selected: return
            for item in selected:
                k = tree.item(item, "values")[0]
                if k in self.data[dict_key]:
                    del self.data[dict_key][k]
            refresh_list()

        def load_into_entry(event):
            selected = tree.selection()
            if not selected: return
            vals = tree.item(selected[0], "values")
            entry1.delete(0, "end")
            entry1.insert(0, vals[0])
            entry2.delete(0, "end")
            entry2.insert(0, vals[1])

        tree.bind("<Double-1>", load_into_entry)
        
        ctk.CTkButton(input_frame, text="Hinzufügen / Ändern", width=120, fg_color="#2980b9", hover_color="#3498db", command=add_or_update).pack(side="left", padx=5)
        ctk.CTkButton(input_frame, text="🗑 Löschen", width=80, fg_color="#c0392b", hover_color="#e74c3c", command=delete_selected).pack(side="left", padx=5)

    def save_data(self):
        try:
            # Sichert das Dictionary als perfekten JSON-String. Keine Syntax-Fehler möglich!
            with open(self.catalog_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
                
            # Zwingt die App, die Daten sofort live neu in den Cache zu laden
            self.logic.load_catalogs() 
            
            messagebox.showinfo("Gespeichert", "Datenbank erfolgreich aktualisiert!")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", str(e))