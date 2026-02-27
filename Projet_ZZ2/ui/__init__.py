"""Aides d'interface utilisateur pour l'application refactorée.

Le code GUI de ``gui.py`` a été découpé en morceaux plus petits
contenus dans ``widgets.py`` et ``helpers.py``. Ce paquet sert à
montrer comment une application PyQt/PyQtGraph peut être construite
de manière modulaire ; l'ancien fichier ``gui.py`` reste inchangé dans
le dossier parent pour des raisons de compatibilité.
"""

# re-exporte des noms courants pour la commodité
from .widgets import OutLog, GimbalWidget3D, STYLE_SHEET
from .helpers import (
    create_section_title,
    create_labeled_widget,
    create_collapsible_section,
    create_slider,
)
