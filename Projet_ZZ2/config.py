"""Fonctions et constantes de configuration.

Ce module centralise tout ce qui concerne la lecture ou l'écriture des
réglages ainsi que les valeurs par défaut. Il a été extrait de la
portion supérieure de ``banc_code.py`` afin que la logique de
configuration puisse être réutilisée indépendamment du reste du
code de contrôle du banc.
"""

import json
import os

# répertoire contenant ce module (racine du paquet)
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(_BASE_DIR, "config")

# ``transport`` sélectionne le type de connexion à l'accéléromètre ;
# ``tcp`` utilise l'hôte/port réseau ci-dessous, ``usb`` ouvre un lien
# série défini par le sous-dictionnaire ``usb``.
#
# ``network`` n'est utilisé qu'en mode TCP. ``usb`` contient un port et
# un baudrate qui ne servent que si ``transport`` vaut ``"usb"``.
DEFAULT_SETTINGS = {
    "transport": "tcp",
    "network": {
        "host": "192.168.4.1",
        "port": 3535
    },
    "usb": {
        "port": "",
        "baudrate": 115200
    },
    "serial": {
        "port": "COM9",
        "baudrate": 115200
    }
}


def _default_settings_path():
    """Retourne le chemin du fichier de réglages par défaut dans le
    dossier config."""
    return os.path.join(CONFIG_DIR, "settings.json")


def load_settings(path=None):
    """Lit des réglages JSON depuis le disque.

    Paramètres
    ----------
    path : str ou None
        Nom de fichier à ouvrir. Si ``None`` le défaut est
        ``config/settings.json`` relatif à la racine du paquet.

    Retour
    ------
    dict
        Configuration analysée, ou ``DEFAULT_SETTINGS`` si le fichier est
        absent ou invalide. Les erreurs sont affichées sur stdout.
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
    """Persiste un dictionnaire de configuration sur le disque.

    Paramètres
    ----------
    new_data : dict
        Données à écrire en JSON.
    path : str ou None
        Nom du fichier cible. Si ``None`` le défaut est
        ``config/settings.json`` relatif à la racine du paquet.

    Retour
    ------
    bool
        ``True`` si l'écriture réussit, ``False`` en cas d'erreur I/O.
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
