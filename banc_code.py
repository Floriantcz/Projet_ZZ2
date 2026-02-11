#!/usr/bin/env python3
import json
import csv
import math
import socket
import threading
import time
from datetime import datetime
from typing import Optional, Tuple

# ---------------- CONFIG ----------------
HOST = "192.168.4.1"
PORT = 3535
SERIAL_PORT = "COM9"
BAUDRATE = 115200
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
paused = False  # Nouvelle variable pour la pause

# ---------------- UTILS ----------------
def now():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

def normalize_angle(a):
    return (a + 180) % 360 - 180

def shortest_angle_error(target, current):
    return (target - current + 180) % 360 - 180

def clamp(v, vmin, vmax):
    return max(min(v, vmax), vmin)

def handle_pause(ser, start_time_ref):
    """Bloque l'exécution si paused=True et compense le temps pour le timeout."""
    global paused, running
    if paused:
        stop_all(ser)
        print("\n|| SYSTÈME EN PAUSE ||")
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
        try: return int(p[2]), int(p[3]), int(p[4])
        except: pass
    return None

def accel_reader(sock):
    global latest_theta, latest_psi, latest_raw, latest_ts, running
    buf = ""
    sock.settimeout(1)
    while running:
        try:
            data = sock.recv(4096).decode(errors="ignore")
            buf += data
            lines = buf.split("\n")
            buf = lines[-1]
            for line in lines[:-1]:
                r = parse_asc3(line)
                if not r: continue
                ax_g, ay_g, az_g = lsb_to_g(*r)
                theta, psi = compute_angles(ax_g, ay_g, az_g)
                with accel_lock:
                    latest_theta, latest_psi, latest_raw, latest_ts = theta, psi, r, now()
        except: pass

# ---------------- MOTOR ----------------
def send(ser, cmd):
    ser.write((cmd + "\n").encode())

def stop_all(ser):
    send(ser, "?stopall")

def move_motor(target, get_angle, motor_id, name, amin, amax, ser):
    global running, paused
    target = clamp(target, amin, amax)
    start = time.time()
    print(f"→ {name} cible : {target:+.1f}°")

    while running:
        start = handle_pause(ser, start)
        if not running: return False

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
    return False

# ---------------- SCAN LOGIC ----------------
def sweep_psi(theta_cmd, psi_positions, ser, dataset):
    global running
    for idx, psi_target in enumerate(psi_positions, 1):
        handle_pause(ser, time.time())
        if not running: return False
        
        print(f"    → Psi {idx}/{len(psi_positions)} : {psi_target:+.1f}°")
        if not move_motor(psi_target, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser):
            return False

        handle_pause(ser, time.time())
        with accel_lock:
            if latest_raw:
                ax, ay, az = latest_raw
                norm = math.sqrt(sum((v / SENSITIVITY) ** 2 for v in latest_raw))
                dataset.append([latest_ts, theta_cmd, latest_theta, latest_psi, ax, ay, az, norm])
    return True

def run_sequence(config_path, ser):
    global running, paused
    with open(config_path) as f:
        sequence = json.load(f)["sequence"]
    dataset = []

    print("\n=== INIT (Psi 180°) ===")
    if not move_motor(180, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser):
        return

    for step_idx, step in enumerate(sequence, 1):
        if not running: break
        theta_cmd = clamp(step["theta"], -THETA_SAFE, THETA_SAFE)
        psi_positions = step.get("psi_positions", [])

        print(f"\n=== ÉTAPE {step_idx}/{len(sequence)} (Theta {theta_cmd}°) ===")
        if not move_motor(theta_cmd, lambda: latest_theta, 1, "Theta", -THETA_SAFE, THETA_SAFE, ser):
            break

        if not sweep_psi(theta_cmd, psi_positions, ser, dataset):
            break

    if running:
        print("\n=== FIN RÉUSSIE ===")
        move_motor(0, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser)
        move_motor(0, lambda: latest_theta, 1, "Theta", -THETA_SAFE, THETA_SAFE, ser)
    
    if dataset:
        fname = f"scan_{datetime.now().strftime('%H%M%S')}.csv"
        with open(fname, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "theta_cmd", "theta", "psi", "x", "y", "z", "norm"])
            writer.writerows(dataset)
        print(f"Sauvegardé : {fname}")