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
QTextEdit#Console { background-color: #0A0A0A; color: #00FF00; font-family: 'Consolas', monospace; font-size: 11px; border: 1px solid #333; }
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

        layout_global = QtWidgets.QVBoxLayout()
        container_global = QtWidgets.QWidget()
        container_global.setLayout(layout_global)
        self.setCentralWidget(container_global)

        self.tabs = QtWidgets.QTabWidget()
        layout_global.addWidget(self.tabs, stretch=4)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setObjectName("Console")
        self.console_log.setReadOnly(True)

        layout_global.addWidget(self.create_section_title("📋 Console Système"))
        layout_global.addWidget(self.console_log, stretch=1)
        self.console_log.setMinimumHeight(100)
        self.console_log.setMaximumHeight(250)

        sys.stdout = OutLog(self.console_log, sys.stdout)

        self.init_control_tab()
        self.init_editor_tab()
        self.init_settings_tab()

        # Si l'un des deux manque, on affiche un avertissement en console
        if not self.sock or not self.ser:
            print("⚠ ATTENTION : Certaines connexions ont échoué. Vérifiez l'onglet SETTINGS.")

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    def init_control_tab(self):
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

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

        graph_side.addWidget(self.create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)
        main_layout.addLayout(graph_side, stretch=3)

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

    def init_settings_tab(self):
        settings_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(settings_widget)
        form_frame = QtWidgets.QFrame()
        form_frame.setObjectName("ControlPanel")
        form = QtWidgets.QFormLayout(form_frame)
        form.setSpacing(15)

        self.edit_host = QtWidgets.QLineEdit(str(banc_code.HOST))
        self.edit_port = QtWidgets.QLineEdit(str(banc_code.PORT))
        self.edit_serial = QtWidgets.QLineEdit(str(banc_code.SERIAL_PORT))
        self.edit_baud = QtWidgets.QLineEdit(str(banc_code.BAUDRATE))
        
        form.addRow(self.create_section_title("Réseau (Accéléromètre)"), QtWidgets.QLabel(""))
        form.addRow("Adresse IP :", self.edit_host)
        form.addRow("Port TCP :", self.edit_port)
        form.addRow(QtWidgets.QLabel(""), QtWidgets.QLabel(""))
        form.addRow(self.create_section_title("Série (Moteurs)"), QtWidgets.QLabel(""))
        form.addRow("Port COM :", self.edit_serial)
        form.addRow("Baudrate :", self.edit_baud)

        layout.addWidget(form_frame)
        
        btn_save_settings = QtWidgets.QPushButton("💾 ENREGISTRER & REDÉMARRER")
        btn_save_settings.setFixedHeight(50)
        btn_save_settings.setStyleSheet("background-color: #2980B9; font-size: 14px;")
        btn_save_settings.clicked.connect(self.save_settings_and_restart)
        layout.addWidget(btn_save_settings)
        
        layout.addStretch()
        layout.addWidget(QtWidgets.QLabel("L'application redémarrera automatiquement pour appliquer les changements."))
        self.tabs.addTab(settings_widget, "⚙️ SETTINGS")

    def save_settings_and_restart(self):
        try:
            new_conf = {
                "network": {"host": self.edit_host.text(), "port": int(self.edit_port.text())},
                "serial": {"port": self.edit_serial.text(), "baudrate": int(self.edit_baud.text())}
            }
            if banc_code.save_settings(new_conf):
                print("♻ Redémarrage de l'application...")
                # Relance le script actuel et ferme le processus en cours
                os.execl(sys.executable, sys.executable, *sys.argv)
        except ValueError:
            QtWidgets.QMessageBox.critical(self, "Erreur", "Veuillez entrer des valeurs numériques valides.")

    # ------------------ FONCTIONS UTILITAIRES ------------------
    def add_row_to_config(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self.in_theta.value())))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(self.in_psi.text()))

    def save_custom_config(self):
        seq = []
        has_error = False
        for i in range(self.table.rowCount()):
            item_theta = self.table.item(i, 0); item_psi = self.table.item(i, 1)
            item_theta.setBackground(QtGui.QColor("#1E1E1E")); item_psi.setBackground(QtGui.QColor("#1E1E1E"))
            try:
                t = float(item_theta.text())
                raw_psi = item_psi.text().replace(';', ',')
                p = [float(x.strip()) for x in raw_psi.split(",") if x.strip()]
                if not p: raise ValueError("Liste Psi vide")
                seq.append({"theta": t, "psi_positions": p})
            except ValueError:
                item_theta.setBackground(QtGui.QColor("#7B241C")); item_psi.setBackground(QtGui.QColor("#7B241C"))
                has_error = True

        if has_error:
            QtWidgets.QMessageBox.warning(self, "Erreur de saisie", "Certaines lignes contiennent des valeurs invalides.")
        else:
            with open("config_custom.json", "w") as f:
                json.dump({"sequence": seq}, f, indent=2)
            print(f"✅ Configuration sauvegardée ({len(seq)} étapes).")

    def create_section_title(self, text):
        lbl = QtWidgets.QLabel(text); lbl.setObjectName("Title"); return lbl

    def create_labeled_widget(self, label_text, widget):
        c = QtWidgets.QVBoxLayout(); lbl = QtWidgets.QLabel(label_text)
        lbl.setAlignment(QtCore.Qt.AlignCenter); lbl.setStyleSheet("font-size: 10px; color: #7F8C8D;")
        c.addWidget(lbl); c.addWidget(widget); w = QtWidgets.QWidget(); w.setLayout(c); return w

    def create_slider(self, min_v, max_v, current_v, callback):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setMinimum(min_v); s.setMaximum(max_v); s.setValue(current_v)
        s.valueChanged.connect(callback); return s

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
        if self.ser is None:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Le port série n'est pas connecté. Impossible de scanner.")
            return
        banc_code.running = True
        self.pbar.setValue(0)
        Thread(target=lambda: banc_code.run_sequence(config, self.ser), daemon=True).start()

    def update_ui(self):
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

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    
    sock, ser = None, None
    
    # Tentative de connexion Socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((banc_code.HOST, banc_code.PORT))
        Thread(target=banc_code.accel_reader, args=(sock,), daemon=True).start()
        print("✅ Connecté à l'accéléromètre.")
    except Exception as e:
        print(f"❌ Erreur Réseau : {e}")
        sock = None

    # Tentative de connexion Série
    try:
        ser = serial.Serial(banc_code.SERIAL_PORT, banc_code.BAUDRATE, timeout=1)
        print("✅ Connecté aux moteurs.")
    except Exception as e:
        print(f"❌ Erreur Série : {e}")
        ser = None

    win = MainWindow(sock, ser)
    win.show()
    sys.exit(app.exec_())