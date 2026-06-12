🔭 SmartSuite
Der All-in-One Werkzeugkasten für Astrofotografen mit Smart-Teleskopen.
Die SmartSuite ist eine mächtige Python-Desktopanwendung, die den gesamten Workflow vor und nach der eigentlichen Bildaufnahme abdeckt. Egal ob du deine Rohdaten (FITS) vom ZWO Seestar (S50/S30) oder Dwarf (II/3) importieren, schlechte Bilder per KI-gestütztem "Smart Score" aussortieren oder das nächste seltene Himmelsereignis planen möchtest – die SmartSuite bündelt alle nötigen Tools unter einer modernen, dunklen Benutzeroberfläche.
![alt text](https://via.placeholder.com/800x450.png?text=Hier+ein+Screenshot+der+SmartSuite+einfuegen)

(Tipp: Füge hier später einen Screenshot des Programms ein – z.B. von der Metrik-Analyse!)
✨ Hauptfunktionen
📥 Smart Import & Archivierung: Liest Rohdaten direkt vom Teleskop oder USB-Stick, erkennt das Ziel anhand der FITS-Header und sortiert sie automatisch in eine saubere Projektstruktur. Unterstützt Mosaik-Routing und N.I.N.A.-Header Fixes.
📊 Deep Sky Metrik-Analyse: Scannt hunderte FITS-Bilder in Sekunden. Berechnet FWHM, Exzentrizität, SNR, Hintergrundrauschen und Sternenanzahl. Ein berechneter "Smart Score" hilft dir, Ausreißer (z.B. durch Wind oder Wolken) vollautomatisch auszusortieren.
🚀 Nahtlose Siril Integration: Führe Siril-Skripte (.ssf) oder Python-Skripte direkt aus der App heraus im Hintergrund aus oder öffne die Siril-GUI direkt im passenden Arbeitsverzeichnis.
☄️ Integrierter Astrotracker: Bezieht Live-Daten aus dem Internet für Kometen (Yoshida/MPC), Kleinplaneten (NEA/PHA) und frische Supernovae (Rochester). Berechnet mithilfe von Skyfield sekundengenau die optimale Beobachtungszeit und Horizonthöhe für deinen Standort.
📅 Astro-Kalender: Berechnet für deine GPS-Koordinaten lokale Himmelsereignisse (ISS-Transite vor Sonne/Mond, Planetenparaden, Finsternisse und Meteorschauer).
📥 Installation & Download
Für Anwender (Fertige App)
Du möchtest nicht programmieren, sondern sofort loslegen?
Gehe auf dieser Seite rechts auf [Releases].
Lade dir die neueste SmartSuite_vX.X.zip herunter.
Entpacke die ZIP-Datei an einen beliebigen Ort.
Starte die SmartSuite.exe.
Für Entwickler (Python Quellcode)
Wenn du den Code ausführen, untersuchen oder erweitern möchtest:
Klone dieses Repository:
code
Bash
git clone https://github.com/DEIN_GITHUB_NAME/SmartSuite.git
Installiere die benötigten Python-Bibliotheken. (Tipp: Nutze ein Virtual Environment!):
code
Bash
pip install customtkinter pillow astropy pandas numpy matplotlib requests beautifulsoup4 ephem skyfield sep
Starte das Programm:
code
Bash
python smart_main.py
⚙️ Externe Abhängigkeiten (Optional)
Um alle Module der SmartSuite (insbesondere die Bildanalyse und das Plate Solving) zu nutzen, müssen folgende kostenlose Programme auf deinem System installiert und in den SmartSuite-Einstellungen verknüpft sein:
Siril: Wird für Stacking-Skripte und die GUI-Integration benötigt.
ASTAP: Für das lokale Plate Solving von Bildern im Astrotracker (Sternendatenbank nicht vergessen!).
Aladin Desktop: Um gelöste Bilder visuell zu prüfen (z.B. zur Supernova-Identifikation).
📝 Lizenz & Credits
Dieses Projekt steht unter der GNU General Public License v3.0.
Entwickelt von Stefan Raphael (2025-2026).
Himmelsmechanik und Ephemeriden werden berechnet mit Skyfield und PyEphem. Metrische Bildanalyse nutzt SEP (Source Extractor).