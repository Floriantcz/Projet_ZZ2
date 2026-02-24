#!/usr/bin/env python3
import sys
import os
import time
import json
import socket
import serial
import glob
import math
import numpy as np
from threading import Thread
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from OpenGL.GL import *
from OpenGL.GLU import *
from PyQt5.QtOpenGL import QGLWidget
import banc_morrel # ton fichier existant

# ------------------ REDIRECTION PRINT ------------------
class OutLog:
    def __init__(self, signal, out=None):
        self.signal = signal
        self.out = out

    def write(self, m):
        if m.strip():
            self.signal.emit(m.strip())
        if self.out:
            self.out.write(m)

    def flush(self):
        if self.out:
            self.out.flush()

# ========================================================================
#  PRIMITIVES 3D
# ========================================================================

def draw_box(w, h, d):
    """Boîte centrée à l'origine, dimensions w x h x d."""
    x, y, z = w / 2, h / 2, d / 2
    faces = [
        ((0, 0,  1), [(-x,-y, z),( x,-y, z),( x, y, z),(-x, y, z)]),
        ((0, 0, -1), [( x,-y,-z),(-x,-y,-z),(-x, y,-z),( x, y,-z)]),
        ((-1,0,  0), [(-x,-y,-z),(-x,-y, z),(-x, y, z),(-x, y,-z)]),
        (( 1,0,  0), [( x,-y, z),( x,-y,-z),( x, y,-z),( x, y, z)]),
        ((0, 1,  0), [(-x, y, z),( x, y, z),( x, y,-z),(-x, y,-z)]),
        ((0,-1,  0), [( x,-y, z),(-x,-y, z),(-x,-y,-z),( x,-y,-z)]),
    ]
    glBegin(GL_QUADS)
    for normal, verts in faces:
        glNormal3fv(normal)
        for v in verts:
            glVertex3fv(v)
    glEnd()


def draw_cylinder(radius, height, slices=24):
    """Cylindre axe Y, centré à l'origine."""
    q = gluNewQuadric()
    gluQuadricNormals(q, GLU_SMOOTH)
    glPushMatrix()
    glTranslatef(0, -height / 2, 0)
    glRotatef(-90, 1, 0, 0)
    gluCylinder(q, radius, radius, height, slices, 1)
    gluDisk(q, 0, radius, slices, 1)
    glTranslatef(0, 0, height)
    gluDisk(q, 0, radius, slices, 1)
    gluDeleteQuadric(q)
    glPopMatrix()


def set_color(r, g, b):
    glColor3f(r, g, b)


# ========================================================================
#  WIDGET 3D GIMBAL (OpenGL) - Avec PSI et THETA corrigés
# ========================================================================

class GimbalWidget3D(QGLWidget):
    """Widget OpenGL pour afficher le gimbal en 3D temps réel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # CORRECTION : PSI = plateau, THETA = cadre
        self.psi_angle   = 0.0   # plateau MDF ±180° (axe X) - PSI
        self.theta_angle = 0.0   # cadre blanc ±90°  (axe Z) - THETA

        self.cam_theta   = 35.0
        self.cam_phi     = 22.0
        self.cam_radius  = 13.0
        self._last_mouse = None

        self.setMinimumSize(400, 400)

    # ── Init OpenGL ──────────────────────────────────────────────────────────
    def initializeGL(self):
        glClearColor(0.04, 0.055, 0.08, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_NORMALIZE)
        glShadeModel(GL_SMOOTH)

        glLightfv(GL_LIGHT0, GL_POSITION, [6.0, 12.0, 7.0, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.0,  1.0,  1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5,  0.5,  0.5, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.08, 0.12, 0.18, 1.0])

        glLightfv(GL_LIGHT1, GL_POSITION, [-6.0, 3.0, -5.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE,  [0.12, 0.22, 0.40, 1.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0,  0.0,  0.0,  1.0])

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    # ── Rendu ────────────────────────────────────────────────────────────────
    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        ph = math.radians(self.cam_phi)
        th = math.radians(self.cam_theta)
        cx = self.cam_radius * math.cos(ph) * math.sin(th)
        cy = self.cam_radius * math.sin(ph)
        cz = self.cam_radius * math.cos(ph) * math.cos(th)
        gluLookAt(cx, cy + 2.5, cz,   0, 2.5, 0,   0, 1, 0)

        self._draw_grid()
        self._draw_base()
        self._draw_gimbal()
        self._draw_axes()

    # ── Grille ───────────────────────────────────────────────────────────────
    def _draw_grid(self):
        glDisable(GL_LIGHTING)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-8, 9):
            c = 0.15 if i == 0 else 0.06
            glColor3f(c * 0.55, c, c * 1.6)
            glVertex3f(i, 0, -8); glVertex3f(i,  0,  8)
            glVertex3f(-8, 0, i); glVertex3f( 8,  0,  i)
        glEnd()
        glEnable(GL_LIGHTING)

    # ── Axes XYZ ─────────────────────────────────────────────────────────────
    def _draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.5)
        ox, oy, oz = 0, 3.4, 0
        L = 1.1
        glBegin(GL_LINES)
        glColor3f(1.0, 0.25, 0.25); glVertex3f(ox, oy, oz); glVertex3f(ox+L, oy,   oz)
        glColor3f(0.25, 1.0, 0.45); glVertex3f(ox, oy, oz); glVertex3f(ox,   oy+L, oz)
        glColor3f(0.25, 0.55, 1.0); glVertex3f(ox, oy, oz); glVertex3f(ox,   oy,   oz+L)
        glEnd()
        glEnable(GL_LIGHTING)

    # ── Base fixe (pieds + rails) ─────────────────────────────────────────────
    def _draw_base(self):
        leg_h = 1.6
        leg_s = 4
        lw    = 0.1

        for sx, sz in ((-1,1),(1,1),(-1,-1),(1,-1)):
            px, pz = sx * leg_s, sz * leg_s

            glPushMatrix()
            glTranslatef(px, leg_h / 2, pz)
            set_color(0.88, 0.92, 0.96)
            draw_box(lw, leg_h, lw)
            glPopMatrix()

            glPushMatrix()
            glTranslatef(px, 0.04, pz)
            set_color(0.80, 0.85, 0.90)
            draw_box(0.26, 0.08, 0.26)
            glPopMatrix()

            glPushMatrix()
            glTranslatef(px, 0.11, pz)
            set_color(0.58, 0.68, 0.78)
            draw_cylinder(0.038, 0.09, 8)
            glPopMatrix()

        span = leg_s * 2
        for tx, tz, rw, rd in [
            ( 0,        leg_s,  span, lw),
            ( 0,       -leg_s,  span, lw),
            ( leg_s,    0,      lw,   span),
            (-leg_s,    0,      lw,   span),
        ]:
            glPushMatrix()
            glTranslatef(tx, leg_h, tz)
            set_color(0.76, 0.83, 0.91)
            draw_box(rw, lw * 1.2, rd)
            glPopMatrix()

    # ── Gimbal (cadre + plateau) ──────────────────────────────────────────────
    def _draw_gimbal(self):
        leg_h = 1.6
        
        # Échelle globale 1.5x pour meilleure visibilité
        scale   = 1.5
        frame_s = 1.85 * scale
        fw      = 0.11 * scale
        plate_s = 1.50 * scale

        # ── Cadre blanc (tourne axe Z) — THETA ────────────────────────────────
        glPushMatrix()
        glTranslatef(0, leg_h, 0)
        glRotatef(-self.theta_angle, 0, 0, 1)  # THETA contrôle le cadre

        for tx, tz, rw, rd in [
            ( 0,        frame_s,  frame_s*2, fw),
            ( 0,       -frame_s,  frame_s*2, fw),
            ( frame_s,  0,        fw, frame_s*2),
            (-frame_s,  0,        fw, frame_s*2),
        ]:
            glPushMatrix()
            glTranslatef(tx, 0, tz)
            set_color(0.92, 0.95, 1.0)
            draw_box(rw, fw, rd)
            glPopMatrix()

        for sx, sz in ((-1,1),(1,1),(-1,-1),(1,-1)):
            glPushMatrix()
            glTranslatef(sx * frame_s, 0, sz * frame_s)
            set_color(0.84, 0.88, 0.94)
            draw_box(0.20 * scale, 0.17 * scale, 0.20 * scale)
            glPopMatrix()

        glPushMatrix()
        glTranslatef(0, -0.19 * scale, frame_s + 0.16 * scale)
        set_color(0.14, 0.14, 0.16)
        draw_box(0.27 * scale, 0.27 * scale, 0.40 * scale)
        glTranslatef(0, 0, 0.24 * scale)
        set_color(0.55, 0.63, 0.72)
        draw_cylinder(0.038 * scale, 0.16 * scale, 12)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(0, -0.19 * scale, frame_s + 0.04 * scale)
        set_color(0.10, 0.10, 0.10)
        glRotatef(90, 1, 0, 0)
        draw_cylinder(0.19 * scale, 0.095 * scale, 24)
        glPopMatrix()

        # ── Plateau MDF (tourne axe X) — PSI ──────────────────────────────────
        glPushMatrix()
        glRotatef(-self.psi_angle, 1, 0, 0)  # PSI contrôle le plateau

        glPushMatrix()
        set_color(0.74, 0.58, 0.36)
        draw_box(plate_s * 2, 0.10 * scale, plate_s * 2)
        glPopMatrix()

        glDisable(GL_LIGHTING)
        glLineWidth(1.0)
        glColor3f(0.57, 0.42, 0.24)
        step = plate_s / 3.5
        glBegin(GL_LINES)
        for i in range(-3, 4):
            x = i * step
            glVertex3f(x, 0.052 * scale, -plate_s)
            glVertex3f(x, 0.052 * scale,  plate_s)
        glEnd()
        glEnable(GL_LIGHTING)

        glPushMatrix()
        glTranslatef(0, 0, plate_s + 0.06 * scale)
        set_color(0.10, 0.10, 0.10)
        glRotatef(90, 1, 0, 0)
        draw_cylinder(0.20 * scale, 0.088 * scale, 24)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(0, 0.09 * scale, 0)
        set_color(0.92, 0.95, 1.0)
        draw_cylinder(0.45 * scale, 0.076 * scale, 36)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(0, 0.144 * scale, 0)
        set_color(0.07, 0.33, 0.17)
        draw_box(0.27 * scale, 0.030 * scale, 0.18 * scale)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(-0.095 * scale, 0.153 * scale, 0)
        set_color(0.08, 0.08, 0.10)
        draw_box(0.060 * scale, 0.036 * scale, 0.15 * scale)
        glPopMatrix()

        glDisable(GL_LIGHTING)
        pulse = 0.7 + 0.3 * math.sin(time.time() * 5.0)
        glColor3f(0.0, pulse, 0.42 * pulse)
        glPushMatrix()
        glTranslatef(0.075 * scale, 0.163 * scale, 0.048 * scale)
        draw_cylinder(0.018 * scale, 0.030 * scale, 8)
        glPopMatrix()
        glEnable(GL_LIGHTING)

        wire_colors = [
            (0.10, 0.10, 0.10),
            (0.10, 0.10, 0.10),
            (0.72, 0.10, 0.08),
            (0.78, 0.63, 0.06),
        ]
        for i, wc in enumerate(wire_colors):
            glPushMatrix()
            glTranslatef((-0.052 + i * 0.036) * scale, 0.255 * scale, -0.048 * scale)
            set_color(*wc)
            draw_box(0.009 * scale, 0.20 * scale, 0.009 * scale)
            glPopMatrix()

        glPopMatrix()  # fin plateau (PSI)
        glPopMatrix()  # fin cadre (THETA)

    # ── Souris ───────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._last_mouse = e.pos()

    def mouseMoveEvent(self, e):
        if self._last_mouse and (e.buttons() & QtCore.Qt.LeftButton):
            dx = e.x() - self._last_mouse.x()
            dy = e.y() - self._last_mouse.y()
            self.cam_theta -= dx * 0.45
            self.cam_phi    = max(-80, min(80, self.cam_phi + dy * 0.45))
            self._last_mouse = e.pos()
            self.update()

    def wheelEvent(self, e):
        self.cam_radius = max(3.0, min(22.0, self.cam_radius - e.angleDelta().y() * 0.01))
        self.update()

    def set_angles(self, theta, psi):
        """
        Mise à jour des angles depuis l'extérieur.
        IMPORTANT: theta contrôle le cadre, psi contrôle le plateau
        """
        self.theta_angle = theta  # THETA = cadre blanc
        self.psi_angle   = psi    # PSI = plateau MDF
        self.update()


#---------------- STYLE ------------------
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

QProgressBar {
    border: 2px solid #34495E; border-radius: 5px; text-align: center; color: white; font-weight: bold; background-color: #1E1E1E;
}
QProgressBar::chunk { background-color: #27AE60; width: 10px; margin: 0.5px; }

QTextEdit#Console {
    background-color: #0A0A0A; color: #00FF00; font-family: 'Consolas', monospace; font-size: 11px; border: 1px solid #333;
}
"""

# ------------------ MAIN WINDOW ------------------
class MainWindow(QtWidgets.QMainWindow):
   
    update_sphere_signal = pyqtSignal(np.ndarray)
    log_signal = pyqtSignal(str)

    def __init__(self, sock, ser):
        super().__init__()

        self.update_sphere_signal.connect(self.update_sphere)
        self.log_signal.connect(self._append_log)

        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center Pro - Banc Accéléromètre")
        self.resize(1600, 950)
        self.setStyleSheet(STYLE_SHEET)

        self.time_data, self.theta_data, self.psi_data = [], [], []
        self.start_time = time.time()

        # Layout global
        layout_global = QtWidgets.QVBoxLayout()
        container_global = QtWidgets.QWidget()
        container_global.setLayout(layout_global)
        self.setCentralWidget(container_global)

        self.tabs = QtWidgets.QTabWidget()
        layout_global.addWidget(self.tabs, stretch=4)

        # Console
        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setObjectName("Console")
        self.console_log.setReadOnly(True)
        layout_global.addWidget(self.create_section_title("📋 Console Système"))
        layout_global.addWidget(self.console_log, stretch=1)
        self.console_log.setMinimumHeight(120)
        self.console_log.setMaximumHeight(250)

        # Rediriger stdout
        sys.stdout = OutLog(self.log_signal, sys.stdout)

        # Initialisation onglets
        self.init_control_tab()
        self.init_editor_tab()

        # Timer UI
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    # ------------------ TAB CONTROL ------------------
    def init_control_tab(self):
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

        # ------------------ GAUCHE : Graphique + 3D Gimbal ------------------
        graph_side = QtWidgets.QVBoxLayout()

        # Affichage Theta / Psi en haut
        header_layout = QtWidgets.QHBoxLayout()
        self.lbl_theta_val = QtWidgets.QLabel("0.0°")
        self.lbl_theta_val.setObjectName("ValueDisplay")
        self.lbl_theta_val.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_psi_val = QtWidgets.QLabel("0.0°")
        self.lbl_psi_val.setObjectName("ValueDisplay")
        self.lbl_psi_val.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(self.create_labeled_widget("THETA (Θ) - CADRE", self.lbl_theta_val))
        header_layout.addWidget(self.create_labeled_widget("PSI (Ψ) - PLATEAU", self.lbl_psi_val))
        graph_side.addLayout(header_layout)

        # Layout horizontal pour graphique + vue 3D côte à côte
        viz_layout = QtWidgets.QHBoxLayout()

        # Plot PyQtGraph
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2), name='Theta')
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2), name='Psi')
        self.plot_widget.addLegend()
        viz_layout.addWidget(self.plot_widget, stretch=1)

        # Vue 3D du Gimbal
        gimbal_container = QtWidgets.QVBoxLayout()
        
        self.gimbal_3d = GimbalWidget3D()
        gimbal_container.addWidget(self.gimbal_3d)
        
        gimbal_widget = QtWidgets.QWidget()
        gimbal_widget.setLayout(gimbal_container)
        viz_layout.addWidget(gimbal_widget, stretch=1)

        graph_side.addLayout(viz_layout)

        # Barre de progression
        graph_side.addWidget(self.create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)

        # Sphere 3D (calibration)
        graph_side.addWidget(self.create_section_title("🌐 Sphère de Calibration"))
        self.sphere_widget = gl.GLViewWidget()
        self.sphere_widget.setCameraPosition(distance=400)
        self.sphere_item = gl.GLMeshItem(meshdata=gl.MeshData.sphere(rows=20, cols=20),
                                         smooth=True, color=(0.2, 0.6, 1, 0.5),
                                         shader='shaded', drawEdges=True)
        self.sphere_widget.addItem(self.sphere_item)
        self.sphere_widget.setMaximumHeight(300)
        graph_side.addWidget(self.sphere_widget)

        main_layout.addLayout(graph_side, stretch=3)

        # ------------------ DROITE : Commandes + Calibration ------------------
        side_panel = QtWidgets.QFrame()
        side_panel.setObjectName("ControlPanel")
        side_panel.setFixedWidth(360)
        side_layout = QtWidgets.QVBoxLayout(side_panel)

        # ----- Séquences de Scan -----
        side_layout.addWidget(self.create_section_title("Séquences de Scan"))
        btn_perso = QtWidgets.QPushButton("🚀 LANCER SCAN PERSO")
        btn_perso.setStyleSheet("background-color: #27AE60; margin-bottom: 5px;")
        btn_perso.clicked.connect(lambda: self.launch_scan("config_custom.json"))
        side_layout.addWidget(btn_perso)

        for mode, config in [("Standard", "config_standard.json"), 
                            ("Rapide", "config_rapide.json"), 
                            ("Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(f"Lancer {mode}")
            btn.clicked.connect(lambda chk, c=config: self.launch_scan(c))
            side_layout.addWidget(btn)

        side_layout.addSpacing(15)

        # ----- Réglages PID -----
        side_layout.addWidget(self.create_section_title("Réglages PID"))
        self.kp_label = QtWidgets.QLabel(f"Gain KP: {banc_morrel.KP}")
        side_layout.addWidget(self.kp_label)
        side_layout.addWidget(self.create_slider(1, 100, int(banc_morrel.KP * 10), self.update_kp))

        self.speed_label = QtWidgets.QLabel(f"Vitesse Max: {banc_morrel.MAX_SPEED}")
        side_layout.addWidget(self.speed_label)
        side_layout.addWidget(self.create_slider(1, 100, banc_morrel.MAX_SPEED, self.update_max_speed))

        side_layout.addSpacing(15)

        # ----- Contrôle d'exécution -----
        side_layout.addWidget(self.create_section_title("Contrôle Exécution"))
        self.btn_pause = QtWidgets.QPushButton("⏸ PAUSE")
        self.btn_pause.clicked.connect(self.action_pause)
        side_layout.addWidget(self.btn_pause)

        self.btn_resume = QtWidgets.QPushButton("▶ REPRISE")
        self.btn_resume.clicked.connect(self.action_resume)
        side_layout.addWidget(self.btn_resume)

        side_layout.addSpacing(15)

        # ----- Arrêt d'urgence -----
        self.emergency_btn = QtWidgets.QPushButton("ARRÊT D'URGENCE")
        self.emergency_btn.setObjectName("Emergency")
        self.emergency_btn.setFixedHeight(60)
        self.emergency_btn.clicked.connect(self.action_emergency)
        side_layout.addWidget(self.emergency_btn)

        side_layout.addSpacing(15)

        # ----- Calibration Accéléromètre -----
        side_layout.addWidget(self.create_section_title("Calibration Accéléromètre"))
        self.btn_calibrate = QtWidgets.QPushButton("🧪 CALIBRER ACCÉLÉROMÈTRE")
        self.btn_calibrate.clicked.connect(self.run_calibration)
        side_layout.addWidget(self.btn_calibrate)

        # Affichage des coefficients
        self.lbl_bias = QtWidgets.QLabel("Bias b: [0,0,0]")
        self.lbl_A1 = QtWidgets.QLabel("Matrice A⁻¹: identité")
        side_layout.addWidget(self.lbl_bias)
        side_layout.addWidget(self.lbl_A1)

        side_layout.addStretch()
        main_layout.addWidget(side_panel)

        # Ajouter l'onglet
        self.tabs.addTab(control_widget, "📊 LIVE MONITORING")

    # ------------------ TAB CONFIG EDITOR ------------------
    def init_editor_tab(self):
        editor_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(editor_widget)

        self.table = QtWidgets.QTableWidget(0,2)
        self.table.setHorizontalHeaderLabels(["Theta (°)", "Psi (ex: 180,90,0)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        add_frame = QtWidgets.QFrame()
        add_frame.setObjectName("ControlPanel")
        add_lyt = QtWidgets.QHBoxLayout(add_frame)
        self.in_theta = QtWidgets.QDoubleSpinBox(); self.in_theta.setRange(-90,90)
        self.in_psi = QtWidgets.QLineEdit(); self.in_psi.setPlaceholderText("180, 90, 0...")
        btn_add = QtWidgets.QPushButton("➕ AJOUTER"); btn_add.clicked.connect(self.add_row_to_config)
        add_lyt.addWidget(QtWidgets.QLabel("Theta:")); add_lyt.addWidget(self.in_theta)
        add_lyt.addWidget(QtWidgets.QLabel("Psi:")); add_lyt.addWidget(self.in_psi); add_lyt.addWidget(btn_add)
        layout.addWidget(add_frame)

        btn_save = QtWidgets.QPushButton("💾 ENREGISTRER CONFIGURATION")
        btn_save.clicked.connect(self.save_custom_config)
        layout.addWidget(btn_save)

        self.tabs.addTab(editor_widget, "📝 CONFIG EDITOR")

    # ------------------ UPDATE SPHERE ------------------
    def update_sphere(self, calibrated):
        """Affiche les points calibrés dans la vue 3D."""
        if calibrated is None:
            return

        try:
            pts = np.asarray(calibrated)
            if np.iscomplexobj(pts):
                pts = np.real(pts)
            if pts.ndim != 2 or pts.shape[1] != 3:
                print("⚠️ Format des points invalide pour la sphère:", pts.shape)
                return

            mask = np.isfinite(pts).all(axis=1)
            pts = pts[mask]

            if pts.size == 0:
                print("⚠️ Aucun point valide pour affichage")
                return

            pts = pts.astype(np.float32)

            for item in list(self.sphere_widget.items):
                if isinstance(item, gl.GLScatterPlotItem):
                    self.sphere_widget.removeItem(item)

            scatter = gl.GLScatterPlotItem(
                pos=pts,
                size=5,
                color=(1, 0.5, 0, 1),
                pxMode=True
            )
            self.sphere_widget.addItem(scatter)
            self.sphere_widget.update()

            center = pts.mean(axis=0)
            self.sphere_widget.opts['center'] = pg.Vector(center[0], center[1], center[2])

            print(f"✅ {len(pts)} points affichés sur la sphère")

        except Exception as e:
            print(f"❌ Erreur update_sphere: {e}")

    def _append_log(self, text):
        """Ajout thread-safe dans la console Qt."""
        self.console_log.append(text)

    # ------------------ UTILITAIRES ------------------
    def create_section_title(self, text):
        lbl = QtWidgets.QLabel(text); lbl.setObjectName("Title"); return lbl

    def create_labeled_widget(self, label_text, widget):
        c = QtWidgets.QVBoxLayout(); lbl = QtWidgets.QLabel(label_text)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setStyleSheet("font-size:10px;color:#7F8C8D;")
        c.addWidget(lbl); c.addWidget(widget)
        w = QtWidgets.QWidget(); w.setLayout(c); return w

    def create_slider(self, min_v, max_v, current_v, callback):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setMinimum(min_v); s.setMaximum(max_v); s.setValue(current_v)
        s.valueChanged.connect(callback)
        return s

    def add_row_to_config(self):
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row,0,QtWidgets.QTableWidgetItem(str(self.in_theta.value())))
        self.table.setItem(row,1,QtWidgets.QTableWidgetItem(self.in_psi.text()))

    def save_custom_config(self):
        seq = []
        for i in range(self.table.rowCount()):
            try:
                t = float(self.table.item(i,0).text())
                p = [float(x.strip()) for x in self.table.item(i,1).text().split(",") if x.strip()]
                seq.append({"theta": t, "psi_positions": p})
            except: continue
        with open("config_custom.json","w") as f: json.dump({"sequence":seq},f,indent=2)
        print("✅ Configuration personnalisée enregistrée.")

    # ------------------ CALIBRATION ------------------
    def run_calibration(self):
        files = glob.glob("scan_*.csv")
        if not files:
            print("❌ Aucun fichier CSV trouvé")
            return
        latest_file = max(files, key=lambda f: os.path.getmtime(f))
        print(f"🔹 Calibration à partir de {latest_file}")

        def qt_callback(raw, calibrated):
            try:
                self.update_sphere_signal.emit(np.array(calibrated))
            except Exception as e:
                print("Callback error:", e)

        from accelerometer_calib import Accelerometer
        acc = Accelerometer(latest_file, qt_callback=qt_callback)
        Thread(target=lambda: self._calibrate_thread(acc), daemon=True).start()

    def _calibrate_thread(self, acc):
        acc.run()
        bias_str = np.array2string(np.round(acc.b.flatten(),4))
        A1_str = np.array2string(np.round(acc.A_1,4))
        QtCore.QMetaObject.invokeMethod(
            self.lbl_bias, "setText", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, f"Bias b: {bias_str}")
        )
        QtCore.QMetaObject.invokeMethod(
            self.lbl_A1, "setText", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, f"A⁻¹:\n{A1_str}")
        )
        print("✅ Calibration terminée.")

    # ------------------ CALLBACKS ------------------
    def update_kp(self, val):
        banc_morrel.KP = val/10.0
        self.kp_label.setText(f"Gain KP: {banc_morrel.KP:.1f}")

    def update_max_speed(self, val):
        banc_morrel.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_pause(self):
        banc_morrel.pause_system()

    def action_resume(self):
        banc_morrel.resume_system()

    def action_emergency(self):
        banc_morrel.emergency_stop(self.ser)

    def launch_scan(self, config):
        if not os.path.exists(config): return
        banc_morrel.running = True
        self.pbar.setValue(0)
        Thread(
            target=lambda: banc_morrel.run_sequence(
                config,
                self.ser,
                progress_callback=lambda p: QtCore.QMetaObject.invokeMethod(
                    self.pbar, "setValue", QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(int, p)
                )
            ),
            daemon=True
        ).start()

    # ------------------ UPDATE UI ------------------
    def update_ui(self):
        with banc_morrel.accel_lock:
            theta = banc_morrel.latest_theta
            psi = banc_morrel.latest_psi

        if theta is not None and psi is not None:
            self.lbl_theta_val.setText(f"{theta:+.1f}°")
            self.lbl_psi_val.setText(f"{psi:+.1f}°")
            
            # Mise à jour de la vue 3D du gimbal
            # IMPORTANT: on passe theta et psi dans le bon ordre
            self.gimbal_3d.set_angles(theta, psi)
            
            now_time = time.time() - self.start_time
            self.time_data.append(now_time)
            self.theta_data.append(theta)
            self.psi_data.append(psi)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

            # Sphere rotation
            self.sphere_item.resetTransform()
            self.sphere_item.rotate(theta, 1, 0, 0)
            self.sphere_item.rotate(psi, 0, 1, 0)

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((banc_morrel.HOST, banc_morrel.PORT))
        ser = serial.Serial(banc_morrel.SERIAL_PORT, banc_morrel.BAUDRATE, timeout=1)
        Thread(target=banc_morrel.accel_reader, args=(sock,), daemon=True).start()
        win = MainWindow(sock, ser)
        win.show()

        sys.exit(app.exec_())
    except Exception as e:
        print(f"Erreur connexion : {e}")