"""Diagnosi: il riconoscimento delle scene (CLIP) funziona sul computer di GitHub? Scrive il risultato in diagnosi_scena.txt."""
import platform, traceback
import numpy as np

righe = [f"python {platform.python_version()}"]
try:
    import torch, open_clip
    righe.append(f"torch {torch.__version__} | open_clip {open_clip.__version__} | numpy {np.__version__}")
    import scena
    scena._clip()
    frame = np.full((640, 360, 3), 120, np.uint8)
    righe.append("riconosci: " + repr(scena.riconosci([frame] * 6, "")))
    righe.append("OK")
except Exception:
    righe.append(traceback.format_exc())
open("diagnosi_scena.txt", "w", encoding="utf-8").write("\n".join(righe) + "\n")
print("\n".join(righe))
