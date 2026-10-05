from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import omni.ui as ui

widgets = [w for w in dir(ui) if not w.startswith("_")]
print("UI WIDGETS:", [w for w in widgets if any(k in w.lower() for k in ["draw", "canvas", "rect", "line", "circle", "stack", "frame", "plot", "image"])])
app.close()
