"""Shared mutable state and flow-control flags.

The original ``banc_code`` module used a collection of global
variables (`running`, `paused`, `latest_theta`, etc.).  In the
refactored code these still live here but they are documented and
accessed through helper functions so that it is clearer where the
important pieces of state are.
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
    """Mark the application as paused; controllers will stop sending
    commands until ``resume_system`` is called.
    """
    global paused
    if not paused:
        paused = True
        print("⏸ PAUSE ACTIVÉE")


def resume_system():
    """Remove the pause flag so that actions may continue."""
    global paused
    if paused:
        paused = False
        print("▶ REPRISE DEMANDÉE")
