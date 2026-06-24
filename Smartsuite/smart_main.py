import sys
import traceback

# 1. Sofort eine Log-Datei öffnen, noch bevor irgendetwas passiert
log_file = open("CRASH_LOG.txt", "w")
log_file.write("Programm gestartet...\n")
log_file.flush()

try:
    log_file.write("Lade Modul: version...\n"); log_file.flush()
    import version
    
    log_file.write("Lade Modul: smart_gui...\n"); log_file.flush()
    import smart_gui
    
    log_file.write("Alle Module erfolgreich geladen! Starte GUI...\n"); log_file.flush()
    
    if __name__ == "__main__":
        start_mode = None
        start_path = None
        if len(sys.argv) > 2 and sys.argv[1] == "--analyze":
            start_mode = "analyze"
            start_path = sys.argv[2]

        app = smart_gui.SmartSuiteApp(version_string=version.CURRENT_VERSION, start_mode=start_mode, start_path=start_path)
        app.mainloop()

except Exception as e:
    # 2. Wenn etwas abstürzt, fangen wir den Fehler GANZ OBEN ab!
    log_file.write("\n!!! KRITISCHER FEHLER AUFGETRETEN !!!\n")
    log_file.write(traceback.format_exc())
finally:
    log_file.close()