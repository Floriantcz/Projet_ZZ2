#!/usr/bin/env python3
import json
import csv
import math
import socket
import threading
import time
import os
from datetime import datetime
from typing import Optional, Tuple

# ---------------- CONFIG (chargé depuis settings.json) ----------------

DEFAULT_SETTINGS = {
    "network": {
        "host": "192.168.4.1",
        "port": 3535
    },
    "serial": {
        "port": "COM9",
        "baudrate": 115200
    }
}

def load_settings():
    if os.path.exists("settings.json"):
        try:
            with open("settings.json", "r") as f:
                data = json.load(f)
                print("✅ Paramètres chargés depuis settings.json")
                return data
        except Exception as e:
            print(f"⚠ Erreur lecture settings.json : {e}")
    print("⚠ Utilisation des paramètres par défaut.")
    return DEFAULT_SETTINGS

def save_settings(new_data):
    try:
        with open("settings.json", "w") as f:
            json.dump(new_data, f, indent=4)
        print("💾 settings.json mis à jour avec succès")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde de settings.json : {e}")
        return False

settings = load_settings()

HOST = settings.get("network", {}).get("host", DEFAULT_SETTINGS["network"]["host"])
PORT = settings.get("network", {}).get("port", DEFAULT_SETTINGS["network"]["port"])
SERIAL_PORT = settings.get("serial", {}).get("port", DEFAULT_SETTINGS["serial"]["port"])
BAUDRATE = settings.get("serial", {}).get("baudrate", DEFAULT_SETTINGS["serial"]["baudrate"])

# ---------------- CONSTANTES CONTROLE ----------------
SENSITIVITY = 256000.0  # LSB / g
KP = 2.5
MAX_SPEED = 30
MIN_SPEED = 15
STOP_THRESHOLD = 0.9
CONTROL_PERIOD = 0.05
SETTLE_TIME = 1.0
TIMEOUT = 30
THETA_SAFE = 85.0
PSI_SAFE = 179.0

# ---------------- SHARED STATE ----------------
accel_lock = threading.Lock()
latest_theta: Optional[float] = None
latest_psi: Optional[float] = None
latest_raw: Optional[Tuple[int, int, int]] = None
latest_ts: Optional[str] = None

running = True
paused = False
progress_val = 0

# ---------------- PAUSE / RESUME ----------------
def pause_system():
    global paused
    if not paused:
        paused = True
        print("⏸ PAUSE ACTIVÉE")

def resume_system():
    global paused
    if paused:
        paused = False
        print("▶ REPRISE DEMANDÉE")

# ---------------- UTILS ----------------
def now():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

def normalize_angle(a):
    return (a + 180) % 360 - 180

def shortest_angle_error(target, current):
    return (target - current + 180) % 360 - 180

def clamp(v, vmin, vmax):
    return max(min(v, vmax), vmin)

# ---------------- MOTOR LOW LEVEL ----------------
def send(ser, cmd):
    if ser is not None:
        try:
            ser.write((cmd + "\n").encode())
        except:
            pass

def stop_all(ser):
    send(ser, "?stopall")

def emergency_stop(ser):
    global running, paused, progress_val
    print("🛑 ARRÊT D'URGENCE ACTIVÉ")
    running = False
    paused = False
    progress_val = 0
    stop_all(ser)

def handle_pause(ser, start_time_ref):
    global paused, running
    if paused and running:
        stop_all(ser)
        print("|| SYSTÈME EN PAUSE ||")
        pause_start = time.time()
        while paused and running:
            time.sleep(0.1)
        pause_duration = time.time() - pause_start
        print("▶ REPRISE")
        return start_time_ref + pause_duration
    return start_time_ref

# ---------------- ACCEL ----------------
def lsb_to_g(ax, ay, az):
    return ax / SENSITIVITY, ay / SENSITIVITY, az / SENSITIVITY

def compute_angles(ax, ay, az):
    eps = 1e-12
    theta = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az + eps)))
    psi = math.degrees(math.atan2(ay, az))
    theta = clamp(theta, -90, 90)
    psi = normalize_angle(psi)
    return theta, psi

def parse_asc3(line):
    p = line.strip().split()
    if len(p) >= 5 and p[0] == "ASC3":
        try:
            return int(p[2]), int(p[3]), int(p[4])
        except:
            pass
    return None

def accel_reader(sock):
    global latest_theta, latest_psi, latest_raw, latest_ts, running
    if sock is None:
        print("⚠ AccelReader: Pas de socket, thread arrêté.")
        return
    
    buf = ""
    sock.settimeout(1)
    while running:
        try:
            data = sock.recv(4096).decode(errors="ignore")
            if not data: break
            buf += data
            lines = buf.split("\n")
            buf = lines[-1]
            for line in lines[:-1]:
                r = parse_asc3(line)
                if not r:
                    continue
                ax_g, ay_g, az_g = lsb_to_g(*r)
                theta, psi = compute_angles(ax_g, ay_g, az_g)
                with accel_lock:
                    latest_theta = theta
                    latest_psi = psi
                    latest_raw = r
                    latest_ts = now()
        except:
            pass

# ---------------- MOTOR CONTROL ----------------
def move_motor(target, get_angle, motor_id, name, amin, amax, ser):
    global running
    if ser is None:
        print(f"❌ Erreur: Impossible de bouger {name}, port série non connecté.")
        return False

    target = clamp(target, amin, amax)
    start = time.time()
    print(f"→ {name} cible : {target:+.1f}°")

    while running:
        start = handle_pause(ser, start)
        with accel_lock:
            current = get_angle()

        if current is None:
            time.sleep(CONTROL_PERIOD)
            continue

        current = normalize_angle(current)
        error = shortest_angle_error(target, current)

        if abs(error) < STOP_THRESHOLD:
            stop_all(ser)
            print(f"✓ {name} atteint")
            return True

        speed = clamp(KP * error, -MAX_SPEED, MAX_SPEED)
        if abs(speed) < MIN_SPEED:
            speed = math.copysign(MIN_SPEED, speed)

        send(ser, f"?m{motor_id}={int(speed)}")

        if time.time() - start > TIMEOUT:
            stop_all(ser)
            print(f"❌ Timeout {name}")
            return False

        time.sleep(CONTROL_PERIOD)

    stop_all(ser)
    return False

# ---------------- SCAN ----------------
def sweep_psi(theta_cmd, psi_positions, ser, dataset, progress_callback):
    global running
    for idx, psi_target in enumerate(psi_positions, 1):
        if not running:
            return False
        print(f"    → Psi {idx}/{len(psi_positions)} : {psi_target:+.1f}°")
        if not move_motor(psi_target, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser):
            return False
        with accel_lock:
            if latest_raw:
                ax, ay, az = latest_raw
                norm = math.sqrt(sum((v / SENSITIVITY) ** 2 for v in latest_raw))
                dataset.append([latest_ts, theta_cmd, latest_theta, latest_psi, ax, ay, az, norm])
        progress_callback()
    return True

def run_sequence(config_path, ser):
    global running, progress_val
    progress_val = 0
    try:
        with open(config_path) as f:
            sequence = json.load(f)["sequence"]
    except Exception as e:
        print(f"❌ Erreur lecture config: {e}")
        return

    total_psi_points = sum(len(step.get("psi_positions", [])) for step in sequence)
    points_done = 0

    def update_progress():
        nonlocal points_done
        global progress_val
        points_done += 1
        if total_psi_points > 0:
            progress_val = int((points_done / total_psi_points) * 100)

    dataset = []
    print("=== INITIALISATION (Psi 180°) ===")
    if not move_motor(180, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser):
        return

    for step_idx, step in enumerate(sequence, 1):
        if not running:
            break
        theta_cmd = clamp(step["theta"], -THETA_SAFE, THETA_SAFE)
        psi_positions = step.get("psi_positions", [])
        print(f"\nÉTAPE {step_idx}/{len(sequence)} (Theta {theta_cmd}°)")
        if not move_motor(theta_cmd, lambda: latest_theta, 1, "Theta", -THETA_SAFE, THETA_SAFE, ser):
            break
        if not sweep_psi(theta_cmd, psi_positions, ser, dataset, update_progress):
            break

    if running:
        print("\n=== FIN DU SCAN RÉUSSIE ===")
        progress_val = 100
        move_motor(0, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser)
        move_motor(0, lambda: latest_theta, 1, "Theta", -THETA_SAFE, THETA_SAFE, ser)

    if dataset:
        fname = f"scan_{datetime.now().strftime('%H%M%S')}.csv"
        with open(fname, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "theta_cmd", "theta", "psi", "x", "y", "z", "norm"])
            writer.writerows(dataset)
        print(f"💾 Fichier sauvegardé : {fname}")