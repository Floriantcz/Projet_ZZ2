"""Custom Qt widgets used by the modular GUI.

This file holds the 3‑D gimbal widget, a standard console redirection
class, and the global stylesheet string.
"""

import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal
import pyqtgraph.opengl as gl


STYLE_SHEET = """
QMainWindow { background-color: #121212; }
QTabWidget::pane { border: none; background-color: #121212; }
QTabBar::tab {
    background: #2D2D2D; color: #888; padding: 12px 30px;
    border-top-left-radius: 5px; border-top-right-radius: 5px; margin-right: 2px;
}
QTabBar::tab:selected { background: #3498DB; color: white; font-weight: bold; }
QFrame#ControlPanel { background-color: #1E1E1E; border-radius: 10px; margin: 5px; }
QLabel { color: #E0E0E0; font-family: 'Segoe UI', sans-serif; }
QLabel#Title { font-size: 14px; font-weight: bold; color: #3498DB; margin-bottom: 5px; text-transform: uppercase; }
QLabel#ValueDisplay { font-size: 32px; font-weight: bold; color: #FFFFFF; background-color: #2D2D2D; border-radius: 5px; padding: 10px; }
QPushButton { background-color: #34495E; color: white; border-radius: 5px; padding: 8px; font-weight: bold; border: None; }
QPushButton:hover { background-color: #3498DB; }
QPushButton#Emergency { background-color: #C0392B; }
QPushButton#Emergency:hover { background-color: #E74C3C; }
QProgressBar { border: 2px solid #34495E; border-radius: 5px; text-align: center; color: white; font-weight: bold; background-color: #1E1E1E; }
QProgressBar::chunk { background-color: #27AE60; width: 10px; margin: 0.5px; }
QTextEdit#Console {
    background-color: #0D1117;
    color: #58D68D;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 10pt;
    border: 2px solid #30363D;
    border-radius: 5px;
    padding: 8px;
    line-height: 1.4;
}
QTableWidget { background-color: #1E1E1E; color: white; gridline-color: #333; border: 1px solid #444; }
QHeaderView::section { background-color: #2D2D2D; color: #3498DB; padding: 5px; font-weight: bold; border: 1px solid #121212; }
QLineEdit, QDoubleSpinBox, QComboBox { background-color: #2D2D2D; color: white; border: 1px solid #34495E; padding: 5px; }
"""


class OutLog:
    """Redirect ``print()`` output into a QTextEdit with colour coding.

    The copy in the original ``gui.py`` was monolithic; here it is
    documented and could be reused by any widget that needs a console.
    """

    def __init__(self, edit: QtWidgets.QTextEdit, out=None, color=None):
        self.edit = edit
        self.out = out
        self.color = color

    def write(self, m):
        if m.strip():
            msg = m.strip()
            if msg.startswith('✅'):
                formatted = f'<span style="color: #58D68D;">{msg}</span>'
            elif msg.startswith('❌'):
                formatted = f'<span style="color: #F1948A;">{msg}</span>'
            elif msg.startswith('⚠'):
                formatted = f'<span style="color: #F8C471;">{msg}</span>'
            elif msg.startswith('🛑'):
                formatted = f'<span style="color: #EC7063; font-weight: bold;">{msg}</span>'
            elif msg.startswith('💾'):
                formatted = f'<span style="color: #85C1E9;">{msg}</span>'
            elif msg.startswith('→') or msg.startswith('||') or msg.startswith('▶'):
                formatted = f'<span style="color: #AED6F1;">{msg}</span>'
            else:
                formatted = f'<span style="color: #58D68D;">{msg}</span>'

            self.edit.append(formatted)
            scrollbar = self.edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        if self.out:
            self.out.write(m)

    def flush(self):
        if self.out:
            self.out.flush()


# ===== primitives for the 3D view =====

def _create_box(w, h, d, color):
    verts = np.array([
        [-w/2, -h/2, -d/2], [w/2, -h/2, -d/2], [w/2, h/2, -d/2], [-w/2, h/2, -d/2],
        [-w/2, -h/2,  d/2], [w/2, -h/2,  d/2], [w/2, h/2,  d/2], [-w/2, h/2,  d/2]
    ])
    faces = np.array([
        [0,1,2], [0,2,3],
        [4,5,6], [4,6,7],
        [0,1,5], [0,5,4],
        [2,3,7], [2,7,6],
        [0,3,7], [0,7,4],
        [1,2,6], [1,6,5]
    ])
    mesh = gl.MeshData(vertexes=verts, faces=faces)
    return gl.GLMeshItem(meshdata=mesh, color=color, smooth=False,
                         drawEdges=True, edgeColor=(0,0,0,0.5))


class GimbalWidget3D(gl.GLViewWidget):
    """3‑D visualization of the two‑axis gimbal.

    The original geometry creation code lives here; the set_angles method
    is the only public API needed by the rest of the GUI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCameraPosition(distance=18, elevation=22, azimuth=35)
        self.setBackgroundColor((10, 14, 20))

        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        self.addItem(grid)

        color_base = (0.76, 0.83, 0.91, 1.0)
        leg_h, leg_s, lw = 1.6, 4, 0.1
        for sx in [-1, 1]:
            for sz in [-1, 1]:
                leg = _create_box(lw, leg_h, lw, color_base)
                leg.translate(sx * leg_s, leg_h / 2, sz * leg_s)
                self.addItem(leg)

        self.cadre_root = gl.GLMeshItem(
            meshdata=gl.MeshData.sphere(rows=10, cols=10),
            drawFaces=False,
            drawEdges=False
        )
        self.addItem(self.cadre_root)

        scale = 1.5
        frame_s, fw = 1.85 * scale, 0.11 * scale
        color_cadre = (0.92, 0.95, 1.0, 1.0)
        for tx, tz, rw, rd in [
            (0, frame_s, frame_s*2, fw),
            (0, -frame_s, frame_s*2, fw),
            (frame_s, 0, fw, frame_s*2),
            (-frame_s, 0, fw, frame_s*2)
        ]:
            box = _create_box(rw, fw, rd, color_cadre)
            box.translate(tx, 0, tz)
            box.setParentItem(self.cadre_root)

        self.plateau_root = gl.GLMeshItem(
            meshdata=gl.MeshData.sphere(rows=10, cols=10),
            drawFaces=False,
            drawEdges=False
        )
        self.plateau_root.setParentItem(self.cadre_root)

        plate_s = 1.50 * scale
        color_plate = (0.74, 0.58, 0.36, 1.0)
        plate = _create_box(plate_s * 2, 0.10 * scale, plate_s * 2, color_plate)
        plate.setParentItem(self.plateau_root)

    def set_angles(self, theta: float, psi: float):
        """Update the orientation of the gimbal.

        ``theta`` rotates the outer frame, ``psi`` tilts the inner plate.
        """
        self.cadre_root.resetTransform()
        self.cadre_root.translate(0, 1.6, 0)
        self.cadre_root.rotate(90, 1, 0, 0)
        self.cadre_root.rotate(-theta, 0, 0, 1)

        self.plateau_root.resetTransform()
        self.plateau_root.rotate(-psi, 1, 0, 0)
