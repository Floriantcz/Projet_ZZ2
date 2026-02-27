"""Fonctions utilitaires pour construire des éléments GUI communs.

Ces helpers ont été extraits de la grande classe ``MainWindow`` de
``gui.py``. Ils permettent de créer des parties individuelles de la
fenêtre de manière isolée et de les tester ou réutiliser plus
i facilement.
"""

from PyQt5 import QtWidgets, QtCore


def create_section_title(text: str) -> QtWidgets.QLabel:
    """Retourne un label d'entête de section stylisé."""
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("Title")
    return lbl


def create_labeled_widget(label_text: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Encadre ``widget`` d'une petite étiquette au-dessus.

    La méthode originale dans ``gui.py`` construisait un widget
    composite avec un layout vertical. Nous réutilisons le même aspect
    ici afin que le reste de l'interface reste visuellement
    cohérent.
    """
    c = QtWidgets.QVBoxLayout()
    lbl = QtWidgets.QLabel(label_text)
    lbl.setAlignment(QtCore.Qt.AlignCenter)
    lbl.setStyleSheet("font-size: 10px; color: #7F8C8D;")
    c.addWidget(lbl)
    c.addWidget(widget)
    w = QtWidgets.QWidget()
    w.setLayout(c)
    return w


def create_collapsible_section(title: str, content_widget: QtWidgets.QWidget, expanded: bool = True) -> QtWidgets.QWidget:
    """Retourne un widget dont le ``content_widget`` peut être
    affiché/masqué.

    Cela correspond aux sections en accordéon vues dans le panneau
    latéral de l'onglet de contrôle.
    """
    wrapper = QtWidgets.QWidget()
    v = QtWidgets.QVBoxLayout(wrapper)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)

    header = QtWidgets.QToolButton()
    header.setText(title)
    header.setCheckable(True)
    header.setChecked(expanded)
    header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
    header.setStyleSheet(
        "QToolButton{ text-align: left; padding: 8px; font-weight: bold; color: #3498DB; font-size: 12px; background: transparent; border: none; }"
    )

    v.addWidget(header)
    v.addWidget(content_widget)
    content_widget.setVisible(expanded)

    def _toggle(checked):
        content_widget.setVisible(checked)
        header.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)

    header.toggled.connect(_toggle)
    return wrapper


def create_slider(min_v: int, max_v: int, current_v: int, callback) -> QtWidgets.QSlider:
    """Construit un curseur horizontal avec une plage et un callback.

    ``callback`` sera invoqué avec la nouvelle valeur entière à chaque
    mouvement du curseur.
    """
    s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    s.setMinimum(min_v)
    s.setMaximum(max_v)
    s.setValue(current_v)
    s.valueChanged.connect(callback)
    return s
