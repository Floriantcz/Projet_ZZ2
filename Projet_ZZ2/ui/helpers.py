"""Utility functions to build common GUI elements.

These helpers were extracted from the large ``MainWindow`` class in
``gui.py``.  They allow individual pieces of the window to be created
in isolation and tested or reused more easily.
"""

from PyQt5 import QtWidgets, QtCore


def create_section_title(text: str) -> QtWidgets.QLabel:
    """Return a stylised section header label."""
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("Title")
    return lbl


def create_labeled_widget(label_text: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Wrap ``widget`` with a small label above it.

    The original method in ``gui.py`` built a composite widget with a
    vertical layout.  We reuse the same look here so that the rest of
    the user interface can remain visually consistent.
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
    """Return a widget whose ``content_widget`` can be shown/hidden.

    This corresponds to the accordion-style sections seen in the side
    panel of the control tab.
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
    """Build a horizontal slider with range and callback.

    ``callback`` will be invoked with the new integer value whenever the
    slider moves.
    """
    s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    s.setMinimum(min_v)
    s.setMaximum(max_v)
    s.setValue(current_v)
    s.valueChanged.connect(callback)
    return s
