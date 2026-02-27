"""Motor command abstractions and bench initialization.

The low‑level serial protocol is wrapped here so that higher layers can
simply call ``move_motor`` with a target angle and a callable to read
back the current position.  Emergency stop logic and pause handling
live in this module as well.
"""

import math
import time
from typing import Callable, Optional

from . import state, utils

# default PID constants (extracted from original banc_code)
KP = 2.5
MAX_SPEED = 30
MIN_SPEED = 15
STOP_THRESHOLD = 0.9
CONTROL_PERIOD = 0.05
TIMEOUT = 30
THETA_SAFE = 85.0
PSI_SAFE = 179.0


def send(ser, cmd: str):
    """Write a command string to the serial port if available."""
    if ser is not None:
        try:
            ser.write((cmd + "\n").encode())
        except Exception:
            # ignore write errors; the caller can decide to abort
            pass


def stop_all(ser):
    """Immediately stop both motors."""
    send(ser, "?stopall")


def emergency_stop(ser):
    """Trigger an immediate shutdown of motion and reset progress.

    This mirrors ``banc_code.emergency_stop`` but lives in the
    refactored package.
    """
    global KP, MAX_SPEED
    print("🛑 ARRÊT D'URGENCE ACTIVÉ")
    state.running = False
    state.paused = False
    state.progress_val = 0
    stop_all(ser)


def handle_pause(ser, start_time_ref):
    """Internal helper used by :func:`move_motor`.

    If the system is paused this function will block until it is
    resumed, stopping the motors in the meantime.  The return value is
    an updated timestamp to compensate for the time spent paused, which
    keeps progress calculations correct.
    """
    if state.paused and state.running:
        stop_all(ser)
        print("|| SYSTÈME EN PAUSE ||")
        pause_start = time.time()
        while state.paused and state.running:
            time.sleep(0.1)
        pause_duration = time.time() - pause_start
        print("▶ REPRISE")
        return start_time_ref + pause_duration
    return start_time_ref


def move_motor(
    target: float,
    get_angle: Callable[[], Optional[float]],
    motor_id: int,
    name: str,
    amin: float,
    amax: float,
    ser
) -> bool:
    """Move a single motor until a desired angle is reached.

    Parameters
    ----------
    target : float
        Desired angle in degrees.
    get_angle : callable
        Function returning the *current* value of the controlled angle.
    motor_id : int
        Identifier sent on the serial bus (1 for theta, 2 for psi).
    name : str
        Human-readable name used in debug prints.
    amin, amax : float
        Safety limits for the commanded angle.
    ser
        Serial port object, or ``None`` if not connected.

    Returns
    -------
    bool
        ``True`` if the motor reached the target before a timeout or
        ``False`` if the operation was aborted or failed.
    """
    if ser is None:
        print(f"❌ Erreur: Impossible de bouger {name}, port série non connecté.")
        return False

    target = utils.clamp(target, amin, amax)
    start = time.time()
    print(f"→ {name} cible : {target:+.1f}°")

    while state.running:
        start = handle_pause(ser, start)
        with state.accel_lock:
            current = get_angle()

        if current is None:
            time.sleep(CONTROL_PERIOD)
            continue

        current = utils.normalize_angle(current)
        error = utils.shortest_angle_error(target, current)

        if abs(error) < STOP_THRESHOLD:
            stop_all(ser)
            print(f"✓ {name} atteint")
            return True

        speed = utils.clamp(KP * error, -MAX_SPEED, MAX_SPEED)
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


def init_bench_home(ser) -> bool:
    """Bring the bench to its home orientation (0°,0°).

    This is executed on GUI startup in the original program.  The
    sequence is:

    1. Move psi to 0°
    2. Move theta to 0°

    Each step aborts if the corresponding motor cannot reach the target.
    """
    if ser is None:
        return False

    print("=== INITIALISATION BANC (Home Position) ===")
    if not move_motor(0, lambda: state.latest_psi, 2, "Psi", -PSI_SAFE, PSI_SAFE, ser):
        print("⚠ Impossible d'initialiser Psi")
        return False

    if not move_motor(0, lambda: state.latest_theta, 1, "Theta", -THETA_SAFE, THETA_SAFE, ser):
        print("⚠ Impossible d'initialiser Theta")
        return False

    print("✅ Banc initialisé en position Home (Theta=0, Psi=0)")
    return True
