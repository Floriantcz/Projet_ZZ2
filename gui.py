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

# --- STYLESHEET (QSS) ---
# Mise à jour pour inclure le style des onglets et du tableau
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
QPushButton#Emergency:disabled { background-color: #2C3E50; color: #7F8C8D; }

QSlider::handle:horizontal { background: #3498DB; width: 18px; border-radius: 9px; }

QTableWidget { background-color: #1E1E1E; color: white; gridline-color: #333; border: 1px solid #444; }
QHeaderView::section { background-color: #2D2D2D; color: #3498DB; padding: 5px; font-weight: bold; border: 1px solid #121212; }
QLineEdit, QDoubleSpinBox { background-color: #2D2D2D; color: white; border: 1px solid #34495E; padding: 5px; }
"""

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, ser):
        super().__init__()
        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center - Banc Accéléromètre")
        self.resize(1300, 850)
        self.setStyleSheet(STYLE_SHEET)

        # État des données
        self.time_data = []
        self.theta_data = []
        self.psi_data = []
        self.start_time = time.time()

        # Création du Widget Central à Onglets
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # Initialisation des deux interfaces
        self.init_control_tab() # Interface actuelle
        self.init_editor_tab()  # Le nouvel éditeur

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    # ---------------- ONGLET 1 : INTERFACE ----------------
    def init_control_tab(self):
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

        # --- PANNEAU DE GAUCHE (GRAPHIQUE) ---
        graph_container = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        
        self.lbl_theta_val = QtWidgets.QLabel("0.0°")
        self.lbl_theta_val.setObjectName("ValueDisplay")
        self.lbl_theta_val.setAlignment(QtCore.Qt.AlignCenter)
        
        self.lbl_psi_val = QtWidgets.QLabel("0.0°")
        self.lbl_psi_val.setObjectName("ValueDisplay")
        self.lbl_psi_val.setAlignment(QtCore.Qt.AlignCenter)

        header_layout.addWidget(self.create_labeled_widget("CURRENT THETA", self.lbl_theta_val))
        header_layout.addWidget(self.create_labeled_widget("CURRENT PSI", self.lbl_psi_val))
        graph_container.addLayout(header_layout)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2), name='Theta')
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2), name='Psi')
        graph_container.addWidget(self.plot_widget)
        main_layout.addLayout(graph_container, stretch=3)

        # --- PANNEAU DE DROITE (COMMANDES COMPLETES) ---
        side_panel = QtWidgets.QFrame()
        side_panel.setObjectName("ControlPanel")
        side_panel.setFixedWidth(320)
        side_layout = QtWidgets.QVBoxLayout(side_panel)

        side_layout.addWidget(self.create_section_title("Séquences de Scan"))
        # Ajout du bouton pour la config perso en premier
        btn_perso = QtWidgets.QPushButton("🚀 LANCER SCAN PERSO")
        btn_perso.setStyleSheet("background-color: #27AE60; margin-bottom: 5px;")
        btn_perso.clicked.connect(lambda: self.launch_scan("config_custom.json"))
        side_layout.addWidget(btn_perso)

        for mode, config in [("Standard", "config_standard.json"), 
                             ("Rapide", "config_rapide.json"), 
                             ("Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(f"Lancer Scan {mode}")
            btn.clicked.connect(lambda chk, c=config: self.launch_scan(c))
            side_layout.addWidget(btn)

        side_layout.addSpacing(20)
        side_layout.addWidget(self.create_section_title("Contrôle du flux"))
        flow_layout = QtWidgets.QHBoxLayout()
        self.pause_btn = QtWidgets.QPushButton("PAUSE")
        self.pause_btn.clicked.connect(self.action_pause)
        self.resume_btn = QtWidgets.QPushButton("REPRISE")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self.action_resume)
        flow_layout.addWidget(self.pause_btn)
        flow_layout.addWidget(self.resume_btn)
        side_layout.addLayout(flow_layout)

        side_layout.addSpacing(20)
        side_layout.addWidget(self.create_section_title("Réglages PID & Vitesse"))
        self.kp_label = QtWidgets.QLabel(f"Gain KP: {banc_code.KP}")
        side_layout.addWidget(self.kp_label)
        self.kp_slider = self.create_slider(1, 100, int(banc_code.KP * 10), self.update_kp)
        side_layout.addWidget(self.kp_slider)

        self.speed_label = QtWidgets.QLabel(f"Vitesse Max: {banc_code.MAX_SPEED}")
        side_layout.addWidget(self.speed_label)
        self.speed_slider = self.create_slider(1, 100, banc_code.MAX_SPEED, self.update_max_speed)
        side_layout.addWidget(self.speed_slider)

        side_layout.addStretch()
        self.emergency_btn = QtWidgets.QPushButton("ARRÊT D'URGENCE")
        self.emergency_btn.setObjectName("Emergency")
        self.emergency_btn.setFixedHeight(60)
        self.emergency_btn.clicked.connect(self.action_emergency)
        side_layout.addWidget(self.emergency_btn)

        self.status_label = QtWidgets.QLabel("Système Prêt")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        side_layout.addWidget(self.status_label)

        main_layout.addWidget(side_panel)
        self.tabs.addTab(control_widget, "📊 LIVE MONITORING & CONTROL")

    # ---------------- ONGLET 2 : L'ÉDITEUR DE CONFIGURATION ----------------
    def init_editor_tab(self):
        editor_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(editor_widget)

        layout.addWidget(self.create_section_title("🛠 Éditeur de Séquence (config_custom.json)"))
        
        # Le tableau
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Angle Theta (°)", "Angles Psi (ex: 180, 90, 0, -90)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Formulaire d'ajout rapide
        add_frame = QtWidgets.QFrame()
        add_frame.setObjectName("ControlPanel")
        add_lyt = QtWidgets.QHBoxLayout(add_frame)
        
        self.in_theta = QtWidgets.QDoubleSpinBox()
        self.in_theta.setRange(-90, 90)
        self.in_psi = QtWidgets.QLineEdit()
        self.in_psi.setPlaceholderText("Séparez par des virgules...")
        
        btn_add = QtWidgets.QPushButton("➕ AJOUTER LIGNE")
        btn_add.clicked.connect(self.add_row_to_config)
        
        add_lyt.addWidget(QtWidgets.QLabel("Theta:"))
        add_lyt.addWidget(self.in_theta)
        add_lyt.addWidget(QtWidgets.QLabel("Psi positions:"))
        add_lyt.addWidget(self.in_psi)
        add_lyt.addWidget(btn_add)
        layout.addWidget(add_frame)

        # Actions de fichier
        file_btns = QtWidgets.QHBoxLayout()
        btn_clear = QtWidgets.QPushButton("🗑 TOUT EFFACER")
        btn_clear.clicked.connect(lambda: self.table.setRowCount(0))
        
        btn_save = QtWidgets.QPushButton("💾 ENREGISTRER LA CONFIGURATION")
        btn_save.setStyleSheet("background-color: #27AE60; padding: 15px;")
        btn_save.clicked.connect(self.save_custom_config)
        
        file_btns.addWidget(btn_clear)
        file_btns.addStretch()
        file_btns.addWidget(btn_save)
        layout.addLayout(file_btns)

        self.tabs.addTab(editor_widget, "📝 CONFIGURATION EDITOR")

    # --- LOGIQUE ÉDITEUR ---
    def add_row_to_config(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self.in_theta.value())))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(self.in_psi.text()))
        self.in_psi.clear()

    def save_custom_config(self):
        seq = []
        for i in range(self.table.rowCount()):
            try:
                t = float(self.table.item(i, 0).text())
                p_raw = self.table.item(i, 1).text()
                p_list = [float(x.strip()) for x in p_raw.split(",") if x.strip()]
                seq.append({"theta": t, "psi_positions": p_list})
            except: continue
        
        with open("config_custom.json", "w") as f:
            json.dump({"sequence": seq}, f, indent=2)
        QtWidgets.QMessageBox.information(self, "Sauvegarde", "La configuration personnalisée a été enregistrée avec succès !")

    # --- HELPERS UI ---
    def create_section_title(self, text):
        lbl = QtWidgets.QLabel(text); lbl.setObjectName("Title"); return lbl

    def create_labeled_widget(self, label_text, widget):
        container = QtWidgets.QVBoxLayout()
        lbl = QtWidgets.QLabel(label_text); lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 10px; color: #7F8C8D; font-weight: bold;")
        container.addWidget(lbl); container.addWidget(widget)
        w = QtWidgets.QWidget(); w.setLayout(container); return w

    def create_slider(self, min_v, max_v, current_v, callback):
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setMinimum(min_v); slider.setMaximum(max_v); slider.setValue(current_v)
        slider.valueChanged.connect(callback); return slider

    # --- LOGIQUE ORIGINALE ---
    def update_kp(self, val):
        banc_code.KP = val / 10.0
        self.kp_label.setText(f"Gain KP: {banc_code.KP:.1f}")

    def update_max_speed(self, val):
        banc_code.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_pause(self):
        banc_code.paused = True
        self.resume_btn.setEnabled(True); self.pause_btn.setEnabled(False)
        self.status_label.setText("⏸ SYSTÈME EN PAUSE")

    def action_resume(self):
        banc_code.paused = False
        self.resume_btn.setEnabled(False); self.pause_btn.setEnabled(True)
        self.status_label.setText("▶ SCAN EN COURS")

    def action_emergency(self):
        banc_code.emergency_stop(self.ser)
        self.emergency_btn.setEnabled(False)
        self.status_label.setText("🛑 ARRÊT D'URGENCE")
        self.status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")

    def launch_scan(self, config):
        if not os.path.exists(config):
            QtWidgets.QMessageBox.critical(self, "Erreur", f"Le fichier {config} n'existe pas. Créez-le dans l'éditeur.")
            return
        banc_code.running = True
        banc_code.paused = False
        self.status_label.setText(f"Scan: {config}")
        Thread(target=lambda: banc_code.run_sequence(config, self.ser), daemon=True).start()

    def update_ui(self):
        with banc_code.accel_lock:
            t, p = banc_code.latest_theta, banc_code.latest_psi
        if t is not None:
            self.lbl_theta_val.setText(f"{t:+.1f}°")
            self.lbl_psi_val.setText(f"{p:+.1f}°")
            now = time.time() - self.start_time
            self.time_data.append(now); self.theta_data.append(t); self.psi_data.append(p)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

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
        print(f"Erreur de connexion : {e}")