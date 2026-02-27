"""Utilitaires de traitement de l'accéléromètre.

Fonctions qui convertissent les chaînes ASC3 brutes provenant du
matériel en unités physiques, calculent les angles et mettent à jour
les valeurs en direct du thread de lecture. Cette logique était au
départ embarquée dans ``banc_code`` et est maintenant isolée.
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
    """Traite une seule ligne reçue depuis la socket de
    l'accéléromètre.

    Le format attendu est ``ASC3 <ignored> ax ay az``. Retourne ``None`` si
    la ligne n'était pas analysable.
    """
    parts = line.strip().split()
    if len(parts) >= 5 and parts[0] == "ASC3":
        try:
            return int(parts[2]), int(parts[3]), int(parts[4])
        except ValueError:
            pass
    return None


def accel_reader(sock: socket.socket):
    """Fonction de thread en arrière-plan qui lit des données depuis
    ``sock``.

    Les variables globales du module :mod:`state` sont mises à jour via
    le verrou partagé afin que d'autres parties du programme puissent
    lire en toute sécurité l'échantillon le plus récent.
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


def accel_reader_serial(ser):
    """Lit les lignes de l'accéléromètre depuis un port série/USB.

    L'implémentation reflète celle de :func:`accel_reader` mais consomme
    les données depuis une interface série plutôt qu'une socket TCP. Cela
    est utilisé lorsque l'utilisateur choisit ``transport = 'usb'`` dans la
    configuration.
    """
    if ser is None:
        print("⚠ AccelReader USB: port série non connecté, thread arrêté.")
        return

    while state.running:
        try:
            # read a full line (blocks up to ``timeout`` on the serial port)
            line = ser.readline().decode(errors="ignore")
            if not line:
                continue
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
            pass
        time.sleep(0.001)
