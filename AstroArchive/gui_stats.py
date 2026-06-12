import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

# --- NEU: Konstanten importieren ---
from constants import ORDER_TYPES, OBJ_TYPE_COLORS, COLOR_UNKNOWN
# -----------------------------------

class StatsWindow(ctk.CTkToplevel):
    def __init__(self, parent, logic):
        super().__init__(parent)
        self.title("AstroArchive Statistik")
        self.geometry("1100x650") 
        
        # --- Event-Handler für das Schließen des Fensters ---
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()
        
        self.logic = logic
        self.fig = None  # Platzhalter für die Grafik
        
        ctk.CTkLabel(self, text="Deine Sammlung im Detail", font=("Arial", 20, "bold")).pack(pady=10)
        
        self.chart_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chart_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.draw_charts()
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", pady=20)
        ctk.CTkButton(btn_frame, text="Schließen", command=self.on_close, width=200).pack()

    def on_close(self):
        # Wichtig: Figure schließen, um Speicherlecks zu vermeiden
        if self.fig:
            plt.close(self.fig)
        self.destroy()

    def draw_charts(self):
        stats = self.logic.get_extended_stats()
        
        # Matplotlib Style
        plt.style.use('dark_background')
        
        # Figure erstellen
        self.fig = Figure(figsize=(10, 5), dpi=100)
        
        # 1. Kameras (Linkes Diagramm)
        ax1 = self.fig.add_subplot(121)
        
        cam_labels = []
        cam_sizes = []
        # Manuelle Farben für Kameras (könnte man auch in constants.py packen, hier ok)
        colors_cam = ["#e67e22", "#e74c3c", "#3498db", "#95a5a6"] 
        
        for k, v in stats["cameras"].items():
            if v > 0:
                cam_labels.append(f"{k} ({v})")
                cam_sizes.append(v)
        
        if cam_sizes:
            wedges, texts, autotexts = ax1.pie(cam_sizes, labels=None, autopct='%1.1f%%', startangle=90, colors=colors_cam[:len(cam_sizes)])
            ax1.set_title("Kamera-Verteilung")
            ax1.legend(wedges, cam_labels, title="Kameras", loc="best", bbox_to_anchor=(0.9, 0, 0.5, 1))
        else:
            ax1.text(0.5, 0.5, "Keine Daten", ha="center")

        # 2. Objekttypen (Rechtes Diagramm) - JETZT MIT KONSTANTEN
        ax2 = self.fig.add_subplot(122)
        type_labels = []
        type_sizes = []
        chart_colors = []
        
        # Wir iterieren durch die feste Reihenfolge aus constants.py
        for k in ORDER_TYPES:
            val = stats["types"].get(k, 0)
            if val > 0:
                type_labels.append(f"{k} ({val})")
                type_sizes.append(val)
                # Farbe aus dem Mapping holen
                chart_colors.append(OBJ_TYPE_COLORS.get(k, COLOR_UNKNOWN))
                
        if type_sizes:
            wedges2, texts2, autotexts2 = ax2.pie(type_sizes, labels=None, autopct='%1.1f%%', startangle=140, colors=chart_colors)
            ax2.set_title("Objekt-Typen")
            ax2.legend(wedges2, type_labels, title="Typen", loc="best", bbox_to_anchor=(0.9, 0, 0.5, 1))
        else:
            ax2.text(0.5, 0.5, "Keine Daten", ha="center")

        self.fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)