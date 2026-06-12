import requests
import json
import time
import logging

class AstrometryClient:
    BASE_URL = "http://nova.astrometry.net/api"
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.session_key = None
        self.headers = {'Referer': 'https://nova.astrometry.net/api/login'}

    def login(self):
        """Loggt sich bei Astrometry.net ein und holt den Session-Key."""
        if not self.api_key:
            return False, "Kein API Key vorhanden."
        try:
            payload = {'request-json': json.dumps({"apikey": self.api_key})}
            resp = requests.post(f"{self.BASE_URL}/login", data=payload, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    self.session_key = data.get("session")
                    return True, "Login erfolgreich."
                return False, f"Login fehlgeschlagen: {data.get('message')}"
            return False, f"Server Fehler (Login): {resp.status_code}"
        except Exception as e:
            return False, f"Verbindungsfehler: {e}"

    def upload_file(self, file_path):
        """Lädt das Bild hoch und gibt die Submission ID zurück."""
        if not self.session_key:
            return None, "Nicht eingeloggt."
        try:
            with open(file_path, 'rb') as f:
                args = {
                    "session": self.session_key,
                    "allow_commercial_use": "n",
                    "allow_modifications": "n",
                    "publicly_visible": "n" 
                }
                resp = requests.post(
                    f"{self.BASE_URL}/upload", 
                    data={'request-json': json.dumps(args)}, 
                    files={'file': f}, 
                    headers=self.headers
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data.get("subid"), "Upload erfolgreich."
                    return None, f"Upload Fehler: {data.get('errormessage')}"
                return None, f"HTTP Fehler beim Upload: {resp.status_code}"
        except Exception as e:
            return None, f"Datei-Fehler: {e}"

    def wait_for_job(self, sub_id, timeout=120):
        """
        Wartet, bis aus der Submission ein Job wird.
        Robust gegen Race-Conditions (Submission fertig, aber Job-Liste noch [null]).
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(f"{self.BASE_URL}/submissions/{sub_id}", headers=self.headers)
                data = resp.json()
                
                # Wir prüfen, ob eine Job-Liste existiert UND ob das erste Element kein None ist
                if data.get("jobs") and len(data["jobs"]) > 0:
                    job_id = data["jobs"][0]
                    if job_id: # Hier stellen wir sicher, dass es nicht [null] ist
                        return job_id
                
                # WICHTIG: Wir brechen hier NICHT mehr ab, nur weil processing_finished True ist.
                # Wir vertrauen darauf, dass der Timeout greift, falls wirklich nichts kommt.
                # Das behebt den "Sofort-Absturz", wenn die API kurz [null] sendet.
                    
            except Exception as e:
                logging.warning(f"Fehler beim Pollen des Jobs (Sub {sub_id}): {e}")
                
            time.sleep(5) 
            
        return None

    def wait_for_calibration(self, job_id, timeout=120):
        """
        Wartet, bis der Job fertig (success) ist.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(f"{self.BASE_URL}/jobs/{job_id}", headers=self.headers)
                data = resp.json()
                status = data.get("status")
                if status == "success": return True
                if status == "failure": return False
            except Exception as e:
                logging.warning(f"Fehler beim Pollen des Status (Job {job_id}): {e}")
                
            time.sleep(5) 
        return False

    def get_results(self, job_id):
        """Holt RA, DEC und annotierte Objekte."""
        try:
            cal_resp = requests.get(f"{self.BASE_URL}/jobs/{job_id}/calibration", headers=self.headers)
            cal_data = cal_resp.json()
            
            ann_resp = requests.get(f"{self.BASE_URL}/jobs/{job_id}/annotations", headers=self.headers)
            ann_data = ann_resp.json()
            
            ra = cal_data.get("ra")
            dec = cal_data.get("dec")
            
            objects = ann_data.get("annotations", [])
            names = []
            for obj in objects:
                if obj.get("names"): names.append(obj["names"][0])
            
            return {
                "ra": ra, 
                "dec": dec, 
                "names": list(set(names)),
                "job_id": job_id
            }
        except Exception as e:
            logging.error(f"Ergebnis-Abruf Fehler für Job {job_id}: {e}")
            return None