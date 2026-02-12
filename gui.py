#!/usr/bin/env python3
import sys
import time
import socket
import serial
import json
import os
from threading import Thread
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import banc_code

# Classe pour rediriger les 'print' vers la console QSS
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

# --- STYLESHEET (QSS) ---
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
QLineEdit, QDoubleSpinBox { background-color: #2D2D2D; color: white; border: 1px solid #34495E; padding: 5px; }
"""

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, ser):
        super().__init__()
        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center Pro - Banc Accéléromètre")
        self.resize(1300, 900)
        self.setStyleSheet(STYLE_SHEET)

        self.time_data, self.theta_data, self.psi_data = [], [], []
        self.start_time = time.time()

        # Layout Principal Vertical (Onglets + Console en bas)
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

        layout_global.addWidget(self.create_section_title("📋 Console Système"))
        layout_global.addWidget(self.console_log, stretch=1)

        self.console_log.setMinimumHeight(100)
        self.console_log.setMaximumHeight(250)


        # Redirection du stdout vers la console
        sys.stdout = OutLog(self.console_log, sys.stdout)

        self.init_control_tab()
        self.init_editor_tab()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    def init_control_tab(self):
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

        # GAUCHE : Graphique + Barre de Progression
        graph_side = QtWidgets.QVBoxLayout()
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

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2))
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2))
        graph_side.addWidget(self.plot_widget)

        # BARRE DE PROGRESSION
        graph_side.addWidget(self.create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)

        main_layout.addLayout(graph_side, stretch=3)

        # DROITE : Commandes
        side_panel = QtWidgets.QFrame()
        side_panel.setObjectName("ControlPanel")
        side_panel.setFixedWidth(320)
        side_layout = QtWidgets.QVBoxLayout(side_panel)

        side_layout.addWidget(self.create_section_title("Séquences de Scan"))
        btn_perso = QtWidgets.QPushButton("🚀 LANCER SCAN PERSO")
        btn_perso.setStyleSheet("background-color: #27AE60; margin-bottom: 5px;")
        btn_perso.clicked.connect(lambda: self.launch_scan("config_custom.json"))
        side_layout.addWidget(btn_perso)

        for mode, config in [("Standard", "config_standard.json"), ("Rapide", "config_rapide.json"), ("Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(f"Lancer {mode}")
            btn.clicked.connect(lambda chk, c=config: self.launch_scan(c))
            side_layout.addWidget(btn)

        side_layout.addSpacing(20)
        side_layout.addWidget(self.create_section_title("Réglages PID"))
        self.kp_label = QtWidgets.QLabel(f"Gain KP: {banc_code.KP}")
        side_layout.addWidget(self.kp_label)
        side_layout.addWidget(self.create_slider(1, 100, int(banc_code.KP * 10), self.update_kp))

        self.speed_label = QtWidgets.QLabel(f"Vitesse Max: {banc_code.MAX_SPEED}")
        side_layout.addWidget(self.speed_label)
        side_layout.addWidget(self.create_slider(1, 100, banc_code.MAX_SPEED, self.update_max_speed))

        # --- Boutons Pause / Reprise ---
        side_layout.addSpacing(20)
        side_layout.addWidget(self.create_section_title("Contrôle Exécution"))

        self.btn_pause = QtWidgets.QPushButton("⏸ PAUSE")
        self.btn_pause.clicked.connect(self.action_pause)
        side_layout.addWidget(self.btn_pause)

        self.btn_resume = QtWidgets.QPushButton("▶ REPRISE")
        self.btn_resume.clicked.connect(self.action_resume)
        side_layout.addWidget(self.btn_resume)

        side_layout.addStretch()
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

    # ------------------ FONCTIONS UTILITAIRES ------------------
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

    def create_section_title(self, text):
        lbl = QtWidgets.QLabel(text); lbl.setObjectName("Title"); return lbl

    def create_labeled_widget(self, label_text, widget):
        c = QtWidgets.QVBoxLayout(); lbl = QtWidgets.QLabel(label_text)
        lbl.setAlignment(QtCore.Qt.AlignCenter); lbl.setStyleSheet("font-size: 10px; color: #7F8C8D;")
        c.addWidget(lbl); c.addWidget(widget); w = QtWidgets.QWidget(); w.setLayout(c); return w

    def create_slider(self, min_v, max_v, current_v, callback):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setMinimum(min_v); s.setMaximum(max_v); s.setValue(current_v)
        s.valueChanged.connect(callback); return s

    # ------------------ CALLBACKS ------------------
    def update_kp(self, val):
        banc_code.KP = val / 10.0
        self.kp_label.setText(f"Gain KP: {banc_code.KP:.1f}")

    def update_max_speed(self, val):
        banc_code.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_emergency(self):
        banc_code.emergency_stop(self.ser)

    def action_pause(self):
        banc_code.pause_system()

    def action_resume(self):
        banc_code.resume_system()

    def launch_scan(self, config):
        if not os.path.exists(config): return
        banc_code.running = True
        self.pbar.setValue(0)
        Thread(target=lambda: banc_code.run_sequence(config, self.ser), daemon=True).start()

    def update_ui(self):
        # Update Progression
        self.pbar.setValue(banc_code.progress_val)
        
        with banc_code.accel_lock:
            t, p = banc_code.latest_theta, banc_code.latest_psi
        if t is not None:
            self.lbl_theta_val.setText(f"{t:+.1f}°")
            self.lbl_psi_val.setText(f"{p:+.1f}°")
            now_time = time.time() - self.start_time
            self.time_data.append(now_time); self.theta_data.append(t); self.psi_data.append(p)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((banc_code.HOST, banc_code.PORT))
        ser = serial.Serial(banc_code.SERIAL_PORT, banc_code.BAUDRATE, timeout=1)
        Thread(target=banc_code.accel_reader, args=(sock,), daemon=True).start()
        win = MainWindow(sock, ser); win.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Erreur connexion : {e}")
