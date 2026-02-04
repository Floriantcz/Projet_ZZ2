#!/usr/bin/env python3
"""
Projet SAPIMAC - Banc de Calibration Accélérométrique
Collaboration : ISIMA / Institut Pascal / SAPIMAC
Objectif : Calibration automatique pour monitoring des déformations du bois.
"""

import csv
import math
import socket
import threading
import time
from datetime import datetime
from typing import List, Optional, Tuple

# ------------------- CONFIGURATION FUSIONNÉE -----------------------
HOST = "192.168.4.1"
PORT = 3535
SERIAL_PORT = "COM7"  # À modifier en '/dev/ttyACM1' si tu repasses sur Linux
BAUDRATE = 115200

SENSITIVITY = 256000.0

# --- Paramètres d'asservissement (Indispensables pour la précision) ---
KP = 2.5               # Gain proportionnel : définit la réactivité
MAX_SPEED = 30         # Vitesse plafond pour la sécurité mécanique
MIN_SPEED = 15         # Vitesse plancher pour vaincre le frottement statique
STOP_THRESHOLD = 0.5   # Précision d'arrêt en degrés
STABLE_REQUIRED = 10   # Nombre de lectures consécutives sous le seuil
CONTROL_PERIOD = 0.05  # Fréquence de rafraîchissement (50ms)

# ------------------- ÉTAT PARTAGÉ ------------------------
accel_lock = threading.Lock()
latest_theta = None
latest_psi_unwrapped = None
latest_accel_g = None
latest_raw_lsb = None
latest_raw_ts = None
running_event = threading.Event()

# ------------------- CALCULS & LECTURE -------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="microseconds") + "Z"

def lsb_to_g(ax_lsb, ay_lsb, az_lsb):
    return ax_lsb / SENSITIVITY, ay_lsb / SENSITIVITY, az_lsb / SENSITIVITY

def compute_angles_precise(ax_g, ay_g, az_g):
    """Calcule θ (inclinaison) et ψ (pivot) avec correction d'axe Z."""
    eps = 1e-12
    theta = math.degrees(math.atan2(ax_g, math.sqrt(ay_g**2 + az_g**2 + eps)))
    alpha_psi = math.degrees(math.atan2(ay_g, math.sqrt(ax_g**2 + az_g**2 + eps)))
    psi_base = (180.0 - alpha_psi if az_g < 0.0 else alpha_psi) % 360.0
    return theta, psi_base

def accel_reader_thread(sock: socket.socket):
    global latest_theta, latest_psi_unwrapped, latest_accel_g, latest_raw_lsb, latest_raw_ts
    buf = ""
    while running_event.is_set():
        try:
            data = sock.recv(4096).decode(errors="ignore")
            if not data: break
            buf += data
            lines = buf.split("\n")
            buf = lines[-1]
            for line in lines[:-1]:
                if not line.startswith("ASC3"): continue
                parts = line.strip().split()
                if len(parts) < 5: continue
                ax_lsb, ay_lsb, az_lsb = int(parts[2]), int(parts[3]), int(parts[4])
                ax_g, ay_g, az_g = lsb_to_g(ax_lsb, ay_lsb, az_lsb)
                theta, psi_b = compute_angles_precise(ax_g, ay_g, az_g)

                with accel_lock:
                    prev = latest_psi_unwrapped
                    if prev is None: latest_psi_unwrapped = psi_b
                    else:
                        k = round((prev - psi_b) / 360.0)
                        latest_psi_unwrapped = psi_b + 360.0 * k
                    
                    latest_theta = theta
                    latest_accel_g = (ax_g, ay_g, az_g)
                    latest_raw_lsb = (ax_lsb, ay_lsb, az_lsb)
                    latest_raw_ts = _now_iso()
        except: continue

# ------------------- FONCTION D'ASSERVISSEMENT --------------------
def send_command(cmd):
    """Envoie une commande G-code au contrôleur série."""
    try:
        ser.write((cmd + "\n").encode())
        ser.flush()
    except: pass

def move_to_angle_closed_loop(target, motor_id):
    """Règle le banc à l'angle cible via une boucle de rétroaction KP."""
    name = "Theta" if motor_id == 1 else "Psi"
    print(f"--> Asservissement M{motor_id} ({name}) vers {target:.2f}°", flush=True)
    
    stable_count = 0
    start_time = time.time()

    while running_event.is_set():
        with accel_lock:
            current = latest_theta if motor_id == 1 else latest_psi_unwrapped
        
        if current is None:
            time.sleep(0.1)
            continue

        error = target - current
        
        # Vérification du seuil de précision et de la stabilité
        if abs(error) < STOP_THRESHOLD:
            stable_count += 1
            if stable_count >= STABLE_REQUIRED:
                send_command("?stopall")
                break
        else:
            stable_count = 0

        # Algorithme Proportionnel
        speed = KP * error
        # Saturation de la vitesse (Clamp)
        speed = max(min(speed, MAX_SPEED), -MAX_SPEED)
        # Gestion du frottement (Vitesse minimale)
        if abs(speed) < MIN_SPEED:
            speed = math.copysign(MIN_SPEED, speed)

        send_command(f"?m{motor_id}={int(speed)}")

        # Timeout de sécurité (30 secondes)
        if time.time() - start_time > 30:
            send_command("?stopall")
            print(f"ERREUR : Timeout atteint pour {name} !", flush=True)
            break
        
        time.sleep(CONTROL_PERIOD)

# ------------------- LOGIQUE DE BALAYAGE -------------------
def sweep_psi_zigzag_asservi(theta_deg, dataset, start_pos, step_deg=30.0):
    """Effectue un balayage complet de 360° par paliers précis."""
    target_end = -180.0 if start_pos > 0 else 180.0
    direction = -1 if target_end < start_pos else 1
    num_steps = int(360 / step_deg)
    
    current_target = start_pos
    for i in range(num_steps + 1):
        # 1. Positionnement via asservissement
        move_to_angle_closed_loop(current_target, motor_id=2)
        
        # 2. Temps de repos métrologique et enregistrement
        time.sleep(0.5)
        with accel_lock:
            psi_meas, th_meas = latest_psi_unwrapped, latest_theta
            raw, ts = latest_raw_lsb, latest_raw_ts
            accel = latest_accel_g
        
        if accel:
            normg = math.sqrt(accel[0]**2 + accel[1]**2 + accel[2]**2)
            dataset.append([ts, theta_deg, th_meas, psi_meas, raw[0], raw[1], raw[2], normg])
            print(f"   [POINT {i}] Psi={psi_meas:.2f}° | Norm={normg:.4f}g", flush=True)

        if i < num_steps:
            current_target += direction * step_deg

    return target_end

def run_scan_sequence():
    """Gère l'intégralité de la séquence de test SAPIMAC."""
    running_event.set()
    reader = threading.Thread(target=accel_reader_thread, args=(sock,), daemon=True)
    reader.start()

    dataset = []
    current_psi_side = 180.0  # Point de départ du zigzag

    try:
        sequence = [
            {"theta": 0.0,   "psi_sweep": False},
            {"theta": 90.0,  "psi_sweep": False},
            {"theta": 60.0,  "psi_sweep": True},
            {"theta": 30.0,  "psi_sweep": True},
            {"theta": 0.0,   "psi_sweep": True},
            {"theta": -30.0, "psi_sweep": True},
            {"theta": -60.0, "psi_sweep": True},
            {"theta": -90.0, "psi_sweep": False},
            {"theta": 0.0,   "psi_sweep": False},
        ]

        print("--- Mise en position initiale (+180°) ---")
        move_to_angle_closed_loop(180.0, motor_id=2)

        for idx, step in enumerate(sequence):
            target_theta = step["theta"]
            print(f"\n=== PALIER {idx+1}/{len(sequence)} : Theta {target_theta}° ===")
            
            # Positionnement inclinaison
            move_to_angle_closed_loop(target_theta, motor_id=1)

            if step["psi_sweep"]:
                current_psi_side = sweep_psi_zigzag_asservi(target_theta, dataset, current_psi_side)
            else:
                time.sleep(1.0) # Mesure statique
                with accel_lock:
                    normg = math.sqrt(sum(x**2 for x in latest_accel_g)) if latest_accel_g else 0
                    dataset.append([latest_raw_ts, target_theta, latest_theta, latest_psi_unwrapped, 
                                    latest_raw_lsb[0], latest_raw_lsb[1], latest_raw_lsb[2], normg])

        print("\n--- Séquence terminée. Retour à l'origine ---")
        move_to_angle_closed_loop(0.0, motor_id=2)
        move_to_angle_closed_loop(0.0, motor_id=1)

        # Sauvegarde CSV
        filename = f"calib_sapimac_{int(time.time())}.csv"
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time_utc", "theta_cmd", "theta_meas", "psi_meas", "x_lsb", "y_lsb", "z_lsb", "norm_g"])
            writer.writerows(dataset)
        print(f"\nFichier sauvegardé : {filename}")

    finally:
        running_event.clear()
        reader.join(1.0)

# ------------------- POINT D'ENTRÉE DU SCRIPT -------------------
if __name__ == "__main__":
    import serial # Import local pour éviter les erreurs si non installé
    try:
        print("Initialisation du Banc SAPIMAC...")
        
        # Connexion Accéléromètre
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect((HOST, PORT))
        print(f"OK : Accéléromètre connecté ({HOST})")

        # Connexion Moteur
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        time.sleep(2) # Attente boot contrôleur
        print(f"OK : Contrôleur moteur connecté ({SERIAL_PORT})")

        run_scan_sequence()

    except KeyboardInterrupt:
        print("\nArrêt manuel détecté.")
    except Exception as e:
        print(f"\nERREUR CRITIQUE : {e}")
    finally:
        print("Fermeture des connexions...")
        try:
            send_command("?stopall")
            ser.close()
            sock.close()
        except: pass
        print("Fin du programme.")
