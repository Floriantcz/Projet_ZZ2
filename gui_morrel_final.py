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
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import pyqtSignal
import pyqtgraph as pg
import pyqtgraph.opengl as gl

import banc_Morrel  # Assure-toi que l'orthographe correspond bien à ton fichier

# ========================================================================
#  REDIRECTION PRINT (CONSOLE QSS)
# ========================================================================
class OutLog:
    def __init__(self, edit, out=None, color=None):
        self.edit = edit
        self.out = out
        self.color = color

    def write(self, m):
        if m.strip():
            self.edit.append(m.strip())
        if self.out:
            self.out.write(m)

    def flush(self):
        if self.out:
            self.out.flush()

# ========================================================================
#  PRIMITIVES 3D PYQTGRAPH (Remplacement du code du binôme)
# ========================================================================
def create_box(w, h, d, color):
    """Crée une boîte 3D compatible avec pyqtgraph au lieu du vieux OpenGL"""
    verts = np.array([
        [-w/2, -h/2, -d/2], [w/2, -h/2, -d/2], [w/2, h/2, -d/2], [-w/2, h/2, -d/2],
        [-w/2, -h/2,  d/2], [w/2, -h/2,  d/2], [w/2, h/2,  d/2], [-w/2, h/2,  d/2]
    ])
    faces = np.array([
        [0,1,2], [0,2,3], # bas
        [4,5,6], [4,6,7], # haut
        [0,1,5], [0,5,4], # avant
        [2,3,7], [2,7,6], # arriere
        [0,3,7], [0,7,4], # gauche
        [1,2,6], [1,6,5]  # droite
    ])
    mesh = gl.MeshData(vertexes=verts, faces=faces)
    # On ajoute des bords noirs pour bien voir les formes sans avoir besoin de shaders complexes
    return gl.GLMeshItem(meshdata=mesh, color=color, smooth=False, drawEdges=True, edgeColor=(0,0,0,0.5))

# ========================================================================
#  WIDGET 3D GIMBAL (Version PyQtGraph unifiée)
# ========================================================================
class GimbalWidget3D(gl.GLViewWidget):
    """Gimbal 3D réécrit proprement en pyqtgraph pour éviter les crashs de contexte"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCameraPosition(distance=18, elevation=22, azimuth=35)
        self.setBackgroundColor((10, 14, 20)) # Fond sombre
        
        # 1. --- La Base (Fixe) ---
        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        self.addItem(grid)
        
        color_base = (0.76, 0.83, 0.91, 1.0)
        leg_h, leg_s, lw = 1.6, 4, 0.1
        
        # Pieds de la base
        for sx in [-1, 1]:
            for sz in [-1, 1]:
                leg = create_box(lw, leg_h, lw, color_base)
                leg.translate(sx * leg_s, leg_h / 2, sz * leg_s)
                self.addItem(leg)

        # 2. --- Le Cadre (THETA : Tourne autour de l'axe Z) ---
        # On crée un nœud invisible qui va servir de pivot
        self.cadre_root = gl.GLMeshItem(meshdata=gl.MeshData.sphere(rows=10, cols=10), drawFaces=False, drawEdges=False)
        self.addItem(self.cadre_root)
        
        scale = 1.5
        frame_s, fw = 1.85 * scale, 0.11 * scale
        color_cadre = (0.92, 0.95, 1.0, 1.0)
        
        # On attache les 4 côtés du cadre au nœud pivot
        for tx, tz, rw, rd in [(0, frame_s, frame_s*2, fw), (0, -frame_s, frame_s*2, fw), (frame_s, 0, fw, frame_s*2), (-frame_s, 0, fw, frame_s*2)]:
            box = create_box(rw, fw, rd, color_cadre)
            box.translate(tx, 0, tz)
            box.setParentItem(self.cadre_root)

        # 3. --- Le Plateau (PSI : Tourne autour de l'axe X par rapport au Cadre) ---
        self.plateau_root = gl.GLMeshItem(meshdata=gl.MeshData.sphere(rows=10, cols=10), drawFaces=False, drawEdges=False)
        self.plateau_root.setParentItem(self.cadre_root) # Le plateau est enfant du cadre !
        
        plate_s = 1.50 * scale
        color_plate = (0.74, 0.58, 0.36, 1.0) # Couleur MDF (Bois)
        plate = create_box(plate_s * 2, 0.10 * scale, plate_s * 2, color_plate)
        plate.setParentItem(self.plateau_root)

    def set_angles(self, theta, psi):
        """Met à jour les rotations via les matrices de transformation internes"""
        # Theta tourne le cadre
    # Theta tourne le cadre
        self.cadre_root.resetTransform()
        self.cadre_root.translate(0, 1.6, 0)
        # On couche le banc de 90° autour de l'axe X pour qu'il soit horizontal de base
        self.cadre_root.rotate(90, 1, 0, 0) 
        # Ensuite on applique la rotation Theta sur le nouvel axe Z local
        self.cadre_root.rotate(-theta, 0, 0, 1)
        # Psi tourne le plateau
        self.plateau_root.resetTransform()
        self.plateau_root.rotate(-psi, 1, 0, 0) # Axe X

# ========================================================================
#  STYLESHEET (QSS)
# ========================================================================
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

QTableWidget { background-color: #1E1E1E; color: white; gridline-color: #333; border: 1px solid #444; }
QHeaderView::section { background-color: #2D2D2D; color: #3498DB; padding: 5px; font-weight: bold; border: 1px solid #121212; }
QLineEdit, QDoubleSpinBox, QComboBox { background-color: #2D2D2D; color: white; border: 1px solid #34495E; padding: 5px; }
"""

# ========================================================================
#  MAIN WINDOW
# ========================================================================
class MainWindow(QtWidgets.QMainWindow):
    update_sphere_signal = pyqtSignal(np.ndarray)

    def __init__(self, sock, ser):
        super().__init__()
        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center Pro - Banc Accéléromètre")
        self.resize(1600, 950)
        self.setStyleSheet(STYLE_SHEET)

        self.time_data, self.theta_data, self.psi_data = [], [], []
        self.start_time = time.time()

        # Layout Principal Vertical
        layout_global = QtWidgets.QVBoxLayout()
        container_global = QtWidgets.QWidget()
        container_global.setLayout(layout_global)
        self.setCentralWidget(container_global)

        self.tabs = QtWidgets.QTabWidget()
        layout_global.addWidget(self.tabs, stretch=4)

        # Ajout de la Console de Log en bas
        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setObjectName("Console")
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(100)
        self.console_log.setMaximumHeight(200)

        layout_global.addWidget(self.create_section_title("📋 Console Système"))
        layout_global.addWidget(self.console_log, stretch=1)

        # Redirection du stdout
        sys.stdout = OutLog(self.console_log, sys.stdout)

        # Initialisation des onglets
        self.init_control_tab()
        self.init_editor_tab()
        self.init_calibration_tab()

        # Connexion des signaux
        self.update_sphere_signal.connect(self.update_sphere)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    # ------------------ ONGLETS ------------------
    def init_control_tab(self):  
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

        # ====== GAUCHE : VISUALISATION (Courbes + 3D) ======
        graph_side = QtWidgets.QVBoxLayout()
        
        # Affichage digital des angles
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

        # Visualisation Temps Réel (Graphique + Gimbal 3D côte à côte)
        viz_layout = QtWidgets.QHBoxLayout()
        
        # Plot 2D
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2), name="Theta (θ)")
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2), name="Psi (ψ)")
        viz_layout.addWidget(self.plot_widget, stretch=1)

        # Nouveau Gimbal 3D (Unifié sous PyQtGraph)
        self.gimbal_3d = GimbalWidget3D()
        viz_layout.addWidget(self.gimbal_3d, stretch=1)
        
        graph_side.addLayout(viz_layout, stretch=2)

        # Barre de progression
        graph_side.addWidget(self.create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)

        # Sphere 3D (RETOUR DE LA SPHERE DE CALIBRATION)
        graph_side.addWidget(self.create_section_title("🌐 Sphère de Calibration"))
        self.sphere_widget = gl.GLViewWidget()
        self.sphere_widget.setCameraPosition(distance=400)
        # On utilise le shader par défaut pour être 100% sûr de la compatibilité Asus/Mesa
        self.sphere_item = gl.GLMeshItem(meshdata=gl.MeshData.sphere(rows=15, cols=15),
                                         smooth=True, color=(0.2, 0.6, 1, 0.3),
                                         drawEdges=True)
        self.sphere_widget.addItem(self.sphere_item)
        self.sphere_widget.setMaximumHeight(250)
        graph_side.addWidget(self.sphere_widget, stretch=1)

        main_layout.addLayout(graph_side, stretch=3)

        # ====== DROITE : PANNEAU DE CONTROLE ======
        side_panel = QtWidgets.QFrame()
        side_panel.setObjectName("ControlPanel")
        side_panel.setFixedWidth(320)
        side_layout = QtWidgets.QVBoxLayout(side_panel)

        # --- Section 1: Paramètres d'acquisition ---
        side_layout.addWidget(self.create_section_title("Paramètres d'Acquisition"))
        acq_frame = QtWidgets.QFrame()
        acq_lyt = QtWidgets.QFormLayout(acq_frame)
        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Moyenne (Average)", "Brut (Raw)"])
        acq_lyt.addRow(QtWidgets.QLabel("Mode de capture :"), self.combo_mode)
        side_layout.addWidget(acq_frame)
        side_layout.addSpacing(15)

        # --- Section 2: Lancement des Scans ---
        side_layout.addWidget(self.create_section_title("Séquences de Scan"))
        btn_perso = QtWidgets.QPushButton("🚀 LANCER SCAN PERSO")
        btn_perso.setStyleSheet("background-color: #27AE60; font-size: 13px; margin-bottom: 5px;")
        btn_perso.clicked.connect(lambda: self.launch_scan("config_custom.json"))
        side_layout.addWidget(btn_perso)

        for mode, config in [("Scan Standard", "config_standard.json"), 
                             ("Scan Rapide", "config_rapide.json"), 
                             ("Scan Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(mode)
            btn.clicked.connect(lambda chk, c=config: self.launch_scan(c))
            side_layout.addWidget(btn)
        side_layout.addSpacing(20)

        # --- Section 3: Réglages en Direct ---
        side_layout.addWidget(self.create_section_title("Réglages PID & Vitesse"))
        self.kp_label = QtWidgets.QLabel(f"Gain Proportionnel (KP): {banc_Morrel.KP}")
        side_layout.addWidget(self.kp_label)
        side_layout.addWidget(self.create_slider(1, 100, int(banc_Morrel.KP * 10), self.update_kp))

        self.speed_label = QtWidgets.QLabel(f"Vitesse Max Moteurs: {banc_Morrel.MAX_SPEED}")
        side_layout.addWidget(self.speed_label)
        side_layout.addWidget(self.create_slider(1, 100, banc_Morrel.MAX_SPEED, self.update_max_speed))
        side_layout.addSpacing(20)

        # --- Section 4: Contrôle Flux ---
        side_layout.addWidget(self.create_section_title("Contrôle Exécution"))
        flow_lyt = QtWidgets.QHBoxLayout()
        self.btn_pause = QtWidgets.QPushButton("⏸ PAUSE")
        self.btn_pause.clicked.connect(self.action_pause)
        self.btn_resume = QtWidgets.QPushButton("▶ REPRISE")
        self.btn_resume.clicked.connect(self.action_resume)
        flow_lyt.addWidget(self.btn_pause)
        flow_lyt.addWidget(self.btn_resume)
        side_layout.addLayout(flow_lyt)
        side_layout.addStretch()

        # --- Section 5: Sécurité ---
        self.emergency_btn = QtWidgets.QPushButton("ARRÊT D'URGENCE")
        self.emergency_btn.setObjectName("Emergency")
        self.emergency_btn.setFixedHeight(60)
        self.emergency_btn.clicked.connect(self.action_emergency)
        side_layout.addWidget(self.emergency_btn)

        main_layout.addWidget(side_panel)
        self.tabs.addTab(control_widget, "📊 LIVE MONITORING")

    def init_editor_tab(self):
        editor_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(editor_widget)
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Angle Theta (°)", "Angles Psi (ex: 180, 90, 0)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        add_frame = QtWidgets.QFrame()
        add_frame.setObjectName("ControlPanel")
        add_lyt = QtWidgets.QHBoxLayout(add_frame)
        self.in_theta = QtWidgets.QDoubleSpinBox(); self.in_theta.setRange(-90, 90)
        self.in_psi = QtWidgets.QLineEdit(); self.in_psi.setPlaceholderText("180, 90, 0...")
        btn_add = QtWidgets.QPushButton("➕ AJOUTER")
        btn_add.clicked.connect(self.add_row_to_config)
        add_lyt.addWidget(QtWidgets.QLabel("Theta:")); add_lyt.addWidget(self.in_theta)
        add_lyt.addWidget(QtWidgets.QLabel("Psi:")); add_lyt.addWidget(self.in_psi); add_lyt.addWidget(btn_add)
        layout.addWidget(add_frame)

        btn_save = QtWidgets.QPushButton("💾 ENREGISTRER CONFIGURATION")
        btn_save.clicked.connect(self.save_custom_config)
        layout.addWidget(btn_save)
        self.tabs.addTab(editor_widget, "📝 CONFIG EDITOR")

    def init_calibration_tab(self):
        calib_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(calib_widget)

        # GAUCHE : ACTIONS
        left_panel = QtWidgets.QVBoxLayout()
        left_panel.addWidget(self.create_section_title("Calcul de Calibration"))
        self.btn_load_csv = QtWidgets.QPushButton("📂 CHARGER FICHIER SCAN")
        self.btn_load_csv.clicked.connect(self.process_calibration)
        left_panel.addWidget(self.btn_load_csv)
        
        self.calib_results = QtWidgets.QTextEdit()
        self.calib_results.setObjectName("Console")
        self.calib_results.setReadOnly(True)
        left_panel.addWidget(QtWidgets.QLabel("Paramètres Identifiés :"))
        left_panel.addWidget(self.calib_results)
        
        self.btn_save_params = QtWidgets.QPushButton("💾 SAUVEGARDER MATRICE")
        self.btn_save_params.setEnabled(False)
        left_panel.addWidget(self.btn_save_params)
        layout.addLayout(left_panel, stretch=1)

        # DROIT : VISUALISATION
        self.calib_plot = pg.PlotWidget()
        self.calib_plot.setBackground('#121212')
        self.calib_plot.showGrid(x=True, y=True)
        self.calib_plot.setAspectLocked(True)
        self.calib_plot.addLegend()
        self.scatter_raw = pg.ScatterPlotItem(size=5, brush=pg.mkBrush(200, 200, 200, 100), name="Données Brutes")
        self.scatter_cal = pg.ScatterPlotItem(size=5, brush=pg.mkBrush(46, 204, 113, 200), name="Données Calibrées")
        self.calib_plot.addItem(self.scatter_raw)
        self.calib_plot.addItem(self.scatter_cal)
        layout.addWidget(self.calib_plot, stretch=2)
        
        self.tabs.addTab(calib_widget, "🛠 CALIBRATION (Analyse)")

    # ------------------ FONCTIONS UTILITAIRES & CALLBACKS ------------------
    def create_section_title(self, text):
        lbl = QtWidgets.QLabel(text); lbl.setObjectName("Title"); return lbl

    def create_labeled_widget(self, label_text, widget):
        c = QtWidgets.QVBoxLayout(); lbl = QtWidgets.QLabel(label_text)
        lbl.setAlignment(QtCore.Qt.AlignCenter); lbl.setStyleSheet("font-size: 10px; color: #7F8C8D;")
        c.addWidget(lbl); c.addWidget(widget); w = QtWidgets.QWidget(); w.setLayout(c); return w

    def create_slider(self, min_v, max_v, current_v, callback):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setMinimum(min_v); s.setMaximum(max_v); s.setValue(current_v)
        s.valueChanged.connect(callback); return s

    def add_row_to_config(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self.in_theta.value())))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(self.in_psi.text()))

    def save_custom_config(self):
        seq = []
        for i in range(self.table.rowCount()):
            try:
                t = float(self.table.item(i, 0).text())
                p = [float(x.strip()) for x in self.table.item(i, 1).text().split(",") if x.strip()]
                seq.append({"theta": t, "psi_positions": p})
            except: continue
        with open("config_custom.json", "w") as f: json.dump({"sequence": seq}, f, indent=2)
        print("✅ Configuration personnalisée enregistrée.")

    def process_calibration(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Ouvrir le scan", "", "CSV Files (*.csv)")
        if not path: return
        import pandas as pd
        from calibration_engine import CalibratorEngine
        try:
            df = pd.read_csv(path)
            raw_lsb = df[['x_lsb', 'y_lsb', 'z_lsb']].values
            engine = CalibratorEngine(sensitivity=banc_Morrel.SENSITIVITY)
            brut_g, calib_g = engine.calibrate_data(raw_lsb)
            
            # Affichage graphique
            self.scatter_raw.setData(brut_g[:,0], brut_g[:,1])
            self.scatter_cal.setData(calib_g[:,0], calib_g[:,1])
            
            # Affichage résultats
            res_text = f"--- BIAS (g) ---\nX: {engine.b[0][0]:.6f}\nY: {engine.b[1][0]:.6f}\nZ: {engine.b[2][0]:.6f}\n\n"
            res_text += "--- MATRICE A-1 ---\n" + np.array2string(engine.A_1, precision=6)
            self.calib_results.setPlainText(res_text)
            self.btn_save_params.setEnabled(True)
            
            # Afficher aussi sur la sphère 3D
            self.update_sphere_signal.emit(calib_g)
            print(f"✅ Calibration réussie pour {path}")
        except Exception as e:
            print(f"❌ Erreur lors de la calibration : {e}")

    def update_sphere(self, calibrated_pts):
        try:
            for item in list(self.sphere_widget.items):
                if isinstance(item, gl.GLScatterPlotItem):
                    self.sphere_widget.removeItem(item)
            scatter = gl.GLScatterPlotItem(pos=calibrated_pts, size=5, color=(1, 0.5, 0, 1), pxMode=True)
            self.sphere_widget.addItem(scatter)
            self.sphere_widget.update()
        except Exception as e:
            pass

    def update_kp(self, val):
        banc_Morrel.KP = val / 10.0
        self.kp_label.setText(f"Gain KP: {banc_Morrel.KP:.1f}")

    def update_max_speed(self, val):
        banc_Morrel.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_emergency(self): banc_Morrel.emergency_stop(self.ser)
    def action_pause(self): banc_Morrel.pause_system()
    def action_resume(self): banc_Morrel.resume_system()

    def launch_scan(self, config):
        if not os.path.exists(config): 
            print(f"❌ Erreur : {config} introuvable")
            return
        acq_mode = "average" if self.combo_mode.currentIndex() == 0 else "raw"
        print(f"🚀 Lancement du scan | Mode: {acq_mode} | Config: {config}")
        banc_Morrel.running = True
        self.pbar.setValue(0)
        Thread(target=lambda: banc_Morrel.run_sequence(config, self.ser, acquisition_mode=acq_mode), daemon=True).start()

    # ------------------ TIMER UPDATE UI ------------------
    def update_ui(self):
        try:
            self.pbar.setValue(banc_Morrel.progress_val)
        except AttributeError:
            pass # Si progress_val n'existe pas encore
        
        with banc_Morrel.accel_lock:
            t, p = banc_Morrel.latest_theta, banc_Morrel.latest_psi
            
        if t is not None:
            self.lbl_theta_val.setText(f"{t:+.1f}°")
            self.lbl_psi_val.setText(f"{p:+.1f}°")
            
            # --- Update du Gimbal 3D (Nouvelle méthode unifiée) ---
            self.gimbal_3d.set_angles(t, p)
            
            now_time = time.time() - self.start_time
            self.time_data.append(now_time); self.theta_data.append(t); self.psi_data.append(p)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

            # --- Update de la Sphère 3D ---
            self.sphere_item.resetTransform()
            self.sphere_item.rotate(t, 1, 0, 0)
            self.sphere_item.rotate(p, 0, 1, 0)

# ========================================================================
#  POINT D'ENTRÉE PRINCIPAL
# ========================================================================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((banc_Morrel.HOST, banc_Morrel.PORT))
        ser = serial.Serial(banc_Morrel.SERIAL_PORT, banc_Morrel.BAUDRATE, timeout=1)
        Thread(target=banc_Morrel.accel_reader, args=(sock,), daemon=True).start()
        win = MainWindow(sock, ser)
        win.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Erreur connexion : {e}")
