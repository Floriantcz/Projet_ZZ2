"""Point d'entrée et classe principale de l'interface
graphique reposant sur les modules refactorisés.

Ce fichier est **nouveau** et n'existait pas dans le workspace
initial. Il montre comment une application PyQt peut être construite en
assemblant des morceaux logiques du paquet ``Projet_ZZ2`` plutôt qu'en
entassant tout dans un script monolithique.

Pour lancer l'interface refactorée ::

    python -m Projet_ZZ2.ui.main

Par défaut, l'application se connecte à l'accéléromètre via TCP, mais une
option USB est désormais disponible. Choisissez le transport dans l'onglet
Settings et indiquez un port série et un baudrate si vous utilisez USB.

Le comportement reste volontairement très proche de l'ancien
``gui.py`` ; ses méthodes délèguent aux modules du paquet
(`accel`, `motor`, `scan`, etc.) au lieu de s'appuyer sur des
variables globales et de gros blocs de code inline.
"""

import sys
import os
import time
import json
import socket
import serial
from threading import Thread

import numpy as np

# déterminer la racine du paquet et le dossier de configuration
# pour que les fichiers JSON puissent être ouverts quel que soit
# le répertoire de travail actuel
PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(PACKAGE_ROOT, "config")

def config_path(filename: str) -> str:
    """Return an absolute path to a configuration file in ``config/``."""
    return os.path.join(CONFIG_DIR, filename)

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# importer les nouvelles briques modulaires
from .. import config as cfg
from .. import state, accel, motor, scan, utils
from .widgets import OutLog, GimbalWidget3D, STYLE_SHEET
from .helpers import (
    create_section_title,
    create_labeled_widget,
    create_collapsible_section,
    create_slider,
)


class MainWindow(QtWidgets.QMainWindow):
    """Main application window built from reusable components."""

    def __init__(self, sock=None, ser=None):
        super().__init__()
        self.sock = sock
        self.ser = ser
        self.setWindowTitle("Control Center Pro - Banc Accéléromètre (modulaire)")
        self.resize(1600, 950)
        self.setStyleSheet(STYLE_SHEET)

        # tampons utilisés pour le tracé en temps réel
        self.time_data, self.theta_data, self.psi_data = [], [], []
        self.start_time = time.time()

        # top‑level layout
        layout_global = QtWidgets.QVBoxLayout()
        container_global = QtWidgets.QWidget()
        container_global.setLayout(layout_global)
        self.setCentralWidget(container_global)

        # zone d'onglets (notebook)
        self.tabs = QtWidgets.QTabWidget()
        layout_global.addWidget(self.tabs, stretch=4)

        # panneau console et actions (réutilisé de l'implémentation
        # précédente)
        console_container = QtWidgets.QHBoxLayout()
        console_frame = QtWidgets.QFrame()
        console_frame.setObjectName("ControlPanel")
        console_layout = QtWidgets.QVBoxLayout(console_frame)
        console_layout.setContentsMargins(8, 8, 8, 8)

        self.console_log = QtWidgets.QTextEdit()
        self.console_log.setObjectName("Console")
        self.console_log.setReadOnly(True)
        self.console_log.setMinimumHeight(112)
        font = QtGui.QFont("Consolas", 9)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.console_log.setFont(font)
        self.console_log.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(create_section_title("📋 Console"))
        header_layout.addStretch()
        console_layout.addLayout(header_layout)
        console_layout.addWidget(self.console_log)

        console_actions = QtWidgets.QFrame()
        console_actions.setObjectName("ControlPanel")
        console_actions.setFixedWidth(140)
        actions_lyt = QtWidgets.QVBoxLayout(console_actions)
        actions_lyt.setContentsMargins(8, 8, 8, 8)
        actions_lyt.setSpacing(10)

        btn_clear = QtWidgets.QPushButton("🗑 Effacer")
        btn_clear.setToolTip("Effacer la console")
        btn_clear.clicked.connect(self.console_log.clear)
        btn_clear.setFixedHeight(36)
        actions_lyt.addWidget(btn_clear)

        btn_copy = QtWidgets.QPushButton("📋 Copier")
        btn_copy.setToolTip("Copier le contenu de la console")
        btn_copy.setFixedHeight(36)
        btn_copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.console_log.toPlainText()))
        actions_lyt.addWidget(btn_copy)
        actions_lyt.addStretch()

        console_container.addWidget(console_frame, stretch=3)
        console_container.addWidget(console_actions, stretch=0)
        layout_global.addLayout(console_container)

        sys.stdout = OutLog(self.console_log, sys.stdout)

        # assembler chaque onglet en utilisant les helpers ci-dessous
        self.init_control_tab()
        self.init_editor_tab()
        self.init_calibration_tab()
        self.init_settings_tab()

        # connexions matérielles
        if not self.sock or not self.ser:
            print("⚠ ATTENTION : Certaines connexions ont échoué. Vérifiez l'onglet SETTINGS.")
        else:
            Thread(target=motor.init_bench_home, args=(self.ser,), daemon=True).start()

        # mise à jour périodique de l'interface
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    # les méthodes qui suivent sont essentiellement une version allégée
    # des fonctions équivalentes de l'ancien ``gui.py`` ; elles sont
    # conservées ici pour la complétude mais délèguent le travail opérationnel
    # aux nouveaux modules (``scan.run_sequence`` etc.). Pour faire court
    # les commentaires ont été omis, mais l'implémentation originale reste
    # consultable dans le fichier d'héritage.

    def init_control_tab(self):
        control_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout(control_widget)

        # côté gauche : graphiques + visualisation 3D
        graph_side = QtWidgets.QVBoxLayout()
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(20)

        theta_widget = QtWidgets.QWidget()
        theta_layout = QtWidgets.QHBoxLayout(theta_widget)
        theta_layout.setContentsMargins(5, 3, 5, 3)
        theta_layout.setSpacing(8)
        theta_lbl = QtWidgets.QLabel("Θ")
        theta_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #E74C3C;")
        self.lbl_theta_val = QtWidgets.QLabel("0.0°")
        self.lbl_theta_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; background-color: #2D2D2D; border-radius: 3px; padding: 3px 12px;")
        theta_layout.addWidget(theta_lbl)
        theta_layout.addWidget(self.lbl_theta_val)

        psi_widget = QtWidgets.QWidget()
        psi_layout = QtWidgets.QHBoxLayout(psi_widget)
        psi_layout.setContentsMargins(5, 3, 5, 3)
        psi_layout.setSpacing(8)
        psi_lbl = QtWidgets.QLabel("Ψ")
        psi_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #3498DB;")
        self.lbl_psi_val = QtWidgets.QLabel("0.0°")
        self.lbl_psi_val.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF; background-color: #2D2D2D; border-radius: 3px; padding: 3px 12px;")
        psi_layout.addWidget(psi_lbl)
        psi_layout.addWidget(self.lbl_psi_val)

        header_layout.addWidget(theta_widget)
        header_layout.addWidget(psi_widget)
        header_layout.addStretch()
        graph_side.addLayout(header_layout)

        viz_layout = QtWidgets.QHBoxLayout()
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#121212')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.theta_curve = self.plot_widget.plot(pen=pg.mkPen('#E74C3C', width=2), name="Theta (θ)")
        self.psi_curve = self.plot_widget.plot(pen=pg.mkPen('#3498DB', width=2), name="Psi (ψ)")
        viz_layout.addWidget(self.plot_widget, stretch=1)
        self.gimbal_3d = GimbalWidget3D()
        viz_layout.addWidget(self.gimbal_3d, stretch=1)
        graph_side.addLayout(viz_layout, stretch=3)
        graph_side.addWidget(create_section_title("Progression du Scan"))
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setValue(0)
        graph_side.addWidget(self.pbar)
        main_layout.addLayout(graph_side, stretch=3)

        # right side: control panel (collapsed sections, sliders, buttons)
        side_panel = QtWidgets.QFrame()
        side_panel.setObjectName("ControlPanel")
        side_panel.setFixedWidth(320)
        side_layout = QtWidgets.QVBoxLayout(side_panel)
        side_layout.setSpacing(10)
        side_layout.setContentsMargins(10, 10, 10, 10)

        acq_frame = QtWidgets.QFrame()
        acq_frame.setObjectName("ControlPanel")
        acq_lyt = QtWidgets.QFormLayout(acq_frame)
        acq_lyt.setContentsMargins(6, 6, 6, 6)
        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Moyenne (Average)", "Brut (Raw)"])
        self.combo_mode.setStyleSheet("color: #FFFFFF; background-color: #2D2D2D;")
        acq_lyt.addRow(QtWidgets.QLabel("Mode de capture :"), self.combo_mode)
        side_layout.addWidget(create_collapsible_section("Paramètres d'Acquisition", acq_frame, expanded=False))

        seq_frame = QtWidgets.QFrame()
        seq_frame.setObjectName("ControlPanel")
        seq_lyt = QtWidgets.QVBoxLayout(seq_frame)
        seq_lyt.setContentsMargins(6, 6, 6, 6)
        btn_perso = QtWidgets.QPushButton("🚀 PERSO")
        btn_perso.setStyleSheet("background-color: #27AE60; padding: 5px; font-size: 12px;")
        btn_perso.clicked.connect(lambda: self.launch_scan("config_custom.json"))
        seq_lyt.addWidget(btn_perso)
        for mode, config_file in [("Standard", "config_standard.json"), ("Rapide", "config_rapide.json"), ("Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(mode)
            btn.setStyleSheet("background-color: #34495E; color: white; border-radius: 5px; padding: 8px; font-weight: bold; border: None;")
            btn.clicked.connect(lambda chk, c=config_file: self.launch_scan(c))
            seq_lyt.addWidget(btn)
        side_layout.addWidget(create_collapsible_section("Séquences", seq_frame, expanded=False))

        pid_frame = QtWidgets.QFrame()
        pid_frame.setObjectName("ControlPanel")
        pid_lyt = QtWidgets.QVBoxLayout(pid_frame)
        pid_lyt.setContentsMargins(6, 6, 6, 6)
        self.kp_label = QtWidgets.QLabel(f"KP: {motor.KP}")
        self.kp_label.setStyleSheet("font-size: 10px;")
        pid_lyt.addWidget(self.kp_label)
        pid_lyt.addWidget(create_slider(1, 100, int(motor.KP * 10), self.update_kp))
        self.speed_label = QtWidgets.QLabel(f"Vitesse Max: {motor.MAX_SPEED}")
        self.speed_label.setStyleSheet("font-size: 10px;")
        pid_lyt.addWidget(self.speed_label)
        pid_lyt.addWidget(create_slider(1, 100, motor.MAX_SPEED, self.update_max_speed))
        side_layout.addWidget(create_collapsible_section("Réglages PID", pid_frame, expanded=False))

        ctrl_frame = QtWidgets.QFrame()
        ctrl_frame.setObjectName("ControlPanel")
        ctrl_lyt = QtWidgets.QHBoxLayout(ctrl_frame)
        ctrl_lyt.setContentsMargins(6, 6, 6, 6)
        ctrl_lyt.setSpacing(8)
        self.btn_pause = QtWidgets.QPushButton("⏸")
        self.btn_pause.setToolTip("Pause")
        self.btn_pause.setFixedSize(64, 36)
        self.btn_pause.setStyleSheet("background-color: #34495E; color: white; border-radius: 5px; font-size: 14px; border: None;")
        self.btn_pause.clicked.connect(self.action_pause)
        self.btn_resume = QtWidgets.QPushButton("▶")
        self.btn_resume.setToolTip("Reprise")
        self.btn_resume.setFixedSize(64, 36)
        self.btn_resume.setStyleSheet("background-color: #34495E; color: white; border-radius: 5px; font-size: 14px; border: None;")
        self.btn_resume.clicked.connect(self.action_resume)
        ctrl_lyt.addWidget(self.btn_pause)
        ctrl_lyt.addWidget(self.btn_resume)
        self.lbl_flow_status = QtWidgets.QLabel("État: idle")
        self.lbl_flow_status.setStyleSheet("font-size: 11px; color: #BDC3C7;")
        ctrl_lyt.addWidget(self.lbl_flow_status)
        ctrl_lyt.addStretch()
        side_layout.addWidget(create_collapsible_section("Contrôle", ctrl_frame, expanded=False))
        side_layout.addStretch()

        self.emergency_btn = QtWidgets.QPushButton("🛑 STOP")
        self.emergency_btn.setObjectName("Emergency")
        self.emergency_btn.setFixedHeight(50)
        self.emergency_btn.setStyleSheet("background-color: #C0392B; color: white; border-radius: 5px; font-size: 14px; font-weight: bold; border: None;")
        self.emergency_btn.clicked.connect(self.action_emergency)
        side_layout.addWidget(self.emergency_btn)

        side_scroll = QtWidgets.QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(side_panel)
        side_scroll.setFixedWidth(340)
        side_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        side_scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
            "QScrollArea QWidget { background-color: transparent; }"
        )
        side_scroll.viewport().setStyleSheet("background-color: transparent;")
        side_scroll.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(side_scroll)
        self.tabs.addTab(control_widget, "📊 LIVE MONITORING")

    def init_editor_tab(self):
        # similaire à l'original ; commentaires supprimés pour la lisibilité
        editor_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(editor_widget)
        layout.addWidget(create_section_title("Éditeur de Configuration Personnalisée"))
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Angle Theta (°)", "Angles Psi (ex: 180, 90, 0)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        add_frame = QtWidgets.QFrame()
        add_frame.setObjectName("ControlPanel")
        add_lyt = QtWidgets.QHBoxLayout(add_frame)
        self.in_theta = QtWidgets.QDoubleSpinBox()
        self.in_theta.setRange(-90, 90)
        self.in_psi = QtWidgets.QLineEdit()
        self.in_psi.setPlaceholderText("180, 90, 0...")
        btn_add = QtWidgets.QPushButton("➕ AJOUTER")
        btn_add.clicked.connect(self.add_row_to_config)
        add_lyt.addWidget(QtWidgets.QLabel("Theta:"))
        add_lyt.addWidget(self.in_theta)
        add_lyt.addWidget(QtWidgets.QLabel("Psi:"))
        add_lyt.addWidget(self.in_psi)
        add_lyt.addWidget(btn_add)
        layout.addWidget(add_frame)
        btn_save = QtWidgets.QPushButton("💾 ENREGISTRER CONFIGURATION")
        btn_save.clicked.connect(self.save_custom_config)
        layout.addWidget(btn_save)
        self.tabs.addTab(editor_widget, "📝 CONFIG EDITOR")

    def init_calibration_tab(self):
        calib_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(calib_widget)
        left_panel = QtWidgets.QVBoxLayout()
        left_panel.addWidget(create_section_title("Calcul de Calibration"))
        self.btn_load_csv = QtWidgets.QPushButton("📂 CHARGER FICHIER SCAN")
        self.btn_load_csv.clicked.connect(self.process_calibration)
        left_panel.addWidget(self.btn_load_csv)
        left_panel.addWidget(QtWidgets.QLabel("Paramètres Identifiés :"))
        self.calib_results = QtWidgets.QTextEdit()
        self.calib_results.setObjectName("Console")
        self.calib_results.setReadOnly(True)
        left_panel.addWidget(self.calib_results)
        self.btn_save_params = QtWidgets.QPushButton("💾 SAUVEGARDER MATRICE")
        self.btn_save_params.setEnabled(False)
        left_panel.addWidget(self.btn_save_params)
        layout.addLayout(left_panel, stretch=1)
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
        self.tabs.addTab(calib_widget, "🛠 CALIBRATION")

    def init_settings_tab(self):
        settings_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(settings_widget)
        form_frame = QtWidgets.QFrame()
        form_frame.setObjectName("ControlPanel")
        form = QtWidgets.QFormLayout(form_frame)
        form.setSpacing(15)
        # lire les réglages réseau/série courants depuis le module de
        # configuration partagé ; il n'est plus nécessaire d'importer
        # l'ancien script ``banc_code``.
        settings = cfg.load_settings()
        # network parameters
        self.edit_host = QtWidgets.QLineEdit(str(settings['network']['host']))
        self.edit_port = QtWidgets.QLineEdit(str(settings['network']['port']))
        # usb parameters (used when transport="usb")
        self.edit_usb_port = QtWidgets.QLineEdit(settings.get('usb', {}).get('port', ""))
        self.edit_usb_baud = QtWidgets.QLineEdit(str(settings.get('usb', {}).get('baudrate', 115200)))
        # motor serial parameters
        self.edit_serial = QtWidgets.QLineEdit(str(settings['serial']['port']))
        self.edit_baud = QtWidgets.QLineEdit(str(settings['serial']['baudrate']))

        # sélection du transport (tcp ou usb)
        self.combo_transport = QtWidgets.QComboBox()
        self.combo_transport.addItems(["tcp", "usb"])
        current_transport = settings.get('transport', 'tcp')
        idx = self.combo_transport.findText(current_transport)
        if idx >= 0:
            self.combo_transport.setCurrentIndex(idx)

        form.addRow(create_section_title("Accéléromètre"), QtWidgets.QLabel(""))
        form.addRow("Type de connexion :", self.combo_transport)
        form.addRow("Adresse IP :", self.edit_host)
        form.addRow("Port TCP :", self.edit_port)
        form.addRow("Port USB :", self.edit_usb_port)
        form.addRow("Baudrate USB :", self.edit_usb_baud)
        form.addRow(QtWidgets.QLabel(""), QtWidgets.QLabel(""))
        form.addRow(create_section_title("Série (Moteurs)"), QtWidgets.QLabel(""))
        form.addRow("Port COM :", self.edit_serial)
        form.addRow("Baudrate :", self.edit_baud)

        # liaison pour basculer la visibilité des champs quand le transport
        # change
        self.combo_transport.currentTextChanged.connect(self._on_transport_changed)
        # initialize visibility state
        self._on_transport_changed(self.combo_transport.currentText())
        layout.addWidget(form_frame)
        btn_save_settings = QtWidgets.QPushButton("💾 ENREGISTRER & REDÉMARRER")
        btn_save_settings.setFixedHeight(50)
        btn_save_settings.setStyleSheet("background-color: #2980B9; font-size: 14px;")
        btn_save_settings.clicked.connect(self.save_settings_and_restart)
        layout.addWidget(btn_save_settings)
        layout.addStretch()
        layout.addWidget(QtWidgets.QLabel("L'application redémarrera automatiquement pour appliquer les changements."))
        self.tabs.addTab(settings_widget, "⚙️ SETTINGS")

    # les méthodes utilitaires / callbacks suivent ; elles reproduisent
    # en grande partie le comportement de l'ancien code tout en
    # déléguant autant que possible au nouveau paquet.

    def create_section_title(self, text):
        return create_section_title(text)

    def create_labeled_widget(self, label_text, widget):
        return create_labeled_widget(label_text, widget)

    def create_collapsible_section(self, title, content_widget, expanded=True):
        return create_collapsible_section(title, content_widget, expanded)

    def create_slider(self, min_v, max_v, current_v, callback):
        return create_slider(min_v, max_v, current_v, callback)

    def add_row_to_config(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self.in_theta.value())))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(self.in_psi.text()))

    def save_custom_config(self):
        seq = []
        has_error = False
        for i in range(self.table.rowCount()):
            item_theta = self.table.item(i, 0)
            item_psi = self.table.item(i, 1)
            item_theta.setBackground(QtGui.QColor("#1E1E1E"))
            item_psi.setBackground(QtGui.QColor("#1E1E1E"))
            try:
                t = float(item_theta.text())
                raw_psi = item_psi.text().replace(';', ',')
                p = [float(x.strip()) for x in raw_psi.split(",") if x.strip()]
                if not p:
                    raise ValueError("Liste Psi vide")
                seq.append({"theta": t, "psi_positions": p})
            except ValueError:
                item_theta.setBackground(QtGui.QColor("#7B241C"))
                item_psi.setBackground(QtGui.QColor("#7B241C"))
                has_error = True
        if has_error:
            QtWidgets.QMessageBox.warning(self, "Erreur de saisie", "Certaines lignes contiennent des valeurs invalides.")
        else:
            # ensure the directory exists just in case
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(config_path("config_custom.json"), "w") as f:
                json.dump({"sequence": seq}, f, indent=2)
            print(f"✅ Configuration sauvegardée ({len(seq)} étapes).")

    def process_calibration(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Ouvrir le scan", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            import csv
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if not rows:
                print("❌ Fichier CSV vide")
                return
            required_cols = ['x_lsb', 'y_lsb', 'z_lsb']
            header = rows[0].keys()
            if not all(col in header for col in required_cols):
                print(f"❌ Colonnes manquantes. Colonnes trouvées : {list(header)}")
                return
            raw_lsb = []
            for row in rows:
                try:
                    x = float(row['x_lsb'])
                    y = float(row['y_lsb'])
                    z = float(row['z_lsb'])
                    raw_lsb.append([x, y, z])
                except (ValueError, KeyError):
                    continue
            if not raw_lsb:
                print("❌ Aucune donnée valide trouvée")
                return
            raw_lsb = np.array(raw_lsb)
            raw_g = raw_lsb / accel.SENSITIVITY
            self.scatter_raw.setData(raw_g[:, 0], raw_g[:, 1])
            x_mean, y_mean, z_mean = np.mean(raw_g, axis=0)
            x_std, y_std, z_std = np.std(raw_g, axis=0)
            norms = np.sqrt(np.sum(raw_g**2, axis=1))
            norm_mean = np.mean(norms)
            norm_std = np.std(norms)
            res_text = f"--- STATISTIQUES BRUTES ---\n"
            res_text += f"Fichier : {os.path.basename(path)}\n"
            res_text += f"Nombre de points : {len(raw_g)}\n\n"
            res_text += f"X: {x_mean:.6f} ± {x_std:.6f} g\n"
            res_text += f"Y: {y_mean:.6f} ± {y_std:.6f} g\n"
            res_text += f"Z: {z_mean:.6f} ± {z_std:.6f} g\n\n"
            res_text += f"Norme moyenne: {norm_mean:.6f} ± {norm_std:.6f} g\n"
            res_text += f"(Théorique: 1.0 g)\n"
            self.calib_results.setPlainText(res_text)
            print(f"✅ Données chargées : {len(raw_g)} points depuis {os.path.basename(path)}")
        except Exception as e:
            print(f"❌ Erreur lors du traitement : {e}")
            import traceback
            traceback.print_exc()

    def update_kp(self, val):
        motor.KP = val / 10.0
        self.kp_label.setText(f"Gain KP: {motor.KP:.1f}")

    def update_max_speed(self, val):
        motor.MAX_SPEED = val
        self.speed_label.setText(f"Vitesse Max: {val}")

    def action_emergency(self):
        motor.emergency_stop(self.ser)
        if hasattr(self, 'lbl_flow_status'):
            self.lbl_flow_status.setText("État: stopped")

    def action_pause(self):
        state.pause_system()
        if hasattr(self, 'lbl_flow_status'):
            self.lbl_flow_status.setText("État: paused")

    def action_resume(self):
        state.resume_system()
        if hasattr(self, 'lbl_flow_status'):
            self.lbl_flow_status.setText("État: running")

    def _on_transport_changed(self, transport: str):
        # enable/disable network/USB fields based on choice
        tcp = transport.lower() == "tcp"
        self.edit_host.setEnabled(tcp)
        self.edit_port.setEnabled(tcp)
        self.edit_usb_port.setEnabled(not tcp)
        self.edit_usb_baud.setEnabled(not tcp)

    def save_settings_and_restart(self):
        try:
            new_conf = {
                "transport": self.combo_transport.currentText(),
                "network": {
                    "host": self.edit_host.text(),
                    "port": int(self.edit_port.text())
                },
                "usb": {
                    "port": self.edit_usb_port.text(),
                    "baudrate": int(self.edit_usb_baud.text() or 0)
                },
                "serial": {
                    "port": self.edit_serial.text(),
                    "baudrate": int(self.edit_baud.text())
                }
            }
            if cfg.save_settings(new_conf):
                print("♻ Redémarrage de l'application...")
                # re‑launch using -m to avoid issues with spaces in the
                # working directory path (sys.argv may be split at spaces).
                # keep the same environment and arguments apart from the
                # module name which we explicitly specify.
                os.execl(sys.executable,
                         sys.executable,
                         "-m",
                         "Projet_ZZ2.ui.main")
        except ValueError:
            QtWidgets.QMessageBox.critical(self, "Erreur", "Veuillez entrer des valeurs numériques valides.")

    def launch_scan(self, config_file):
        # convert bare filenames to the config directory
        if not os.path.isabs(config_file):
            config_file = config_path(config_file)
        if not os.path.exists(config_file):
            print(f"❌ Erreur : {config_file} introuvable")
            return
        if self.ser is None:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Le port série n'est pas connecté. Impossible de scanner.")
            return
        acq_mode = "average" if self.combo_mode.currentIndex() == 0 else "raw"
        print(f"🚀 Lancement du scan | Mode: {acq_mode} | Config: {config_file}")
        state.running = True
        self.pbar.setValue(0)
        Thread(target=lambda: scan.run_sequence(config_file, self.ser, acquisition_mode=acq_mode), daemon=True).start()

    def update_ui(self):
        self.pbar.setValue(state.progress_val)
        with state.accel_lock:
            t = state.latest_theta
            p = state.latest_psi
        if t is None:
            return
        self.lbl_theta_val.setText(f"{t:+.1f}°")
        self.lbl_psi_val.setText(f"{p:+.1f}°")
        self.gimbal_3d.set_angles(t, p)
        now_time = time.time() - self.start_time
        self.time_data.append(now_time)
        self.theta_data.append(t)
        self.psi_data.append(p)
        if len(self.time_data) > 400:
            self.time_data.pop(0)
            self.theta_data.pop(0)
            self.psi_data.pop(0)
        self.theta_curve.setData(self.time_data, self.theta_data)
        self.psi_curve.setData(self.time_data, self.psi_data)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    sock, ser = None, None
    # attempt connections using configuration loaded from settings.json
    settings = cfg.load_settings()

    # accelerometer connection: TCP or USB depending on configuration
    transport = settings.get('transport', 'tcp').lower()
    if transport == 'tcp':
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((settings['network']['host'], settings['network']['port']))
            Thread(target=accel.accel_reader, args=(sock,), daemon=True).start()
            print("✅ Connecté à l'accéléromètre (TCP).")
        except Exception as e:
            print(f"❌ Erreur Réseau : {e}")
            sock = None
    else:
        # USB path: open a separate serial port for accel
        try:
            usb_port = settings.get('usb', {}).get('port', '')
            usb_baud = settings.get('usb', {}).get('baudrate', 115200)
            if usb_port:
                sock = None  # not used
                ser_acc = serial.Serial(usb_port, usb_baud, timeout=1)
                Thread(target=accel.accel_reader_serial, args=(ser_acc,), daemon=True).start()
                print("✅ Connecté à l'accéléromètre (USB).")
            else:
                raise ValueError("Port USB non spécifié")
        except Exception as e:
            print(f"❌ Erreur USB : {e}")
            sock = None

    # motor serial connection remains unchanged
    try:
        ser = serial.Serial(settings['serial']['port'], settings['serial']['baudrate'], timeout=1)
        print("✅ Connecté aux moteurs.")
    except Exception as e:
        print(f"❌ Erreur Série : {e}")
        ser = None

    # pass the object representing the accelerometer connection
    # (either TCP socket or the USB serial port) so that the UI warning
    # logic remains valid.
    accel_conn = sock if transport == 'tcp' else locals().get('ser_acc', None)
    win = MainWindow(accel_conn, ser)
    win.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
