import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import customtkinter as ctk
import os
import threading
import csv
import re
from datetime import datetime, timedelta

# Astropy Imports
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
import astropy.units as u

import smart_utils as utils
import smart_metric

class DeepSkyAnalyseFrame(ctk.CTkFrame):
    def __init__(self, parent):
        # Frame initialisieren (ohne Hintergrundfarbe, damit es sich einfügt)
        super().__init__(parent, fg_color="transparent")
        
        # Variablen (ehemals in SmartSuiteApp)
        self.ana_col = ("Datei", "Target", "Gerät", "Filter", "Exp", "Alt", "Gain", "EQM", "RA", "DEC", "Fokus", "Temp", "Datum", "Zeit")
        self.ana_data = []
        self.ana_chart_data = []
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.ana_filt)

        # --- UI AUFBAU ---
        fr = ctk.CTkFrame(self)
        fr.pack(fill="x", padx=20, pady=10)
        
        btn_ana = ctk.CTkButton(fr, text="Ordner analysieren", command=self.ana_br)
        btn_ana.pack(side="left", padx=10)
        
        btn_ex = ctk.CTkButton(fr, text="📥 CSV Export", command=self.ana_ex, fg_color="#27ae60")
        btn_ex.pack(side="left", padx=10)
        
        btn_met = ctk.CTkButton(fr, text="📊 Metrische Analyse", command=self.ana_met, fg_color="#8e44ad")
        btn_met.pack(side="left", padx=10)
        
        self.ana_stat = ctk.CTkLabel(fr, text="Bereit", font=("Arial", 12, "bold"))
        self.ana_stat.pack(side="left", padx=20)
        
        self.ana_s = ctk.CTkEntry(fr, textvariable=self.search_var, placeholder_text="Suchen...", width=300)
        self.ana_s.pack(side="right", padx=(5, 10))
        ctk.CTkLabel(fr, text="🔍", font=("Arial", 16)).pack(side="right", padx=(10, 0))

        self.lbl_m = ctk.CTkLabel(self, text="Bitte Ordner wählen...", font=("Arial", 22, "bold"), anchor="w")
        self.lbl_m.pack(fill="x", padx=20)
        self.lbl_s = ctk.CTkLabel(self, text="", font=("Arial", 12), text_color="gray", anchor="w")
        self.lbl_s.pack(fill="x", padx=20)

        f3 = ctk.CTkFrame(self, border_width=2, border_color="#3b8ed0")
        f3.pack(fill="both", expand=True, padx=20, pady=10)
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2a2a", foreground="white", fieldbackground="#2a2a2a", borderwidth=0)
        style.configure("Treeview.Heading", background="#3b8ed0", foreground="white", font=("Arial", 10, "bold"))
        style.map("Treeview", background=[('selected', '#1f6aa5')])
        
        self.tree = ttk.Treeview(f3, columns=self.ana_col, show="headings")
        sb_y = ttk.Scrollbar(f3, orient="vertical", command=self.tree.yview)
        sb_x = ttk.Scrollbar(f3, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        
        for c in self.ana_col: 
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_tree(_c, False))
            self.tree.column(c, width=90, minwidth=50) 
            
        self.tree.tag_configure('odd', background='#404040')
        self.tree.tag_configure('even', background='#2b2b2b')
        
        sb_y.pack(side="right", fill="y", pady=3, padx=(0,3))
        sb_x.pack(side="bottom", fill="x", padx=3, pady=(0,3))
        self.tree.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        
        self.c_frame = ctk.CTkFrame(self, height=180)
        self.c_frame.pack(fill="x", padx=20, pady=10)
        self.chart = tk.Canvas(self.c_frame, bg="#1a1a1a", height=160, highlightthickness=0)
        self.chart.pack(fill="both", expand=True, padx=20, pady=10)
        
        f5 = ctk.CTkFrame(self, border_width=2, border_color="#3b8ed0")
        f5.pack(fill="x", padx=20, pady=10)
        f5.grid_columnconfigure(0, weight=0); f5.grid_columnconfigure(1, weight=1)
        f5.grid_rowconfigure(0, weight=1)
        
        fg = ctk.CTkFrame(f5, fg_color="transparent")
        fg.grid(row=0, column=0, sticky="nw", padx=15, pady=10)
        self.l_f = ctk.CTkLabel(fg, text="Dateien: 0", font=("Arial", 14, "bold")); self.l_f.pack(anchor="w")
        self.l_t = ctk.CTkLabel(fg, text="Gesamt: 0h 0m", text_color="#3b8ed0"); self.l_t.pack(anchor="w")
        self.l_ir = ctk.CTkLabel(fg, text="Astro/IRCUT: 0m"); self.l_ir.pack(anchor="w")
        self.l_lp = ctk.CTkLabel(fg, text="DUO-BAND/LP: 0m", text_color="#2ecc71"); self.l_lp.pack(anchor="w")
        
        fsess = ctk.CTkFrame(f5, fg_color="transparent")
        fsess.grid(row=0, column=1, sticky="nsew", padx=20, pady=10)
        ctk.CTkLabel(fsess, text="Sessions:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.sess_box = ctk.CTkScrollableFrame(fsess, height=100, fg_color="#222222")
        self.sess_box.pack(fill="both", expand=True)

    # --- FUNKTIONEN ---
    def launch_external_analysis(self, path):
        self.curr_ana = os.path.normpath(path)
        self.lbl_s.configure(text=self.curr_ana)
        self.ana_stat.configure(text="Lade externe Daten...", text_color="#e67e22")
        threading.Thread(target=self.w_ana, args=(self.curr_ana,), daemon=True).start()

    def ana_br(self):
        d = filedialog.askdirectory()
        if d:
            self.curr_ana = os.path.normpath(d)
            self.ana_stat.configure(text="Lade Daten...", text_color="#e67e22")
            threading.Thread(target=self.w_ana, args=(self.curr_ana,), daemon=True).start()

    def w_ana(self, d):
        raw_data = []
        cfg = utils.load_config() 
        try: 
            files = [f for f in os.listdir(d) if f.lower().endswith(('.fit', '.fits'))]
        except Exception as e: 
            utils.log.error(f"Fehler beim Lesen des Analyse-Ordners '{d}': {e}")
            files = []
            
        cn = "Unknown"; obj = "Unknown"
        
        for f in files:
            try:
                with fits.open(os.path.join(d, f)) as h:
                    hdr = h[0].header
                    dt_str = hdr.get('DATE-OBS', '').split('.')[0]
                    try: dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
                    except Exception as e: 
                        dt = datetime.min
                    
                    tmp = hdr.get('CCD-TEMP') or hdr.get('DET-TEMP') or hdr.get('TEMP')
                    ra = hdr.get('RA'); dec = hdr.get('DEC')
                    
                    dev_raw = str(hdr.get('TELESCOP', 'Unknown'))
                    dev_up = dev_raw.upper()
                    
                    # Hier war der Fehler beim Kopieren! 
                    if "S50" in dev_up: dev = "Seestar_S50"
                    elif "S30" in dev_up: dev = "Seestar_S30" 
                    elif "DWARF" in dev_up: dev = "Dwarf_3" if "3" in dev_up else "Dwarf_II"
                    else: dev = dev_raw

                    if cn == "Unknown" and ra and dec:
                        try:
                            sc = SkyCoord(ra=ra*u.deg, dec=dec*u.deg)
                            cn = sc.get_constellation()
                        except Exception: pass
                            
                    if obj == "Unknown": obj = hdr.get('OBJECT', 'Unknown')
                    
                    alt = "N/A"
                    direct_alt = hdr.get('OBJCTALT') or hdr.get('ALT-OBS') or hdr.get('CENTALT')
                    if direct_alt: alt = f"{float(direct_alt):.1f}"
                    elif ra and dec and dt != datetime.min:
                        try:
                            lat = hdr.get('SITELAT') or hdr.get('LAT-OBS')
                            lon = hdr.get('SITELONG') or hdr.get('LONG-OBS')
                            if not lat: lat = cfg.get("default_lat")
                            if not lon: lon = cfg.get("default_lon")
                            if lat and lon:
                                loc = EarthLocation(lat=float(lat)*u.deg, lon=float(lon)*u.deg)
                                coord = SkyCoord(ra=float(ra)*u.deg, dec=float(dec)*u.deg)
                                alt_deg = coord.transform_to(AltAz(obstime=Time(dt), location=loc)).alt.deg
                                alt = f"{alt_deg:.1f}"
                        except Exception: pass
                    
                    row = (
                        f, hdr.get('OBJECT'), dev, hdr.get('FILTER'), 
                        hdr.get('EXPTIME'), alt, hdr.get('GAIN'), hdr.get('EQMODE'), 
                        hdr.get('RA'), hdr.get('DEC'), hdr.get('FOCUSPOS'), tmp, 
                        dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S')
                    )
                    raw_data.append({"val": row, "dt": dt, "fil": str(hdr.get('FILTER')).upper(), "exp": float(hdr.get('EXPTIME') or 0), "tmp": tmp})
            except Exception as e: pass
                
        raw_data.sort(key=lambda x: x["dt"])
        if self.winfo_exists():
            self.after(0, lambda: self.finish_ana(raw_data, obj, cn))

    def finish_ana(self, raw_data, obj, cn):
        if not self.winfo_exists(): return
        self.ana_data = [x["val"] for x in raw_data]
        self.ana_chart_data = [(x["dt"].strftime('%H:%M'), x["tmp"]) for x in raw_data if x["tmp"] is not None]
        self.ana_filt()
        
        t_sec = sum(x["exp"] for x in raw_data)
        nb_keys = ["LP", "DUO", "DB", "NB", "OIII", "HA", "SII", "H-ALPHA", "UHC"]
        lp_sec = sum(x["exp"] for x in raw_data if any(k in x["fil"] for k in nb_keys))
        ir_sec = t_sec - lp_sec

        self.ana_stat.configure(text=f"{len(raw_data)} Dateien geladen", text_color="#2ecc71")
        self.l_f.configure(text=f"Dateien: {len(raw_data)}"); self.l_t.configure(text=f"Gesamt: {int(t_sec//3600)}h {int((t_sec%3600)//60)}m")
        self.l_ir.configure(text=f"Astro/IRCUT: {int(ir_sec//60)}m"); self.l_lp.configure(text=f"DUO-BAND/LP: {int(lp_sec//60)}m")
        self.lbl_m.configure(text=f"Objekt {obj} im Sternbild {cn}"); self.lbl_s.configure(text=self.curr_ana)
        self.draw_chart(); self.build_sessions(raw_data)

    def ana_filt(self, *args):
        try: s = self.ana_s.get().lower()
        except: s = self.search_var.get().lower()
        self.tree.delete(*self.tree.get_children())
        display_idx = 0
        for row in self.ana_data:
            match = False
            for item in row:
                if item and s in str(item).lower():
                    match = True
                    break
            if match:
                tag = 'odd' if display_idx % 2 else 'even'
                self.tree.insert("", "end", values=row, tags=(tag,))
                display_idx += 1

    def ana_ex(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv")
        if f:
            try:
                with open(f, 'w', newline='') as c:
                    w = csv.writer(c, delimiter=';'); w.writerow(self.ana_col)
                    for i in self.tree.get_children(): w.writerow(self.tree.item(i)['values'])
            except Exception as e: 
                messagebox.showerror("Fehler", f"Konnte CSV nicht speichern:\n{e}")
                
    def ana_met(self):
        if hasattr(self, 'curr_ana'): smart_metric.MetricAnalysisWindow(self, self.curr_ana)
        
    def sort_tree(self, col, rev):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try: l.sort(key=lambda t: float(re.sub(r'[^\d.]', '', str(t[0]))), reverse=rev)
        except Exception: l.sort(reverse=rev)
        for i, (v, k) in enumerate(l): self.tree.move(k, '', i); self.tree.item(k, tags=('odd' if i % 2 else 'even',))
        self.tree.heading(col, command=lambda: self.sort_tree(col, not rev))

    def draw_chart(self):
        self.chart.delete("all")
        if len(self.ana_chart_data) < 2: return
        w, h = self.chart.winfo_width(), self.chart.winfo_height()
        temps = [d[1] for d in self.ana_chart_data]; min_t, max_t = min(temps), max(temps)
        if min_t == max_t: min_t -= 1; max_t += 1
        px, py = 80, 40; pw, ph = w - 2*px, h - 2*py
        
        for j in range(5): 
            y = h - py - (j / 4) * ph
            self.chart.create_line(px, y, w - px, y, fill="#333333", dash=(2, 4))
            
        pts = []
        for i, t in enumerate(temps):
            x = px + (i/(len(temps)-1))*pw; y = h - py - ((t-min_t)/(max_t-min_t))*ph; pts.extend([x, y])
            if i % max(1, len(temps)//10) == 0: self.chart.create_text(x, h-py+15, text=self.ana_chart_data[i][0], fill="gray", font=("Arial", 8))
            
        self.chart.create_line(pts, fill="#3b8ed0", width=2, smooth=True)
        self.chart.create_text(px-10, py, text=f"{max_t:.1f}°C", fill="gray", anchor="e")
        self.chart.create_text(px-10, h-py, text=f"{min_t:.1f}°C", fill="gray", anchor="e")

    def build_sessions(self, data):
        for w in self.sess_box.winfo_children(): w.destroy()
        if not data: return
        try: gap_mins = int(utils.load_config().get("session_gap", 5))
        except ValueError: gap_mins = 5

        sessions = []; cur = None
        for item in data:
            if cur is None or (item["dt"] - cur['end'] > timedelta(minutes=gap_mins)) or (item["fil"] != cur['fil']):
                if cur: sessions.append(cur)
                cur = {'id': len(sessions)+1, 'start': item["dt"], 'end': item["dt"], 'cnt': 0, 'obj': item["val"][1], 'fil': item["fil"]}
            cur['cnt'] += 1; cur['end'] = item["dt"]
            
        if cur: sessions.append(cur)
        for s in sessions:
            c = ctk.CTkFrame(self.sess_box, fg_color="#333333"); c.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(c, text=f"#{s['id']} | {s['start'].strftime('%Y-%m-%d %H:%M')} | {s['obj']} ({s['fil']}) - {s['cnt']} Bilder", font=("Consolas", 11)).pack(side=tk.LEFT, padx=10)