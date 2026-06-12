import customtkinter as ctk
import tkinter as tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import warnings
import re  # <--- NEU: Für den Fix notwendig
from datetime import datetime
from logic_map import MapLogic

# --- Wir nutzen deine Konstanten ---
from constants import COLOR_GALAXY, COLOR_NEBULA, COLOR_CLUSTER, COLOR_COMET, COLOR_OTHER, OBJ_TYPE_COLORS
# -----------------------------------

# Warnungen unterdrücken
warnings.filterwarnings("ignore", message="invalid value encountered in arcsin")
warnings.filterwarnings("ignore", category=RuntimeWarning)

class SkyMapWindow(ctk.CTkToplevel):
    def __init__(self, parent, main_logic, on_click_callback):
        super().__init__(parent)
        self.title("AstroArchive SkyMap")
        self.geometry("1200x800") 
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        
        try:
            self.after(300, self.focus_force)
        except Exception:
            pass
        
        self.main_logic = main_logic
        self.map_logic = MapLogic(main_logic)
        self.on_click_callback = on_click_callback
        
        # --- UI AUFBAU ---
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.top_bar, text="Himmelskarte", font=("Arial", 20, "bold")).pack(side="left")
        
        # LEGENDE
        self.legend_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.legend_frame.pack(side="left", padx=20)
        
        def add_legend_item(parent, color, text):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(side="left", padx=5)
            lbl = ctk.CTkLabel(f, text="● " + text, text_color=color, font=("Arial", 12, "bold"))
            lbl.pack(side="left")

        add_legend_item(self.legend_frame, COLOR_GALAXY, "Galaxie")
        add_legend_item(self.legend_frame, COLOR_NEBULA, "Nebel")
        add_legend_item(self.legend_frame, COLOR_CLUSTER, "Sternhaufen")
        add_legend_item(self.legend_frame, COLOR_COMET, "Komet")
        add_legend_item(self.legend_frame, COLOR_OTHER, "Sonstiges")

        # --- FILTER BEREICH ---
        self.filter_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.filter_frame.pack(side="right")

        # 1. Sternbild Dropdown
        const_list = ["Alle"] + self.main_logic.get_available_constellations()
        self.filter_var = ctk.StringVar(value="Alle")
        self.combo_filter = ctk.CTkOptionMenu(
            self.filter_frame, values=const_list, variable=self.filter_var, width=180,
            command=self.refresh_map_event 
        )
        self.combo_filter.pack(side="left", padx=(0, 10))
        
        # 2. Datums Filter
        ctk.CTkLabel(self.filter_frame, text="Datum:", font=("Arial", 12)).pack(side="left", padx=5)
        self.entry_start = ctk.CTkEntry(self.filter_frame, width=90, placeholder_text="01.01.2025")
        self.entry_start.pack(side="left", padx=2)
        ctk.CTkLabel(self.filter_frame, text="-").pack(side="left")
        self.entry_end = ctk.CTkEntry(self.filter_frame, width=90, placeholder_text="31.12.2026")
        self.entry_end.pack(side="left", padx=2)
        
        self.btn_filter = ctk.CTkButton(self.filter_frame, text="Filter", width=50, command=self.trigger_refresh)
        self.btn_filter.pack(side="left", padx=10)

        # --- LADE-INDIKATOR ---
        self.lbl_loading = ctk.CTkLabel(self, text="Berechne Karte...", 
                                      fg_color="#3498db", text_color="white", 
                                      corner_radius=10, width=200, height=40,
                                      font=("Arial", 16, "bold"))
        
        # --- PLOT BEREICH ---
        plt.style.use('dark_background')
        
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.fig.patch.set_facecolor('#2b2b2b') 
        
        self.ax = self.fig.add_subplot(111, projection="mollweide")
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.canvas.mpl_connect("pick_event", self.on_pick)
        
        self.annot = None
        self.scat = None
        self.names = []
        self.full_ids = []

        self.after(200, self.trigger_refresh)

    def on_close(self):
        if self.fig:
            plt.close(self.fig)
        self.destroy()

    def refresh_map_event(self, selection):
        self.trigger_refresh()

    def trigger_refresh(self):
        self.lbl_loading.place(relx=0.5, rely=0.5, anchor="center")
        self.lbl_loading.lift()
        self.update() 
        self.after(10, self.perform_filtering)

    def perform_filtering(self):
        try:
            d_start = self.entry_start.get().strip()
            d_end = self.entry_end.get().strip()
            if not d_start: d_start = None
            if not d_end: d_end = None
            
            raw_data = self.main_logic.get_map_objects_filtered(d_start, d_end)
            
            full_db_index = getattr(self.main_logic, 'index', {})
            enriched_data = []
            for item in raw_data:
                new_item = item.copy()
                c_val = ""
                fid = new_item.get("full_id")
                if fid and fid in full_db_index:
                    obj_data = full_db_index[fid]
                    c_val = obj_data.get("parent", "")
                new_item["constellation"] = c_val
                enriched_data.append(new_item)

            selection = self.filter_var.get()
            final_data = []

            if selection == "Alle":
                final_data = enriched_data
            else:
                filter_key = selection 
                for k, v in self.main_logic.constellation_names.items():
                    if v == selection: 
                        filter_key = k
                        break
                
                f_key_str = str(filter_key).strip().lower()
                for item in enriched_data:
                    c_val = str(item.get("constellation", "")).strip().lower()
                    if f_key_str == c_val:
                        final_data.append(item)
            
            self.plot_objects(final_data, selection)
            
        except Exception as e:
            print(f"ERROR in Map: {e}")
        finally:
            self.lbl_loading.place_forget()

    def plot_objects(self, data_list, selection_title="Alle"):
        self.ax.clear()
        
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(10,10), textcoords="offset points",
                            bbox=dict(boxstyle="round", fc="#f1c40f", ec="black", alpha=0.9),
                            color="black", weight='bold',
                            arrowprops=dict(arrowstyle="->", color="white"),
                            zorder=20)
        self.annot.set_visible(False)
        
        self.ax.grid(True, color="#aaaaaa", linestyle="--", linewidth=0.5, alpha=0.5, zorder=0)
        self.ax.set_xticklabels(['14h','16h','18h','20h','22h','0h','2h','4h','6h','8h','10h']) 
        self.ax.tick_params(axis='x', colors='#aaaaaa', labelsize=9)
        self.ax.tick_params(axis='y', colors='#aaaaaa', labelsize=9)
        self.ax.axhline(0, color='#3498db', linestyle='-', linewidth=0.8, alpha=0.5, zorder=5)

        try:
            mw_ra, mw_dec = self.map_logic.get_milky_way_path()
            self.ax.plot(list(mw_ra), list(mw_dec), color="#bdc3c7", alpha=0.2, linewidth=10, linestyle="-", zorder=1)
            self.ax.plot(list(mw_ra), list(mw_dec), color="white", alpha=0.3, linewidth=1, linestyle="--", zorder=2)
        except Exception: pass

        if not data_list:
            self.ax.text(0, 0, "Keine Objekte gefunden", color="white", ha="center", zorder=20)
            self.canvas.draw()
            return

        ra_rad, dec_rad, colors, sizes = [], [], [], []
        self.names = []
        self.full_ids = []

        for item in data_list:
            r = item["ra"]
            d = item["dec"]
            
            if r > 180: r -= 360
            r_rad = -1 * (r * (3.14159 / 180)) 
            d_rad = d * (3.14159 / 180)
            
            ra_rad.append(r_rad)
            dec_rad.append(d_rad)
            self.names.append(item["name"])
            self.full_ids.append(item["full_id"])
            
            otype = self.main_logic.determine_object_type(item["name"])
            c = OBJ_TYPE_COLORS.get(otype, COLOR_OTHER)
            colors.append(c)
            
            sizes.append(40) 

        self.scat = self.ax.scatter(ra_rad, dec_rad, c=colors, s=sizes, 
                                    edgecolors='white', linewidth=0.8, 
                                    picker=5, zorder=10)
        
        title_text = "Gesamter Himmel" if selection_title == "Alle" else f"Sternbild: {selection_title}"
        self.ax.set_title(title_text, color="white", pad=15, fontsize=14)

        self.canvas.draw()
        
        # --- FIX: Automatisches "Wackeln" für High-DPI Update ---
        # Da das einfache Neusetzen der Geometrie nicht reicht, erzwingen wir
        # eine minimale Änderung (+1 Pixel Breite), die das Layout-System aufweckt.
        if not getattr(self, "_first_draw_done", False):
            self._first_draw_done = True
            
            def do_jiggle():
                try:
                    # Geometrie-String holen (z.B. '1200x800+100+100')
                    geo = self.geometry()
                    match = re.match(r"(\d+)x(\d+)(.*)", geo)
                    if match:
                        w = int(match.group(1))
                        h = int(match.group(2))
                        rest = match.group(3)
                        
                        # 1. Kurz ändern (+1px Breite)
                        self.geometry(f"{w+1}x{h}{rest}")
                        
                        # 2. Sofort wieder herstellen
                        self.after(50, lambda: self.geometry(geo))
                except Exception as e:
                    print(f"Jiggle Error: {e}")

            # Einmalig ausführen, kurz nachdem die Karte gezeichnet wurde
            self.after(100, do_jiggle)
        # -------------------------------------------------------------

    def update_annot(self, ind):
        try:
            pos = self.scat.get_offsets()[ind["ind"][0]]
            self.annot.xy = pos
            text = " / ".join([self.names[n] for n in ind["ind"]])
            self.annot.set_text(text)
        except: pass

    def on_hover(self, event):
        if not self.annot: return

        vis = self.annot.get_visible()
        if event.inaxes == self.ax and self.scat:
            cont, ind = self.scat.contains(event)
            if cont:
                self.update_annot(ind)
                self.annot.set_visible(True)
                self.canvas.draw_idle()
            else:
                if vis:
                    self.annot.set_visible(False)
                    self.canvas.draw_idle()

    def on_pick(self, event):
        if event.artist != self.scat: return
        try:
            ind = event.ind[0]
            if ind < len(self.full_ids):
                self.on_click_callback(self.full_ids[ind])
        except: pass