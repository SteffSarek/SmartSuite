# ==============================================================================
# SMART_MAIN.PY - Startpunkt (V3.0.0: SmartScore & Python Scripts)
# ==============================================================================
import smart_gui
import sys

# Version 3.0.0 Release
CURRENT_VERSION = "3.0"

if __name__ == "__main__":
    start_mode = None
    start_path = None
    
    # Prüfen, ob Argumente übergeben wurden (z.B. von AstroArchive)
    if len(sys.argv) > 2:
        if sys.argv[1] == "--analyze":
            start_mode = "analyze"
            start_path = sys.argv[2]

    app = smart_gui.SmartSuiteApp(version_string=CURRENT_VERSION, start_mode=start_mode, start_path=start_path)
    app.mainloop()