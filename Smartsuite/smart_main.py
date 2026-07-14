# ==============================================================================
# SMART_MAIN.PY - Programmstart & Splash Screen
# ==============================================================================
import sys
import os
import traceback
import tkinter as tk

# 1. Sofort eine Log-Datei öffnen, noch bevor irgendetwas passiert
log_file = open("CRASH_LOG.txt", "w")
log_file.write("Programm gestartet...\n")
log_file.flush()

def resource_path(relative_path):
    """ Ermittelt den absoluten Pfad zu Ressourcen (für Dev und PyInstaller) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    # Lade die Version ganz am Anfang (das geht extrem schnell, da es keine Abhängigkeiten hat)
    import version
    app_version = version.CURRENT_VERSION
except:
    app_version = "1.x"

# ==============================================================================
# SPLASH SCREEN AUFBAU (Pures Tkinter, lädt in Millisekunden)
# ==============================================================================
splash = tk.Tk()
splash.overrideredirect(True) # Entfernt den Windows-Rahmen (Titelzeile)

# Fenstergröße und Zentrierung
width = 500
height = 360
screen_width = splash.winfo_screenwidth()
screen_height = splash.winfo_screenheight()
x = (screen_width / 2) - (width / 2)
y = (screen_height / 2) - (height / 2)
splash.geometry(f'{int(width)}x{int(height)}+{int(x)}+{int(y)}')

# Dunkler, moderner Hintergrund (ähnlich Seti Astro Suite)
bg_color = "#0f141e"
splash.configure(bg=bg_color)

# 1. LOGO LADEN
try:
    # PIL laden geht schnell genug für den Splash Screen
    from PIL import Image, ImageTk
    img_path = resource_path("smartsuite.png")
    if not os.path.exists(img_path):
        img_path = resource_path("smartsuite.ico")
        
    if os.path.exists(img_path):
        img = Image.open(img_path)
        img = img.resize((140, 140), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        lbl_img = tk.Label(splash, image=photo, bg=bg_color)
        lbl_img.image = photo # Referenz behalten!
        lbl_img.pack(pady=(35, 10))
    else:
        raise Exception("Kein Bild gefunden")
except Exception as e:
    log_file.write(f"Splash Logo konnte nicht geladen werden: {e}\n")
    lbl_img = tk.Label(splash, text="🔭", font=("Arial", 60), bg=bg_color, fg="white")
    lbl_img.pack(pady=(30, 10))

# 2. TITEL & VERSION
tk.Label(splash, text="SmartSuite", font=("Segoe UI", 26, "bold"), bg=bg_color, fg="white").pack(pady=(0, 0))
tk.Label(splash, text=f"Version {app_version}", font=("Segoe UI", 12), bg=bg_color, fg="#888888").pack(pady=(0, 20))

# 3. PROGRESS BAR (Animiert über Canvas)
canvas = tk.Canvas(splash, width=400, height=4, bg="#1a2233", highlightthickness=0)
canvas.pack(pady=(10, 5))
progress_rect = canvas.create_rectangle(0, 0, 0, 4, fill="#3498db", outline="")

# 4. STATUS TEXT
lbl_status = tk.Label(splash, text="Initialisiere System...", font=("Segoe UI", 9), bg=bg_color, fg="#aaaaaa")
lbl_status.pack(anchor="w", padx=50)

# 5. COPYRIGHT (Ganz unten)
tk.Label(splash, text="© 2025-2026 Stefan Raphael • All Rights Reserved", font=("Segoe UI", 8), bg=bg_color, fg="#555555").pack(side="bottom", pady=15)

# Fenster auf den Bildschirm zwingen
splash.update()

# ==============================================================================
# HEAVY IMPORTS (Während der Splash Screen angezeigt wird)
# ==============================================================================
try:
    # Schritt 1: Module laden (Hier passiert 90% der Ladezeit wegen Astropy/Pandas)
    canvas.coords(progress_rect, 0, 0, 60, 4) # 15% Balken
    lbl_status.config(text="Triebwerke starten... Lade Astrometrie & Skyfield Module")
    splash.update()
    
    log_file.write("Lade Modul: smart_gui...\n"); log_file.flush()
    import smart_gui # <--- HIER lädt Python jetzt im Hintergrund die schweren Geschütze
    
    # Schritt 2: GUI instanziieren
    canvas.coords(progress_rect, 0, 0, 320, 4) # 80% Balken
    lbl_status.config(text="Baue Benutzeroberfläche auf...")
    splash.update()
    
    log_file.write("Alle Module geladen! Starte GUI...\n"); log_file.flush()
    
    if __name__ == "__main__":
        start_mode = None
        start_path = None
        if len(sys.argv) > 2 and sys.argv[1] == "--analyze":
            start_mode = "analyze"
            start_path = sys.argv[2]

        app = smart_gui.SmartSuiteApp(version_string=app_version, start_mode=start_mode, start_path=start_path)
        
        # Schritt 3: Fertig!
        canvas.coords(progress_rect, 0, 0, 400, 4) # 100% Balken
        lbl_status.config(text="Ready for take off!")
        splash.update()
        
        # Splash Screen schließen und Hauptprogramm übergeben
        splash.destroy()
        app.mainloop()

except Exception as e:
    # 2. Wenn etwas abstürzt, fangen wir den Fehler ab und schreiben ins Log
    log_file.write("\n!!! KRITISCHER FEHLER AUFGETRETEN !!!\n")
    log_file.write(traceback.format_exc())
    # Damit das Fenster nicht ewig hängen bleibt, wenn ein Fehler auftritt:
    try: splash.destroy() 
    except: pass
finally:
    log_file.close()