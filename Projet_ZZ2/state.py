"""État mutable partagé et drapeaux de contrôle de flux.

Le module original ``banc_code`` utilisait un ensemble de variables
globale (`running`, `paused`, `latest_theta`, etc.). Dans le code
refactoré elles résident toujours ici mais sont documentées et
accessibles via des fonctions utilitaires afin de clarifier où se
trouvent les éléments d'état importants.
"""

import threading
from typing import Optional, Tuple

# ------ concurrency primitives ------
accel_lock = threading.Lock()

# ------ accelerometer data (updated by ``accel`` module) ------
latest_theta: Optional[float] = None
latest_psi: Optional[float] = None
latest_raw: Optional[Tuple[int, int, int]] = None
latest_ts: Optional[str] = None

# ------ control flags ------
running = True
paused = False

# progress bar value (0-100)
progress_val = 0


def pause_system():
    """Marque l'application comme en pause ; les contrôleurs cesseront
d'envoyer des commandes tant que ``resume_system`` n'est pas appelé.
    """
    global paused
    if not paused:
        paused = True
        print("⏸ PAUSE ACTIVÉE")


def resume_system():
    """Supprime le drapeau de pause pour permettre la reprise des actions."""
    global paused
    if paused:
        paused = False
        print("▶ REPRISE DEMANDÉE")
