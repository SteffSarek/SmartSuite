# constants.py

# --- FARBDEFINITIONEN ---
COLOR_GALAXY  = "#f1c40f"  # Gelb/Orange
COLOR_NEBULA  = "#e74c3c"  # Rot/Pink
COLOR_CLUSTER = "#2ecc71"  # Grün (jetzt heller/frischer)
COLOR_COMET   = "#9b59b6"  # Lila
COLOR_OTHER   = "#3498db"  # Blau
COLOR_UNKNOWN = "#95a5a6"  # Grau

# Mapping für Logik und Charts
OBJ_TYPE_COLORS = {
    "Galaxy": COLOR_GALAXY,
    "Nebula": COLOR_NEBULA,
    "Cluster": COLOR_CLUSTER,
    "Comet": COLOR_COMET,
    "Other": COLOR_OTHER
}

# Reihenfolge für Legenden und Diagramme
ORDER_TYPES = ["Galaxy", "Nebula", "Cluster", "Comet", "Other"]