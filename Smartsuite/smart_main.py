# ==============================================================================
# SMART_MAIN.PY - Startpunkt
# ==============================================================================
import smart_gui
import sys
import version # Lade die Version zentral

if __name__ == "__main__":
    start_mode = None
    start_path = None
    
    # Prüfen, ob Argumente übergeben wurden (z.B. von AstroArchive)
    if len(sys.argv) > 2:
        if sys.argv[1] == "--analyze":
            start_mode = "analyze"
            start_path = sys.argv[2]

    # Übergebe die Version an die GUI
    app = smart_gui.SmartSuiteApp(version_string=version.CURRENT_VERSION, start_mode=start_mode, start_path=start_path)
    app.mainloop()