"""UI helpers for the refactored application.

The GUI code from ``gui.py`` has been split into smaller pieces
contained in ``widgets.py`` and ``helpers.py``.  This package is
intended to demonstrate how a PyQt/PyQtGraph application can be built
in a modular fashion; the original ``gui.py`` file is left untouched in
the parent directory for legacy purposes.
"""

# re-export common names for convenience
from .widgets import OutLog, GimbalWidget3D, STYLE_SHEET
from .helpers import (
    create_section_title,
    create_labeled_widget,
    create_collapsible_section,
    create_slider,
)
