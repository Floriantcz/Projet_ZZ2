"""Accelerometer processing utilities.

Functions which convert raw ASC3 strings from the hardware into
physical units, compute angles, and maintain the reader thread live
values.  This logic was originally embedded in ``banc_code`` and is
now isolated.
"""

import math
import socket
import time
from typing import Optional

from . import state, utils

# sensitivity constant (LSB per g)
SENSITIVITY = 256000.0


def lsb_to_g(ax: int, ay: int, az: int):
    """Convert raw accelerometer counts to g's.

    Parameters mirror the old implementation but are now pure.
    """
    return ax / SENSITIVITY, ay / SENSITIVITY, az / SENSITIVITY


def compute_angles(ax: float, ay: float, az: float):
    """Return (theta, psi) from acceleration vector in g.

    The formula is unchanged from ``banc_code`` but the arguments are
    clearly documented here.
    """
    eps = 1e-12
    theta = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az + eps)))
    psi = math.degrees(math.atan2(ay, az))
    theta = utils.clamp(theta, -90, 90)
    psi = utils.normalize_angle(psi)
    return theta, psi


def parse_asc3(line: str) -> Optional[tuple]:
    """Handle a single line received from the accelerometer socket.

    The expected format is ``ASC3 <ignored> ax ay az``.  Returns ``None``
    if the line was not parsable.
    """
    parts = line.strip().split()
    if len(parts) >= 5 and parts[0] == "ASC3":
        try:
            return int(parts[2]), int(parts[3]), int(parts[4])
        except ValueError:
            pass
    return None


def accel_reader(sock: socket.socket):
    """Background thread function which reads data from ``sock``.

    The global variables in :mod:`state` are updated via the shared
    lock so that other parts of the program can safely read the most
    recent sample.
    """
    if sock is None:
        print("⚠ AccelReader: Pas de socket, thread arrêté.")
        return

    buf = ""
    sock.settimeout(1)
    while state.running:
        try:
            data = sock.recv(4096).decode(errors="ignore")
            if not data:
                break
            buf += data
            lines = buf.split("\n")
            buf = lines[-1]
            for line in lines[:-1]:
                r = parse_asc3(line)
                if not r:
                    continue
                ax_g, ay_g, az_g = lsb_to_g(*r)
                theta, psi = compute_angles(ax_g, ay_g, az_g)
                with state.accel_lock:
                    state.latest_theta = theta
                    state.latest_psi = psi
                    state.latest_raw = r
                    state.latest_ts = utils.now()
        except Exception:
            # Ignore timeouts and decode errors; loop will retry
            pass
        
        # small sleep avoids busy‑wait and reduces CPU usage
        time.sleep(0.001)
