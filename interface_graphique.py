"""
Gimbal Platform – Visualisation 3D
====================================
Dépendances :
    pip install PyQt5 PyOpenGL PyOpenGL_accelerate

Lancement :
    python gimbal_3d.py
"""

import sys
import math
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QSlider, QLabel, QGroupBox, QPushButton,
    QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette
from OpenGL.GL import *
from OpenGL.GLU import *
from PyQt5.QtOpenGL import QGLWidget


# ─────────────────────────────────────────────────────────────
#  OpenGL Widget
# ─────────────────────────────────────────────────────────────

class GimbalWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Angles contrôlés par les sliders
        self.inner_angle = 0.0   # plateau MDF  ±180°  (axe X)
        self.outer_angle = 0.0   # cadre blanc  ±90°   (axe X du cadre)

        # Orbite caméra
        self.cam_theta  = 30.0   # azimut  (degrés)
        self.cam_phi    = 25.0   # élévation
        self.cam_radius = 12.0
        self.last_mouse = None

        # Animation auto
        self.anim_time  = 0.0
        self.anim_speed = 0.0   # 0 = off

        self.setMinimumSize(640, 480)
        self.setMouseTracking(True)

    # ── Init OpenGL ─────────────────────────────────────────
    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_NORMALIZE)
        glShadeModel(GL_SMOOTH)

        glClearColor(0.039, 0.055, 0.078, 1.0)   # #0a0e14

        # Lumière principale
        glLightfv(GL_LIGHT0, GL_POSITION,  [5.0, 10.0, 6.0, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,   [1.0, 1.0,  1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR,  [0.6, 0.6,  0.6, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT,   [0.1, 0.15, 0.2, 1.0])

        # Lumière de remplissage (bleue froide)
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_POSITION, [-5.0, 2.0, -4.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE,  [0.15, 0.25, 0.45, 1.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0,  0.0,  0.0,  1.0])

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    # ── Rendu principal ─────────────────────────────────────
    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        # Position caméra (orbite sphérique)
        phi   = math.radians(self.cam_phi)
        theta = math.radians(self.cam_theta)
        cx = self.cam_radius * math.cos(phi) * math.sin(theta)
        cy = self.cam_radius * math.sin(phi)
        cz = self.cam_radius * math.cos(phi) * math.cos(theta)
        gluLookAt(cx, cy + 2, cz,   0, 2, 0,   0, 1, 0)

        # Grille de sol
        self._draw_grid()

        # ── BASE FIXE (pieds + rails bas) ───────────────────
        self._draw_base()

        # ── CADRE BLANC (outerPivot) ─ rotation axe Z ───────
        glPushMatrix()
        glTranslatef(0, 2.0, 0)
        glRotatef(-self.outer_angle, 0, 0, 1)
        self._draw_outer_frame()

        # ── PLATEAU MDF (innerPivot) ─ rotation axe X ───────
        glPushMatrix()
        glRotatef(-self.inner_angle, 1, 0, 0)
        self._draw_mdf_plate()
        glPopMatrix()

        glPopMatrix()

        # Axes XYZ (indicateurs)
        self._draw_axes()

    # ── Grille ──────────────────────────────────────────────
    def _draw_grid(self):
        glDisable(GL_LIGHTING)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-10, 11):
            t = 0.12 if i == 0 else 0.05
            glColor3f(t, t * 1.5, t * 2.2)
            glVertex3f(i, 0, -10); glVertex3f(i, 0,  10)
            glVertex3f(-10, 0, i); glVertex3f( 10, 0, i)
        glEnd()
        glEnable(GL_LIGHTING)

    # ── Axes XYZ ────────────────────────────────────────────

    def _draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.5)
        orig = [0, 2.8, 0]
        glBegin(GL_LINES)
        glColor3f(1, 0.2, 0.2); glVertex3fv(orig); glVertex3f(orig[0]+1.2, orig[1], orig[2])
        glColor3f(0.2, 1, 0.4); glVertex3fv(orig); glVertex3f(orig[0], orig[1]+1.2, orig[2])
        glColor3f(0.2, 0.5, 1); glVertex3fv(orig); glVertex3f(orig[0], orig[1], orig[2]+1.2)
        glEnd()
        glEnable(GL_LIGHTING)

    # ── Base fixe ───────────────────────────────────────────
    def _draw_base(self):
        fs   = 2.25    # demi-taille du cadre
        legH = 1.4
        pw   = 0.08    # épaisseur profil



    # ── Cadre blanc (tourne ±90° axe Z) ─────────────────────
    def _draw_outer_frame(self):
        tp  = 1.8    # demi-taille du cadre supérieur
        pw  = 0.10

        # 4 rails du cadre
        self._set_color(0.94, 0.97, 1.0)
        self._draw_box( 0,  0,  tp,  tp*2, pw*1.4, pw*1.4)
        self._draw_box( 0,  0, -tp,  tp*2, pw*1.4, pw*1.4)
        self._draw_box( tp, 0,  0,   pw*1.4, pw*1.4, tp*2)
        self._draw_box(-tp, 0,  0,   pw*1.4, pw*1.4, tp*2)

        # Blocs de coin
        self._set_color(0.88, 0.92, 0.97)
        for sx, sz in [(-1,1),(1,1),(-1,-1),(1,-1)]:
            self._draw_box(sx*tp, 0, sz*tp,  0.20, 0.16, 0.20)

        # Moteur (avant, centre)
        self._set_color(0.12, 0.12, 0.14)
        self._draw_box(0, -0.18, tp+0.15,   0.28, 0.28, 0.38)

        # Poulie moteur
        self._set_color(0.15, 0.15, 0.15)
        self._draw_cylinder(0, -0.18, tp+0.36,  0.18, 0.10, 20, axis='z')

        # Axe pivot (stub horizontal)
        self._set_color(0.72, 0.80, 0.88)
        self._draw_cylinder(0, 0, 0,  0.06, tp*2, 24, axis='z')

        # Courroie (loop simplifié)
        self._set_color(0.10, 0.10, 0.10)
        self._draw_cylinder(0, -0.18, tp+0.03,  0.22, 0.08, 24, axis='z')

    # ── Plateau MDF + accéléromètre (tourne ±180° axe X) ────
    def _draw_mdf_plate(self):
        ps = 1.55   # demi-taille plateau (un peu plus petit que le cadre)

        # Plaque MDF
        self._set_color(0.76, 0.60, 0.40)
        self._draw_box(0, 0, 0,  ps*2, 0.10, ps*2)

        # Lignes de texture MDF (cannelures)
        glDisable(GL_LIGHTING)
        glLineWidth(1.0)
        glColor3f(0.60, 0.46, 0.28)
        glBegin(GL_LINES)
        for i in range(-3, 4):
            x = i * ps / 3.5
            glVertex3f(x, 0.056, -ps); glVertex3f(x, 0.056,  ps)
        glEnd()
        glEnable(GL_LIGHTING)

        # Disque support accéléromètre
        self._set_color(0.93, 0.96, 1.0)
        self._draw_cylinder(0, 0.09, 0,  0.48, 0.08, 40)

        # PCB (vert)
        self._set_color(0.08, 0.36, 0.22)
        self._draw_box(0, 0.14, 0,  0.30, 0.035, 0.20)

        # LED verte (émissive)
        glDisable(GL_LIGHTING)
        pulse = 0.7 + 0.3 * math.sin(self.anim_time * 5)
        glColor3f(0, pulse, 0.5 * pulse)
        self._draw_cylinder_raw(0.08, 0.163, 0.05,  0.022, 0.035, 8)
        glEnable(GL_LIGHTING)

        # Connecteur (rangée de pins)
        self._set_color(0.08, 0.08, 0.10)
        self._draw_box(-0.10, 0.155, 0,  0.07, 0.04, 0.18)

        # Fils (4 fils colorés)
        colors = [(0.1,0.1,0.1),(0.1,0.1,0.1),(0.7,0.1,0.1),(0.8,0.6,0.0)]
        for i, c in enumerate(colors):
            self._set_color(*c)
            ox = -0.06 + i * 0.04
            self._draw_box(ox, 0.25, -0.06,  0.012, 0.22, 0.012)

        # Poulie plateau
        self._set_color(0.12, 0.12, 0.12)
        self._draw_cylinder(0, 0, ps + 0.08,  0.22, 0.09, 24, axis='z')

    # ── Helpers géométrie ────────────────────────────────────
    def _set_color(self, r, g, b, a=1.0):
        glColor4f(r, g, b, a)

    def _draw_box(self, x, y, z, w, h, d):
        """Dessine un parallélépipède centré en (x,y,z)."""
        glPushMatrix()
        glTranslatef(x, y, z)
        glScalef(w, h, d)
        self._unit_cube()
        glPopMatrix()

    def _unit_cube(self):
        hw = 0.5
        vertices = [
            # face avant
            (-hw,-hw, hw),( hw,-hw, hw),( hw, hw, hw),(-hw, hw, hw),
            # face arrière
            (-hw,-hw,-hw),(-hw, hw,-hw),( hw, hw,-hw),( hw,-hw,-hw),
            # face gauche
            (-hw,-hw,-hw),(-hw,-hw, hw),(-hw, hw, hw),(-hw, hw,-hw),
            # face droite
            ( hw,-hw,-hw),( hw, hw,-hw),( hw, hw, hw),( hw,-hw, hw),
            # face dessus
            (-hw, hw,-hw),(-hw, hw, hw),( hw, hw, hw),( hw, hw,-hw),
            # face dessous
            (-hw,-hw,-hw),( hw,-hw,-hw),( hw,-hw, hw),(-hw,-hw, hw),
        ]
        normals = [
            (0,0,1),(0,0,-1),(-1,0,0),(1,0,0),(0,1,0),(0,-1,0)
        ]
        glBegin(GL_QUADS)
        for face in range(6):
            glNormal3fv(normals[face])
            for v in range(4):
                glVertex3fv(vertices[face*4 + v])
        glEnd()

    def _draw_cylinder(self, x, y, z, radius, height, slices, axis='y'):
        glPushMatrix()
        glTranslatef(x, y, z)
        if axis == 'x':
            glRotatef(90, 0, 1, 0)
        elif axis == 'z':
            glRotatef(90, 1, 0, 0)
        quad = gluNewQuadric()
        gluQuadricNormals(quad, GLU_SMOOTH)
        glTranslatef(0, -height/2, 0)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quad, radius, radius, height, slices, 1)
        # caps
        gluDisk(quad, 0, radius, slices, 1)
        glTranslatef(0, 0, height)
        gluDisk(quad, 0, radius, slices, 1)
        gluDeleteQuadric(quad)
        glPopMatrix()

    def _draw_cylinder_raw(self, x, y, z, radius, height, slices):
        """Cylindre sans rotation, axe Y, pour la LED."""
        glPushMatrix()
        glTranslatef(x, y, z)
        quad = gluNewQuadric()
        gluQuadricNormals(quad, GLU_SMOOTH)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quad, radius, radius, height, slices, 1)
        gluDisk(quad, 0, radius, slices, 1)
        glTranslatef(0, 0, height)
        gluDisk(quad, 0, radius, slices, 1)
        gluDeleteQuadric(quad)
        glPopMatrix()

    # ── Souris (orbite caméra) ───────────────────────────────
    def mousePressEvent(self, event):
        self.last_mouse = event.pos()

    def mouseMoveEvent(self, event):
        if self.last_mouse and event.buttons() & Qt.LeftButton:
            dx = event.x() - self.last_mouse.x()
            dy = event.y() - self.last_mouse.y()
            self.cam_theta -= dx * 0.5
            self.cam_phi    = max(-85, min(85, self.cam_phi + dy * 0.5))
            self.last_mouse = event.pos()
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.cam_radius = max(3.0, min(22.0, self.cam_radius - delta * 0.01))
        self.update()

    # ── Animation auto ───────────────────────────────────────
    def tick(self):
        if self.anim_speed > 0:
            self.anim_time += 0.016 * self.anim_speed * 0.015
            self.inner_angle = math.sin(self.anim_time * 1.3) * 160
            self.outer_angle = math.sin(self.anim_time * 0.7) * 75
        self.update()


# ─────────────────────────────────────────────────────────────
#  Panneau de contrôle (droite)
# ─────────────────────────────────────────────────────────────
class ControlPanel(QWidget):
    def __init__(self, gimbal: GimbalWidget):
        super().__init__()
        self.gimbal = gimbal
        self._build_ui()

    def _build_ui(self):
        self.setFixedWidth(280)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Titre
        title = QLabel("⚙  Gimbal Control")
        title.setFont(QFont("Courier New", 11, QFont.Bold))
        title.setStyleSheet("color:#7ecfff; letter-spacing:1px;")
        layout.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#1e3a5a;")
        layout.addWidget(sep)

        # Plateau MDF ±180°
        grp1 = self._make_group("Plateau MDF + accéléromètre", "#ff9f43")
        v1 = QVBoxLayout(grp1)

        self.lbl_inner = QLabel("0°")
        self.lbl_inner.setAlignment(Qt.AlignCenter)
        self.lbl_inner.setFont(QFont("Courier New", 16, QFont.Bold))
        self.lbl_inner.setStyleSheet("color:#ff9f43;")

        self.sld_inner = QSlider(Qt.Horizontal)
        self.sld_inner.setRange(-180, 180)
        self.sld_inner.setValue(0)
        self.sld_inner.setTickPosition(QSlider.TicksBelow)
        self.sld_inner.setTickInterval(45)
        self.sld_inner.valueChanged.connect(self._on_inner)

        bounds = QLabel("-180°                    0°                   +180°")
        bounds.setFont(QFont("Courier New", 7))
        bounds.setStyleSheet("color:#3a6a9a;")

        v1.addWidget(self.lbl_inner)
        v1.addWidget(self.sld_inner)
        v1.addWidget(bounds)
        layout.addWidget(grp1)

        # Cadre blanc ±90°
        grp2 = self._make_group("Cadre blanc (inclinaison)", "#7ecfff")
        v2 = QVBoxLayout(grp2)

        self.lbl_outer = QLabel("0°")
        self.lbl_outer.setAlignment(Qt.AlignCenter)
        self.lbl_outer.setFont(QFont("Courier New", 16, QFont.Bold))
        self.lbl_outer.setStyleSheet("color:#7ecfff;")

        self.sld_outer = QSlider(Qt.Horizontal)
        self.sld_outer.setRange(-90, 90)
        self.sld_outer.setValue(0)
        self.sld_outer.setTickPosition(QSlider.TicksBelow)
        self.sld_outer.setTickInterval(30)
        self.sld_outer.valueChanged.connect(self._on_outer)

        bounds2 = QLabel("-90°             0°             +90°")
        bounds2.setFont(QFont("Courier New", 7))
        bounds2.setStyleSheet("color:#3a6a9a;")

        v2.addWidget(self.lbl_outer)
        v2.addWidget(self.sld_outer)
        v2.addWidget(bounds2)
        layout.addWidget(grp2)

        # Animation auto
        grp3 = self._make_group("Animation automatique", "#88ff88")
        v3 = QVBoxLayout(grp3)

        self.lbl_speed = QLabel("OFF")
        self.lbl_speed.setAlignment(Qt.AlignCenter)
        self.lbl_speed.setFont(QFont("Courier New", 13, QFont.Bold))
        self.lbl_speed.setStyleSheet("color:#88ff88;")

        self.sld_speed = QSlider(Qt.Horizontal)
        self.sld_speed.setRange(0, 100)
        self.sld_speed.setValue(0)
        self.sld_speed.valueChanged.connect(self._on_speed)

        v3.addWidget(self.lbl_speed)
        v3.addWidget(self.sld_speed)
        layout.addWidget(grp3)

        # Bouton reset
        btn = QPushButton("⟳  RESET")
        btn.setFont(QFont("Courier New", 10, QFont.Bold))
        btn.setStyleSheet("""
            QPushButton {
                background:#1e3a5a; color:#7ecfff;
                border:1px solid #2a5a8a; border-radius:6px;
                padding:8px;
            }
            QPushButton:hover { background:#2a5a8a; }
            QPushButton:pressed { background:#0d2a4a; }
        """)
        btn.clicked.connect(self._reset)
        layout.addWidget(btn)

        # Info caméra
        cam_info = QLabel("🖱  Clic+glisser → orbiter\n🖱  Molette → zoom")
        cam_info.setFont(QFont("Courier New", 8))
        cam_info.setStyleSheet("color:#3a6a9a;")
        cam_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(cam_info)

        layout.addStretch()

    def _make_group(self, title, color):
        grp = QGroupBox(title)
        grp.setFont(QFont("Courier New", 8))
        grp.setStyleSheet(f"""
            QGroupBox {{
                color:{color}; border:1px solid #1e3a5a;
                border-radius:6px; margin-top:8px; padding-top:6px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; left:8px;
            }}
        """)
        return grp

    def _on_inner(self, v):
        self.gimbal.inner_angle = v
        self.lbl_inner.setText(f"{v:+d}°")
        self.gimbal.update()

    def _on_outer(self, v):
        self.gimbal.outer_angle = v
        self.lbl_outer.setText(f"{v:+d}°")
        self.gimbal.update()

    def _on_speed(self, v):
        self.gimbal.anim_speed = v
        self.lbl_speed.setText(f"{v}%" if v > 0 else "OFF")

    def _reset(self):
        self.sld_inner.setValue(0)
        self.sld_outer.setValue(0)
        self.sld_speed.setValue(0)
        self.gimbal.anim_time = 0.0


# ─────────────────────────────────────────────────────────────
#  Fenêtre principale
# ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gimbal Platform – Visualisation 3D")
        self.setMinimumSize(960, 580)

        # Palette sombre
        p = QPalette()
        p.setColor(QPalette.Window,      QColor("#0a0e14"))
        p.setColor(QPalette.WindowText,  QColor("#c8d8e8"))
        p.setColor(QPalette.Base,        QColor("#0d1520"))
        p.setColor(QPalette.Text,        QColor("#c8d8e8"))
        p.setColor(QPalette.Button,      QColor("#1e3a5a"))
        p.setColor(QPalette.ButtonText,  QColor("#7ecfff"))
        self.setPalette(p)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.gimbal = GimbalWidget()
        self.panel  = ControlPanel(self.gimbal)

        # Séparateur vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#1e3a5a;")

        layout.addWidget(self.gimbal, stretch=1)
        layout.addWidget(sep)
        layout.addWidget(self.panel)

        # Timer 60 fps
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _tick(self):
        self.gimbal.tick()
        # Sync sliders si animation auto active
        if self.gimbal.anim_speed > 0:
            self.panel.sld_inner.blockSignals(True)
            self.panel.sld_outer.blockSignals(True)
            self.panel.sld_inner.setValue(int(self.gimbal.inner_angle))
            self.panel.sld_outer.setValue(int(max(-90, min(90, self.gimbal.outer_angle))))
            self.panel.lbl_inner.setText(f"{int(self.gimbal.inner_angle):+d}°")
            self.panel.lbl_outer.setText(f"{int(self.gimbal.outer_angle):+d}°")
            self.panel.sld_inner.blockSignals(False)
            self.panel.sld_outer.blockSignals(False)


# ─────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
