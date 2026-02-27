"""Fonctions utilitaires générales.

Ce module regroupe de petites fonctions utilisées par plusieurs autres
parties de l'application (arithmétique d'angles, limitation, formatage
de timestamp, etc.).
"""

from datetime import datetime


def now():
    """Retourne un timestamp UTC avec une précision milliseconde.

    Le format est identique à celui de la fonction ``banc_code.now``
    dans le code original.
    """
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def normalize_angle(angle):
    """Ramène un angle dans l'intervalle ``[-180, 180)``.

    Le résultat est équivalent à la formule originale utilisée dans
    ``banc_code.normalize_angle``.
    """
    return (angle + 180) % 360 - 180


def shortest_angle_error(target, current):
    """Calcule la différence signée minimale entre ``current`` et
    ``target`` (également normalisée dans ``[-180,180)``).

    Utile pour les boucles PID lorsque les angles se recouvrent.
    """
    return (target - current + 180) % 360 - 180


def clamp(value, minimum, maximum):
    """Limite ``value`` à l'intervalle fermé ``[minimum, maximum]``.

    Cet utilitaire rend l'intention plus claire et évite les répétitions
    de `min(max(...))` dans le code.
    """
    return max(min(value, maximum), minimum)
