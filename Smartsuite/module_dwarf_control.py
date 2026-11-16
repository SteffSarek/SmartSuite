# ==============================================================================
# MODULE_DWARF_CONTROL.PY - Direkte WebSocket Steuerung für Dwarflab Teleskope
# ==============================================================================
import sys
import os
import time
import threading
import requests
import smart_utils as utils

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

DWARF_IMPORT_ERROR = ""

try:
    from dwarf_python_api.lib.dwarf_config import DwarfConfig
    from dwarf_python_api.lib.dwarf_session import DwarfManager
    from dwarf_python_api.lib.dwarf_session_socket import disconnect_socket, get_client_status
    from dwarf_python_api.lib.dwarf_utils import (
        set_HostMaster, perform_time, perform_timezone, perform_set_location,
        perform_enter_astro_mode, perform_goto, perform_stop_goto,
        perform_set_astro_exposure_by_name_v3, perform_set_astro_gain_v3, perform_set_ir_filter_v3,
        perform_set_astro_stack_count_v3, perform_continue_shooting, perform_clear_needs_continue_shooting,
        perform_takeAstroPhoto, perform_stopAstroPhoto,
        perform_start_autofocus, perform_calibration, start_polar_align,
        perform_reboot, perform_powerOpenRGB, perform_powerCloseRGB
    )
    DWARF_API_AVAILABLE = True
except Exception as e:
    import traceback
    utils.log.error(f"Dwarf API Import Fehler:\n{traceback.format_exc()}")
    DWARF_IMPORT_ERROR = str(e)
    DWARF_API_AVAILABLE = False

class DwarfController:
    def __init__(self):
        self.manager = None
        self.session = None
        self.light_state = False 
        if DWARF_API_AVAILABLE:
            self.manager = DwarfManager()

    def setup_session(self, ip_address):
        if not DWARF_API_AVAILABLE: return False
        
        # --- NEU: ZOMBIE-FÄNGER ---
        # Falls intern noch eine alte Verbindung hängt, wird sie gnadenlos gekappt,
        # bevor wir eine neue anfordern! Das verhindert den "DEVICE_OCCUPIED" Fehler.
        if self.session:
            try: self.disconnect()
            except: pass
            time.sleep(0.5)
            if self.session.dwarf_uid:
                try: self.manager.remove(self.session.dwarf_uid)
                except: pass
        # ---------------------------

        real_uid = "SmartSuite_Dwarf"
        try:
            r = requests.post(f"http://{ip_address}:8082/deviceInfo", timeout=2)
            if r.status_code == 200:
                data = r.json().get("data", {})
                real_uid = data.get("deviceName", "SmartSuite_Dwarf")
        except: pass
            
        cfg = utils.load_config()
        lat = float(cfg.get("default_lat", 51.16))
        lon = float(cfg.get("default_lon", 10.45))

        config = DwarfConfig(
            dwarf_uid=real_uid, dwarf_ip=ip_address, 
            client_id="0000DAF2-0000-1000-8000-00805F9B34FB",
            latitude=lat, longitude=lon, timezone="Europe/Berlin"
        )
        self.session = self.manager.add(config, make_default=True)
        self.light_state = False
        return True

    def get_status(self):
        if not self.session: return None
        try:
            status = get_client_status(self.session)
            if isinstance(status, dict) and "fullStatus" in status:
                return status["fullStatus"]
        except: pass
        return None

    def connect_and_init(self, callback):
        if not self.session: return
        def worker():
            try:
                # Nur Basis-Verbindung prüfen
                if set_HostMaster(session=self.session):
                    if callback: callback(True, "Verbunden")
                else:
                    if callback: callback(False, "Abgelehnt (App noch verbunden?)")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def disconnect(self):
        if self.session:
            try: disconnect_socket(self.session)
            except: pass

    # =========================================================================
    # AKTIONEN - AB HIER WIEDER MIT ABSOLUTER ROBUSTHEIT VOR JEDEM BEFEHL!
    # =========================================================================
    def goto_target(self, ra_deg, dec_deg, target_name, callback=None):
        if not self.session: return
        def worker():
            try:
                ra_hours = ra_deg / 15.0
                # Panzer-Logik:
                if not set_HostMaster(session=self.session):
                    if callback: callback(False, "Keine Master-Rechte.")
                    return
                perform_time(session=self.session)
                perform_timezone(session=self.session)
                perform_set_location(session=self.session)
                perform_enter_astro_mode(session=self.session)
                
                success = perform_goto(ra=ra_hours, dec=dec_deg, target=target_name, session=self.session)
                if callback: callback(success, "GoTo erfolgreich gestartet!" if success else "Abgelehnt (Teleskop nicht kalibriert oder unter Horizont!).")
            except Exception as e:
                if callback: callback(False, f"Fehler: {str(e)}")
        threading.Thread(target=worker, daemon=True).start()

    def stop_goto(self, callback=None):
        if not self.session: return
        def worker():
            try:
                success = perform_stop_goto(session=self.session)
                if callback: callback(success, "GoTo gestoppt!" if success else "Fehler beim Stoppen.")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def start_capture(self, exposure_str, gain_int, ir_index, callback=None):
        if not self.session: return
        def worker():
            try:
                # Panzer-Logik:
                if not set_HostMaster(session=self.session): return
                perform_enter_astro_mode(session=self.session)
                
                perform_set_astro_exposure_by_name_v3(name=exposure_str, dwarf_id="3", session=self.session)
                perform_set_astro_gain_v3(value=gain_int, session=self.session)
                perform_set_ir_filter_v3(name_or_index=ir_index, session=self.session)
                perform_set_astro_stack_count_v3(9999, session=self.session)
                
                time.sleep(1.0) # Filterrad drehen lassen
                
                success = perform_takeAstroPhoto(ir_index=ir_index, session=self.session)
                if callback: callback(success, "Aufnahme läuft!" if success else "Aufnahme fehlgeschlagen.")
            except Exception as e:
                if callback: callback(False, f"Fehler: {str(e)}")
        threading.Thread(target=worker, daemon=True).start()

    def stop_capture(self, callback=None):
        if not self.session: return
        def worker():
            try:
                success = perform_stopAstroPhoto(session=self.session)
                if callback: callback(success, "Aufnahme gestoppt!" if success else "Konnte nicht stoppen.")
            except Exception as e:
                if callback: callback(False, f"Fehler: {str(e)}")
        threading.Thread(target=worker, daemon=True).start()

    def confirm_continue(self):
        if not self.session: return
        def worker():
            try:
                perform_continue_shooting(session=self.session)
                perform_clear_needs_continue_shooting(session=self.session)
            except: pass
        threading.Thread(target=worker, daemon=True).start()

    def focus_infinite(self, callback=None):
        if not self.session: return
        def worker():
            try:
                # Panzer-Logik:
                if not set_HostMaster(session=self.session): return
                perform_enter_astro_mode(session=self.session)
                
                success = perform_start_autofocus(True, session=self.session)
                if callback: callback(success, "Autofokus gestartet!" if success else "Fehler beim Fokussieren.")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def calibrate(self, callback=None):
        if not self.session: return
        def worker():
            try:
                # Panzer-Logik:
                if not set_HostMaster(session=self.session):
                    if callback: callback(False, "Keine Master-Rechte.")
                    return
                perform_time(session=self.session)
                perform_set_location(session=self.session)
                perform_enter_astro_mode(session=self.session)
                
                perform_set_astro_exposure_by_name_v3("1", dwarf_id="3", session=self.session)
                perform_set_astro_gain_v3(80, session=self.session)
                perform_set_ir_filter_v3(1, session=self.session) 
                time.sleep(1.0)
                
                success = perform_calibration(session=self.session)
                if callback: callback(success, "Kalibrierung gestartet!" if success else "Fehler (Wolken?).")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def eq_solving(self, callback=None):
        if not self.session: return
        def worker():
            try:
                if not set_HostMaster(session=self.session): return
                perform_enter_astro_mode(session=self.session)
                
                res = start_polar_align(session=self.session)
                if res is not False: 
                    if callback: callback(True, "EQ Solving gestartet!")
                else:
                    if callback: callback(False, "EQ Solving fehlgeschlagen.")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def toggle_lights(self, callback=None):
        if not self.session: return
        def worker():
            try:
                if self.light_state:
                    success = perform_powerCloseRGB(session=self.session)
                else:
                    success = perform_powerOpenRGB(session=self.session)
                if success: self.light_state = not self.light_state
                if callback: callback(success, "Licht geschaltet." if success else "Fehler beim Licht.")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def reboot(self, callback=None):
        if not self.session: return
        def worker():
            try:
                success = perform_reboot(session=self.session)
                if callback: callback(success, "Neustart eingeleitet!" if success else "Fehler beim Neustart.")
            except Exception as e:
                if callback: callback(False, str(e))
        threading.Thread(target=worker, daemon=True).start()

dwarf_ctrl = DwarfController()