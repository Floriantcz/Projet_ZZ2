"""Aides pour le balayage de séquences et l'acquisition de données.

Ce module contient la logique précédemment située dans la seconde moitié
de ``banc_code.py``. Les fonctions sont paramétrées de sorte que les
appelants puissent fournir leurs propres callbacks de progression ou
objets port série ; elles ne dépendent pas de globals hormis le module
partagé ``state``.
"""

import csv
import json
import math
import time
from datetime import datetime
from typing import List

from . import state, motor, utils, accel


def take_static_measures(dataset: List[List], theta_cmd: float, samples: int = 10):
    """Collecte ``samples`` mesures individuelles à angles fixes.

    Les mesures sont ajoutées à ``dataset`` dans le même format que
    dans le code original. ``theta_cmd`` est la valeur de theta commandée
    correspondant à la position actuelle des moteurs.
    """
    measures_taken = 0
    old_ts = None

    while measures_taken < samples:
        with state.accel_lock:
            ts = state.latest_ts
            raw = state.latest_raw
            theta = state.latest_theta
            psi = state.latest_psi

        if ts and raw and ts != old_ts:
            x, y, z = raw
            norm = math.sqrt(
                (x / accel.SENSITIVITY) ** 2 +
                (y / accel.SENSITIVITY) ** 2 +
                (z / accel.SENSITIVITY) ** 2
            )
            dataset.append([ts, theta_cmd, theta, psi, x, y, z, norm])
            old_ts = ts
            measures_taken += 1
        else:
            time.sleep(0.01)


def take_static_measures_average(dataset: List[List], theta_cmd: float, samples: int = 10):
    """Identique à :func:`take_static_measures` mais effectue une
    moyenne pour chaque lot.

    Réduit le bruit des valeurs enregistrées ; c'est le mode
    "average" de l'interface graphique.
    """
    measures_taken = 0
    old_ts = None
    ax_sum = ay_sum = az_sum = 0.0

    while measures_taken < samples:
        with state.accel_lock:
            ts = state.latest_ts
            raw = state.latest_raw
            theta = state.latest_theta
            psi = state.latest_psi

        if ts and raw and ts != old_ts:
            ax, ay, az = raw
            ax_sum += ax
            ay_sum += ay
            az_sum += az
            old_ts = ts
            measures_taken += 1
        else:
            time.sleep(0.01)

    ax_mean = ax_sum / samples
    ay_mean = ay_sum / samples
    az_mean = az_sum / samples
    norm = math.sqrt(
        (ax_mean / accel.SENSITIVITY) ** 2 +
        (ay_mean / accel.SENSITIVITY) ** 2 +
        (az_mean / accel.SENSITIVITY) ** 2
    )
    dataset.append([ts, theta_cmd, theta, psi, ax_mean, ay_mean, az_mean, norm])


def sweep_psi(theta_cmd: float, psi_positions: List[float], ser, dataset: List[List],
              acquisition_mode: str = "average",
              progress_callback=None) -> bool:
    """Fait parcourir au moteur psi une série de positions et enregistre
    les données.

    Cet helper est utilisé par :func:`run_sequence` et est paramétré avec
    ``acquisition_mode`` et ``progress_callback`` afin qu'il puisse être
    réutilisé dans différents contextes (outil CLI, GUI, tests...).
    """
    global running

    for idx, psi_target in enumerate(psi_positions, 1):
        if not state.running:
            return False

        print(f"    → Psi {idx}/{len(psi_positions)} : {psi_target:+.1f}°")

        if not motor.move_motor(psi_target, lambda: state.latest_psi, 2, "Psi",
                                -motor.PSI_SAFE, motor.PSI_SAFE, ser):
            return False

        time.sleep(motor.SETTLE_TIME)

        if acquisition_mode == "raw":
            take_static_measures(dataset, theta_cmd, samples=10)
        else:
            take_static_measures_average(dataset, theta_cmd, samples=10)

        if progress_callback:
            progress_callback()

    return True


def run_sequence(config_path: str, ser, acquisition_mode: str = "average",
                 progress_callback=None):
    """Exécute une séquence de scan complète décrite par un fichier JSON.

    Le comportement reflète ``banc_code.run_sequence`` mais il s'agit
    désormais d'une petite fonction autonome qui peut être importée par
    des clients GUI ou non-GUI.
    """
    state.progress_val = 0

    try:
        with open(config_path) as f:
            sequence = json.load(f)["sequence"]
    except Exception as e:
        print(f"❌ Erreur lecture config: {e}")
        return

    dataset = []
    total_psi_points = sum(len(step.get("psi_positions", [])) for step in sequence)
    points_done = 0

    def _update_progress():
        nonlocal points_done
        points_done += 1
        if total_psi_points > 0:
            state.progress_val = int((points_done / total_psi_points) * 100)
        if progress_callback:
            progress_callback(state.progress_val)

    print("=== INITIALISATION (Psi 180°) ===")
    if not motor.move_motor(180, lambda: state.latest_psi, 2, "Psi",
                            -motor.PSI_SAFE, motor.PSI_SAFE, ser):
        return

    for step_idx, step in enumerate(sequence, 1):
        if not state.running:
            break
        theta_cmd = utils.clamp(step["theta"], -motor.THETA_SAFE, motor.THETA_SAFE)
        psi_positions = step.get("psi_positions", [])
        print(f"\nÉTAPE {step_idx}/{len(sequence)} (Theta {theta_cmd}°)")
        if not motor.move_motor(theta_cmd, lambda: state.latest_theta, 1, "Theta",
                                -motor.THETA_SAFE, motor.THETA_SAFE, ser):
            break
        if not sweep_psi(theta_cmd, psi_positions, ser, dataset,
                         acquisition_mode, _update_progress):
            break

    if state.running:
        print("\n=== FIN DU SCAN RÉUSSIE ===")
        state.progress_val = 100
        if progress_callback:
            progress_callback(100)
        motor.move_motor(0, lambda: state.latest_psi, 2, "Psi",
                         -motor.PSI_SAFE, motor.PSI_SAFE, ser)
        motor.move_motor(0, lambda: state.latest_theta, 1, "Theta",
                         -motor.THETA_SAFE, motor.THETA_SAFE, ser)

    if dataset:
        fname = f"scan_{datetime.now().strftime('%H%M%S')}.csv"
        with open(fname, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "theta_cmd", "theta", "psi", "x_lsb", "y_lsb", "z_lsb", "norm"])
            writer.writerows(dataset)
        print(f"💾 Fichier sauvegardé : {fname}")
