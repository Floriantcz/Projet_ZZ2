"""Widgets Qt personnalisés utilisés par l'interface modulaire.

Ce fichier contient le widget gimbal 3D, une classe de redirection
standard de console et la chaîne de feuille de style globale.
"""

import numpy as np
from PyQt5 import QtWidgets, QtCore
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
QPushButton { 
    background-color: #34495E; 
    color: white; 
    border-radius: 5px; 
    padding: 8px; 
    font-weight: bold; 
    border: 2px solid #34495E;
}
QPushButton:hover { 
    background-color: #3498DB;
    border: 2px solid #5DADE2;
}
QPushButton:pressed {
    background-color: #2980B9;
    border: 2px solid #2471A3;
}
QPushButton#Emergency { 
    background-color: #C0392B;
    border: 2px solid #C0392B;
}
QPushButton#Emergency:hover { 
    background-color: #E74C3C;
    border: 2px solid #EC7063;
}
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


class OutLog(QtCore.QObject):
    """Redirige la sortie de ``print()`` vers un QTextEdit avec
    colorisation.

    La version originale dans ``gui.py`` était monolithique ; ici elle
    est documentée et peut être réutilisée par n'importe quel widget qui
    a besoin d'une console.
    """
    
    # Signal thread-safe pour écrire dans le QTextEdit
    append_signal = pyqtSignal(str)

    def __init__(self, edit: QtWidgets.QTextEdit, out=None, color=None):
        super().__init__()
        self.edit = edit
        self.out = out
        self.color = color
        # Connecter le signal au slot
        self.append_signal.connect(self._append_text)
    
    def _append_text(self, text):
        """Slot thread-safe pour ajouter du texte au QTextEdit."""
        self.edit.append(text)
        scrollbar = self.edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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

            # Utiliser le signal au lieu d'appeler directement append
            self.append_signal.emit(formatted)

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
    """Visualisation 3D du cardan à deux axes.

    Le code de création de la géométrie original se trouve ici ; la méthode
    set_angles est la seule API publique nécessaire pour le reste de la GUI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCameraPosition(distance=18, elevation=22, azimuth=35)
        self.setBackgroundColor((10, 14, 20))

        # Constantes partagées avec set_angles
        self.LEG_H = 3.0   # hauteur des piliers
        self.LEG_S = 3.5   # écartement XZ des piliers
        lw = 0.2           # section carrée des piliers

        # Grille au sol
        grid = gl.GLGridItem()
        self.addItem(grid)

        # ── Cadre (pivot Theta) posé au sommet des piliers ──
        self.cadre_root = gl.GLMeshItem(
            meshdata=gl.MeshData.sphere(rows=10, cols=10),
            drawFaces=False, drawEdges=False
        )
        self.addItem(self.cadre_root)

        scale   = 1.5
        frame_s = 1.85 * scale
        fw      = 0.11 * scale
        color_cadre = (0.92, 0.95, 1.0, 1.0)

        for tx, tz, rw, rd in [
            ( 0,        frame_s,  frame_s * 2, fw),
            ( 0,       -frame_s,  frame_s * 2, fw),
            ( frame_s,  0,        fw, frame_s * 2),
            (-frame_s,  0,        fw, frame_s * 2),
        ]:
            box = _create_box(rw, fw, rd, color_cadre)
            box.translate(tx, 0, tz)
            box.setParentItem(self.cadre_root)

        # ── Plateau (pivot Psi, enfant du cadre) ──
        self.plateau_root = gl.GLMeshItem(
            meshdata=gl.MeshData.sphere(rows=10, cols=10),
            drawFaces=False, drawEdges=False
        )
        self.plateau_root.setParentItem(self.cadre_root)

        plate_s     = 1.50 * scale
        color_plate = (0.74, 0.58, 0.36, 1.0)
        plate = _create_box(plate_s * 2, 0.10 * scale, plate_s * 2, color_plate)
        plate.setParentItem(self.plateau_root)

        # Initialisation visuelle à angles nuls
        self.set_angles(0, 0)


    def set_angles(self, theta, psi):
        self.cadre_root.resetTransform()
        # 1. Monte le cadre exactement au sommet des piliers
        self.cadre_root.translate(0, self.LEG_H, 0)
        # 2. Couche l'ensemble horizontalement
        self.cadre_root.rotate(90, 1 , 0, 0)
        # 3. Applique la rotation Theta
        self.cadre_root.rotate(-theta, 1, 0, 0)

        self.plateau_root.resetTransform()
        
        self.plateau_root.rotate(-psi, 1, 0, 0)


    """def set_angles(self, theta, psi):
        self.cadre_root.resetTransform()
        # 1. Monte le cadre au sommet des piliers sur l'axe Z
        self.cadre_root.translate(0, 0, self.LEG_H)
        
        # 2. Applique la rotation Theta (Axe X par exemple)
        self.cadre_root.rotate(theta, 1, 0, 0)

        self.plateau_root.resetTransform()
        # 3. Applique la rotation Psi (Axe Y pour faire un cardan perpendiculaire)
        self.plateau_root.rotate(psi, 0, 1, 0)"""
