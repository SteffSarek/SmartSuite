import logging
import ctypes  # <--- NEU: Für den DPI-Fix notwendig
from logging.handlers import RotatingFileHandler # <--- NEU: Import für rotierende Logs

try:
    # Versuche, Windows 8.1+ DPI Awareness zu setzen (Per Monitor DPI aware)
    ctypes.windll.shcore.SetProcessDpiAwareness(1) 
except Exception:
    try:
        # Fallback für älteres Windows (System DPI aware)
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from gui import AstroApp
from logic import AstroLogic

# --- LOGGING KONFIGURATION (Verbessert) ---
# Wir nutzen einen RotatingFileHandler, damit die Datei nicht explodiert.
# maxBytes=1_000_000  -> Maximal 1 MB pro Datei
# backupCount=3       -> Behalte die letzten 3 vollen Dateien (plus die aktuelle)

log_handler = RotatingFileHandler(
    "astro_log.txt", 
    maxBytes=1_000_000, 
    backupCount=3, 
    encoding="utf-8"
)

logging.basicConfig(
    handlers=[log_handler], # Hier nutzen wir den smarten Handler
    level=logging.INFO,     # INFO loggt Erfolge (z.B. Solves), ERROR loggt Fehler
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# ---------------------------------------

if __name__ == "__main__":
    try:
        # 1. Logik-Controller initialisieren
        logic = AstroLogic()
        
        # 2. GUI starten
        app = AstroApp(logic)
        
        # 3. Hauptschleife
        app.mainloop()
        
    except Exception as e:
        # Fängt Abstürze ab, die nicht in der GUI behandelt wurden
        logging.critical(f"Kritischer Fehler im Hauptprogramm: {e}", exc_info=True)
        raise e  # Trotzdem abstürzen lassen, damit man es in der Konsole sieht