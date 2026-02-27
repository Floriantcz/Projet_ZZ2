"""Configuration helpers and constants.

This module centralises everything that concerns loading or saving
settings as well as default values.  It was extracted from the top
portion of ``banc_code.py`` so that configuration logic can be
reused independently of the rest of the bench control code.
"""

import json
import os

# directory containing this module (the package root)
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(_BASE_DIR, "config")

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


def _default_settings_path():
    """Return path to the default settings file inside the config folder."""
    return os.path.join(CONFIG_DIR, "settings.json")


def load_settings(path=None):
    """Read JSON settings from disk.

    Parameters
    ----------
    path : str or None
        Filename to open.  If ``None`` the default is
        ``config/settings.json`` relative to the package root.

    Returns
    -------
    dict
        Parsed configuration, or ``DEFAULT_SETTINGS`` if the file is
        missing or invalid.  Errors are printed to stdout.
    """
    if path is None:
        path = _default_settings_path()

    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                print(f"✅ Paramètres chargés depuis {path}")
                return data
        except Exception as e:
            print(f"⚠ Erreur lecture {path} : {e}")
    print("⚠ Utilisation des paramètres par défaut.")
    return DEFAULT_SETTINGS


def save_settings(new_data, path=None):
    """Persist a configuration dictionary to disk.

    Parameters
    ----------
    new_data : dict
        Data to be written as JSON.
    path : str or None
        Target filename.  If ``None`` the default is
        ``config/settings.json`` relative to the package root.

    Returns
    -------
    bool
        ``True`` on success, ``False`` if an I/O error occurred.
    """
    if path is None:
        path = _default_settings_path()
    # ensure destination directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(new_data, f, indent=4)
        print(f"💾 {path} mis à jour avec succès")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde de {path} : {e}")
        return False
