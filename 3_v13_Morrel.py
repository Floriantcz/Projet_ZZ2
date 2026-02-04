#!/usr/bin/env python3
import argparse
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
SERIAL_PORT = "COM3"  # À ajuster selon votre OS
BAUDRATE = 115200

SENSITIVITY = 256000.0

# --- Paramètres d'asservissement (Indispensables) ---
KP = 2.5               # Gain proportionnel
MAX_SPEED = 30         # Vitesse max moteur
MIN_SPEED = 15         # Vitesse min pour vaincre les frottements
STOP_THRESHOLD = 0.5   # Précision d'arrêt (degrés)
STABLE_REQUIRED = 10   # Nombre de lectures stables avant de valider
CONTROL_PERIOD = 0.05  # 50ms

SETTLE_TIMEOUT = 8.0
STABLE_TOL = 0.008
OMEGA_EST = 8.04       # Estimation pour les mouvements longs

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
    eps = 1e-12
    # Theta (Moteur 1)
    theta = math.degrees(math.atan2(ax_g, math.sqrt(ay_g**2 + az_g**2 + eps)))
    # Psi Base (Moteur 2)
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
                    # Unwrapping Psi pour continuité
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
def move_to_angle_closed_loop(target, motor_id):
    """
    FONCTION CLÉ : Asservissement en boucle fermée.
    Remplace move_psi_direct et les time.sleep imprécis.
    """
    name = "Theta" if motor_id == 1 else "Psi"
    print(f"--> Asservissement M{motor_id} ({name}) vers {target:.2f}°")
    
    stable_count = 0
    start_time = time.time()

    while running_event.is_set():
        with accel_lock:
            current = latest_theta if motor_id == 1 else latest_psi_unwrapped
        
        if current is None: continue

        error = target - current
        
        # Vérification de l'arrêt
        if abs(error) < STOP_THRESHOLD:
            stable_count += 1
            if stable_count >= STABLE_REQUIRED:
                send_command(f"?stopall")
                break
        else:
            stable_count = 0

        # Calcul de la vitesse proportionnelle
        speed = KP * error
        speed = max(min(speed, MAX_SPEED), -MAX_SPEED)
        if abs(speed) < MIN_SPEED:
            speed = math.copysign(MIN_SPEED, speed)

        send_command(f"?m{motor_id}={int(speed)}")

        if time.time() - start_time > 30: # Timeout sécurité
            send_command(f"?stopall")
            print("Timeout!")
            break
        
        time.sleep(CONTROL_PERIOD)

# ------------------- HELPERS MOTEUR -------------------
def send_command(cmd):
    try:
        ser.write((cmd + "\n").encode())
        ser.flush()
    except: pass

# ------------------- LOGIQUE DE BALAYAGE -------------------
def sweep_psi_zigzag_asservi(theta_deg, dataset, start_pos, step_deg=30.0):
    target_end = -180.0 if start_pos > 0 else 180.0
    direction = -1 if target_end < start_pos else 1
    num_steps = int(360 / step_deg)
    
    current_target = start_pos
    for i in range(num_steps + 1):
        # 1. Aller à la position précise
        move_to_angle_closed_loop(current_target, motor_id=2)
        
        # 2. Mesure
        time.sleep(0.5) # Petit temps de repos final
        with accel_lock:
            psi_meas, th_meas = latest_psi_unwrapped, latest_theta
            raw, ts = latest_raw_lsb, latest_raw_ts
            accel = latest_accel_g
        
        if accel:
            normg = math.sqrt(accel[0]**2 + accel[1]**2 + accel[2]**2)
            dataset.append([ts, theta_deg, th_meas, psi_meas, raw[0], raw[1], raw[2], normg])
            print(f"Point {i}: Psi={psi_meas:.2f}°")

        # 3. Préparer le pas suivant
        if i < num_steps:
            current_target += direction * step_deg

    return target_end

def run_scan_sequence():
    running_event.set()
    # Connexions (Socket et Serial déjà initialisés globalement ou ici)
    reader = threading.Thread(target=accel_reader_thread, args=(sock,), daemon=True)
    reader.start()

    dataset = []
    current_psi_side = 180.0 

    try:
        # Séquence automatique (sans input utilisateur)
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

        # Position initiale précise
        move_to_angle_closed_loop(180.0, motor_id=2)

        for step in sequence:
            # Positionnement Theta précis
            move_to_angle_closed_loop(step["theta"], motor_id=1)

            if step["psi_sweep"]:
                current_psi_side = sweep_psi_zigzag_asservi(step["theta"], dataset, current_psi_side)
            else:
                time.sleep(1.0)
                # Enregistrement simple...
        
        # Retour à 0
        move_to_angle_closed_loop(0.0, motor_id=2)

    finally:
        running_event.clear()
        ser.close()
        sock.close()

# (Ajoutez les imports et initialisations nécessaires pour sock et ser avant run_scan_sequence)
