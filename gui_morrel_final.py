#!/usr/bin/env python3
import sys
import os
import time
import json
import socket
import serial
import glob
import numpy as np
from threading import Thread
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal
import pyqtgraph as pg
import pyqtgraph.opengl as gl
import numpy as np
import banc_Morrel  # ton fichier existant

# ------------------ REDIRECTION PRINT ------------------
# ------------------ REDIRECTION PRINT ------------------
class OutLog:
    def __init__(self, signal, out=None):
        self.signal = signal
        self.out = out

    def write(self, m):
        if m.strip():
            # ✅ thread-safe via signal Qt
            self.signal.emit(m.strip())
        if self.out:
            self.out.write(m)

    def flush(self):
        if self.out:
            self.out.flush()

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
    log_signal = pyqtSignal(str)   # ✅ AJOUT


    def __init__(self, sock, ser):
        super().__init__()

        self.update_sphere_signal.connect(self.update_sphere)
        self.log_signal.connect(self._append_log)


        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center Pro - Banc Accéléromètre")
        self.resize(1500, 950)
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

        # ------------------ GAUCHE : Graphique + Progression ------------------
        graph_side = QtWidgets.QVBoxLayout()

        # Affichage Theta / Psi en haut
        header_layout = QtWidgets.QHBoxLayout()
        self.lbl_theta_val = QtWidgets.QLabel("0.0°")
        self.lbl_theta_val.setObjectName("ValueDisplay")
        self.lbl_theta_val.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_psi_val = QtWidgets.QLabel("0.0°")
        self.lbl_psi_val.setObjectName("ValueDisplay")
        self.lbl_psi_val.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(self.create_labeled_widget("CURRENT THETA", self.lbl_theta_val))
        header_layout.addWidget(self.create_labeled_widget("CURRENT PSI", self.lbl_psi_val))
        graph_side.addLayout(header_layout)

        # Plot PyQtGraph
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2))
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2))
        graph_side.addWidget(self.plot_widget)

        # Barre de progression
        graph_side.addWidget(self.create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)

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
        self.kp_label = QtWidgets.QLabel(f"Gain KP: {banc_Morrel.KP}")
        side_layout.addWidget(self.kp_label)
        side_layout.addWidget(self.create_slider(1, 100, int(banc_Morrel.KP * 10), self.update_kp))

        self.speed_label = QtWidgets.QLabel(f"Vitesse Max: {banc_Morrel.MAX_SPEED}")
        side_layout.addWidget(self.speed_label)
        side_layout.addWidget(self.create_slider(1, 100, banc_Morrel.MAX_SPEED, self.update_max_speed))

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

        # Sphere 3D
        self.sphere_widget = gl.GLViewWidget()
        self.sphere_widget.setCameraPosition(distance=400)
        self.sphere_item = gl.GLMeshItem(meshdata=gl.MeshData.sphere(rows=20, cols=20),
                                         smooth=True, color=(0.2, 0.6, 1, 0.5),
                                         shader='shaded', drawEdges=True)
        self.sphere_widget.addItem(self.sphere_item)
        graph_side.addWidget(self.sphere_widget)

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
        """Affiche les points calibrés dans la vue 3D de façon robuste."""

        if calibrated is None:
            return

        try:
            # --- conversion numpy propre ---
            pts = np.asarray(calibrated)

            # enlever partie imaginaire si présente
            if np.iscomplexobj(pts):
                pts = np.real(pts)

            # vérifier shape
            if pts.ndim != 2 or pts.shape[1] != 3:
                print("⚠️ Format des points invalide pour la sphère:", pts.shape)
                return

            # enlever NaN / inf
            mask = np.isfinite(pts).all(axis=1)
            pts = pts[mask]

            if pts.size == 0:
                print("⚠️ Aucun point valide pour affichage")
                return

            # conversion float32 obligatoire OpenGL
            pts = pts.astype(np.float32)

            # ------------------------------
            # supprimer anciens nuages
            # ------------------------------
            for item in list(self.sphere_widget.items):
                if isinstance(item, gl.GLScatterPlotItem):
                    self.sphere_widget.removeItem(item)

            # ------------------------------
            # ajouter nouveaux points
            # ------------------------------
            scatter = gl.GLScatterPlotItem(
                pos=pts,
                size=5,
                color=(1, 0.5, 0, 1),
                pxMode=True
            )
            self.sphere_widget.addItem(scatter)

            # ------------------------------
            # 🔥 IMPORTANT : forcer refresh
            # ------------------------------
            self.sphere_widget.update()

            # ------------------------------
            # 🔥 OPTIONNEL mais recommandé
            # recentrer caméra sur données
            # ------------------------------
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

        # Thread-safe GUI update
        def qt_callback(raw, calibrated):
            try:
                self.update_sphere_signal.emit(np.array(calibrated))
            except Exception as e:
                print("Callback error:", e)

        from accelerometer_calib import Accelerometer  # suppose que tu as cette classe
        acc = Accelerometer(latest_file, qt_callback=qt_callback)
        Thread(target=lambda: self._calibrate_thread(acc), daemon=True).start()

    def _calibrate_thread(self, acc):
        acc.run()
        # Affichage coefficients dans GUI
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
        banc_Morrel.KP = val/10.0
        self.kp_label.setText(f"Gain KP: {banc_Morrel.KP:.1f}")

    def update_max_speed(self, val):
        banc_Morrel.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_pause(self):
        banc_Morrel.pause_system()

    def action_resume(self):
        banc_Morrel.resume_system()

    def action_emergency(self):
        banc_Morrel.emergency_stop(self.ser)

    def launch_scan(self, config):
        if not os.path.exists(config): return
        banc_Morrel.running = True
        self.pbar.setValue(0)
        Thread(
            target=lambda: banc_Morrel.run_sequence(
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
        with banc_Morrel.accel_lock:
            t, p = banc_Morrel.latest_theta, banc_Morrel.latest_psi

        if t is not None:
            self.lbl_theta_val.setText(f"{t:+.1f}°")
            self.lbl_psi_val.setText(f"{p:+.1f}°")
            now_time = time.time() - self.start_time
            self.time_data.append(now_time)
            self.theta_data.append(t)
            self.psi_data.append(p)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

            # --- Sphere rotation ---
            self.sphere_item.resetTransform()
            self.sphere_item.rotate(t,1,0,0)
            self.sphere_item.rotate(p,0,1,0)

# ------------------ MAIN ------------------
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
