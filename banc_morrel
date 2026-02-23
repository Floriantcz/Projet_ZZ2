#!/usr/bin/env python3
import json
import csv
import math
import socket
import threading
import numpy as np
import time
from datetime import datetime
from typing import Optional, Tuple

# ============================================================
# CONFIG PAR DÉFAUT (peuvent être surchargées par le GUI)
# ============================================================
# ---------------- CONFIG ----------------
HOST = "192.168.4.1"
PORT = 3535
SERIAL_PORT = "/dev/ttyACM0"
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


# ============================================================
# ÉTAT PARTAGÉ
# ============================================================
accel_lock = threading.Lock()
latest_theta: Optional[float] = None
latest_psi: Optional[float] = None
latest_raw: Optional[Tuple[int, int, int]] = None
latest_ts: Optional[str] = None

running = True
paused = False
progress_val = 0

# ============================================================
# PAUSE / RESUME (GUI compatible)
# ============================================================
def pause_system():
    global paused
    paused = True
    print("⏸ PAUSE ACTIVÉE")

def resume_system():
    global paused
    paused = False
    print("▶ REPRISE")

# ============================================================
# UTILS
# ============================================================
def now():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

def normalize_angle(a):
    return (a + 180) % 360 - 180

def shortest_angle_error(target, current):
    return (target - current + 180) % 360 - 180

def clamp(v, vmin, vmax):
    return max(min(v, vmax), vmin)

# ============================================================
# ACCÉLÉRO
# ============================================================
def lsb_to_g(ax, ay, az):
    return ax / SENSITIVITY, ay / SENSITIVITY, az / SENSITIVITY

def compute_angles(ax, ay, az):
    eps = 1e-12
    theta = math.degrees(math.atan2(ax, math.sqrt(ay*ay + az*az + eps)))
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

# ============================================================
# MOTEUR BAS NIVEAU
# ============================================================
def send(ser, cmd):
    ser.write((cmd + "\n").encode())

def stop_all(ser):
    send(ser, "?stopall")

def handle_pause(ser, start_time_ref):
    global paused, running
    if paused and running:
        stop_all(ser)
        pause_start = time.time()
        while paused and running:
            time.sleep(0.1)
        return start_time_ref + (time.time() - pause_start)
    return start_time_ref

# ============================================================
# CONTRÔLE MOTEUR
# ============================================================
def move_motor(target, get_angle, motor_id, name, amin, amax, ser):
    global running

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

# ============================================================
#  NOUVELLE ACQUISITION (TA FEATURE)
# ============================================================
def take_static_measures(dataset, theta_cmd, samples=10):
    """Mode RAW : enregistre chaque mesure"""
    measures_taken = 0
    old_ts = None

    while measures_taken < samples:
        with accel_lock:
            ts = latest_ts
            raw = latest_raw
            theta = latest_theta
            psi = latest_psi

        if ts and raw and ts != old_ts:
            x, y, z = raw
            norm = math.sqrt(
                (x / SENSITIVITY) ** 2 +
                (y / SENSITIVITY) ** 2 +
                (z / SENSITIVITY) ** 2
            )

            dataset.append([ts, theta_cmd, theta, psi, x, y, z, norm])

            old_ts = ts
            measures_taken += 1
        else:
            time.sleep(0.01)


def take_static_measures_average(dataset, theta_cmd, samples=10):
    """Mode AVERAGE : moyenne des mesures"""
    measures_taken = 0
    old_ts = None
    ax_sum = ay_sum = az_sum = 0.0

    while measures_taken < samples:
        with accel_lock:
            ts = latest_ts
            raw = latest_raw
            theta = latest_theta
            psi = latest_psi

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
        (ax_mean / SENSITIVITY) ** 2 +
        (ay_mean / SENSITIVITY) ** 2 +
        (az_mean / SENSITIVITY) ** 2
    )

    dataset.append([
        ts, theta_cmd, theta, psi,
        ax_mean, ay_mean, az_mean, norm
    ])

# ============================================================
# SWEEP PSI (GUI READY)
# ============================================================
def sweep_psi(theta_cmd, psi_positions, ser, dataset,
              progress_callback=None,
              acquisition_mode="average"):

    global running

    for psi_target in psi_positions:
        if not running:
            return False

        if not move_motor(
            psi_target,
            lambda: latest_psi,
            2,
            "Psi",
            -PSI_SAFE,
            PSI_SAFE,
            ser,
        ):
            return False

        time.sleep(SETTLE_TIME)

        
        if acquisition_mode == "raw":
            take_static_measures(dataset, theta_cmd)
        else:
            take_static_measures_average(dataset, theta_cmd)

        if progress_callback:
            progress_callback()

    return True

# ============================================================
# SÉQUENCE PRINCIPALE (UTILISÉE PAR GUI)
# ============================================================
def run_sequence(config_path, ser,
                 acquisition_mode="average",
                 progress_callback=None):

    global running, progress_val
    progress_val = 0

    with open(config_path) as f:
        sequence = json.load(f)["sequence"]

    dataset = []

    total_points = sum(len(s.get("psi_positions", [])) for s in sequence)
    done = 0

    def update_progress():
        nonlocal done
        global progress_val
        done += 1
        if total_points:
            progress_val = int(100 * done / total_points)
        if progress_callback:
            progress_callback(progress_val)

    # position initiale
    move_motor(180, lambda: latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser)

    for step in sequence:
        if not running:
            break

        theta_cmd = clamp(step["theta"], -THETA_SAFE, THETA_SAFE)

        if not move_motor(
            theta_cmd,
            lambda: latest_theta,
            1,
            "Theta",
            -THETA_SAFE,
            THETA_SAFE,
            ser,
        ):
            break

        psi_positions = step.get("psi_positions", [])

        if not psi_positions:
            if acquisition_mode == "raw":
                take_static_measures(dataset, theta_cmd)
            else:
                take_static_measures_average(dataset, theta_cmd)


        if not sweep_psi(
            theta_cmd,
            psi_positions,
            ser,
            dataset,
            update_progress,
            acquisition_mode,
        ):
            break

    # sauvegarde
    if dataset:
        fname = f"scan_{datetime.now().strftime('%H%M%S')}.csv"
        with open(fname, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["time", "theta_cmd", "theta", "psi", "x_lsb", "y_lsb", "z_lsb", "norm"]
            )
            writer.writerows(dataset)

        print(f"💾 Fichier sauvegardé : {fname}")
