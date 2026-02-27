"""General-purpose helper functions.

This module collects small utilities that are used by several other
parts of the application (angle arithmetic, clamping, timestamp
formatting, etc.).
"""

from datetime import datetime


def now():
    """Return a UTC timestamp string with millisecond precision.

    The format matches the behaviour of :func:`banc_code.now` in the
    original code.
    """
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def normalize_angle(angle):
    """Wrap an angle into the range ``[-180, 180)``.

    The result is equivalent to the original formula used in
    ``banc_code.normalize_angle``.
    """
    return (angle + 180) % 360 - 180


def shortest_angle_error(target, current):
    """Compute the signed minimal difference from ``current`` to
    ``target`` (also normalized to ``[-180,180)``).

    Useful for PID loops when angles wrap around.
    """
    return (target - current + 180) % 360 - 180


def clamp(value, minimum, maximum):
    """Restrict ``value`` to the closed interval ``[minimum, maximum]``.

    This helper makes intent clearer and reduces repeated use of
    `min(max(...))` throughout the codebase.
    """
    return max(min(value, maximum), minimum)
