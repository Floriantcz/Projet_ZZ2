"""Abstractions de commandes moteurs et initialisation du banc.

Le protocole série bas niveau est encapsulé ici afin que les couches
supérieures puissent simplement appeler ``move_motor`` avec un angle
cible et une fonction retournant la position actuelle. La logique
d'arrêt d'urgence et de pause se trouvent également dans ce module.
"""

import math
import time
from typing import Callable, Optional

from . import state, utils

# constantes PID par défaut (extraites de l'ancien banc_code)
KP = 2.5
MAX_SPEED = 30
MIN_SPEED = 15
STOP_THRESHOLD = 0.9
CONTROL_PERIOD = 0.05
TIMEOUT = 30
THETA_SAFE = 85.0
PSI_SAFE = 179.0
SETTLE_TIME = 0.5  # temps d'attente après mouvement (secondes)


def send(ser, cmd: str):
    """Écrit une chaîne de commande sur le port série si disponible."""
    if ser is not None:
        try:
            ser.write((cmd + "\n").encode())
        except Exception:
            # ignore write errors; the caller can decide to abort
            pass


def stop_all(ser):
    """Arrête immédiatement les deux moteurs."""
    send(ser, "?stopall")


def emergency_stop(ser):
    """Déclenche un arrêt immédiat des mouvements et remet la
    progression à zéro.

    Cela reflète ``banc_code.emergency_stop`` mais vit dans le paquet
    refactoré.
    """
    global KP, MAX_SPEED
    print("🛑 ARRÊT D'URGENCE ACTIVÉ")
    state.running = False
    state.paused = False
    state.progress_val = 0
    stop_all(ser)


def handle_pause(ser, start_time_ref):
    """Helper interne utilisé par :func:`move_motor`.

    Si le système est en pause, cette fonction bloquera jusqu'à ce
    qu'il reprenne, en arrêtant les moteurs pendant ce temps. La valeur
    renvoyée est un horodatage ajusté pour compenser la durée de pause,
    ce qui maintient les calculs de progression corrects.
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
    """Bouge un moteur unique jusqu'à l'angle souhaité.

    Paramètres
    ----------
    target : float
        Angle désiré en degrés.
    get_angle : callable
        Fonction retournant la valeur *actuelle* de l'angle contrôlé.
    motor_id : int
        Identifiant envoyé sur le bus série (1 pour theta, 2 pour psi).
    name : str
        Nom convivial utilisé dans les messages de debug.
    amin, amax : float
        Limites de sécurité pour l'angle demandé.
    ser
        Objet port série, ou ``None`` si non connecté.

    Retour
    ------
    bool
        ``True`` si le moteur atteint la cible avant un timeout, sinon
        ``False`` si l'opération est abandonnée ou échoue.
    """
    if ser is None:
        print(f"❌ Erreur: Impossible de bouger {name}, port série non connecté.")
        return False

    target = utils.clamp(target, amin, amax)
    start = time.time()
    print(f"→ {name} cible : {target:+.1f}° (state.running={state.running})")

    iterations = 0
    while state.running:
        iterations += 1
        if iterations % 20 == 0:  # Log every second
            print(f"🔍 DEBUG: {name} boucle #{iterations}, still running...")
            
        start = handle_pause(ser, start)
        with state.accel_lock:
            current = get_angle()

        if current is None:
            if iterations == 1:
                print(f"⚠ {name}: angle actuel None, attente données accéléromètre...")
            time.sleep(CONTROL_PERIOD)
            continue

        current = utils.normalize_angle(current)
        error = utils.shortest_angle_error(target, current)

        if iterations <= 3:  # Log first few iterations
            print(f"🔍 DEBUG: {name} iter {iterations}: current={current:.1f}°, error={error:.1f}°")

        if abs(error) < STOP_THRESHOLD:
            stop_all(ser)
            print(f"✓ {name} atteint après {iterations} itérations")
            return True

        speed = utils.clamp(KP * error, -MAX_SPEED, MAX_SPEED)
        if abs(speed) < MIN_SPEED:
            speed = math.copysign(MIN_SPEED, speed)

        send(ser, f"?m{motor_id}={int(speed)}")

        if time.time() - start > TIMEOUT:
            stop_all(ser)
            print(f"❌ Timeout {name} après {iterations} itérations")
            return False

        time.sleep(CONTROL_PERIOD)

    stop_all(ser)
    print(f"⚠ {name}: sortie de boucle car state.running=False après {iterations} itérations")
    return False


def init_bench_home(ser) -> bool:
    """Ramène le banc à son orientation initiale (0°,0°).

    Cela est exécuté au démarrage de l'interface dans le programme
    original. La séquence est :

    1. Déplacer Psi à 0°
    2. Déplacer Theta à 0°

    Chaque étape est interrompue si le moteur correspondant ne peut
    atteindre la cible.
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