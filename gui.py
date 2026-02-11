#!/usr/bin/env python3
import sys
import time
import socket
import serial
from threading import Thread
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import banc_code

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, ser):
        super().__init__()
        self.sock, self.ser = sock, ser
        self.setWindowTitle("Contrôle Banc Accéléromètre")
        self.resize(1100, 650)

        # Graphique
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.addLegend()
        self.setCentralWidget(self.plot_widget)
        self.theta_curve = self.plot_widget.plot(pen='r', name='Theta')
        self.psi_curve = self.plot_widget.plot(pen='b', name='Psi')

        self.time_data, self.theta_data, self.psi_data = [], [], []
        self.start_time = time.time()

        self.init_ui()
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(50)

    def init_ui(self):
        dock = QtWidgets.QDockWidget("Commandes", self)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)

        # Scans
        layout.addWidget(QtWidgets.QLabel("<b>LANCEMENT</b>"))
        for m, c in [("Standard", "config_standard.json"), ("Rapide", "config_rapide.json"), ("Lent", "config_lent.json")]:
            btn = QtWidgets.QPushButton(f"Scan {m}")
            btn.clicked.connect(lambda chk, conf=c: self.launch_scan(conf))
            layout.addWidget(btn)

        layout.addSpacing(20)

        # Flux (Pause / Reprise)
        layout.addWidget(QtWidgets.QLabel("<b>FLUX DU SCAN</b>"))
        
        self.pause_btn = QtWidgets.QPushButton("STOP / PAUSE")
        self.pause_btn.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; height: 40px;")
        self.pause_btn.clicked.connect(self.action_pause)
        layout.addWidget(self.pause_btn)

        self.resume_btn = QtWidgets.QPushButton("CONTINUE")
        self.resume_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; height: 40px;")
        self.resume_btn.clicked.connect(self.action_resume)
        self.resume_btn.setEnabled(False)
        layout.addWidget(self.resume_btn)

        layout.addSpacing(10)
        
        self.abort_btn = QtWidgets.QPushButton("ABANDONNER LE SCAN")
        self.abort_btn.clicked.connect(self.action_abort)
        layout.addWidget(self.abort_btn)

        layout.addStretch()
        self.status_label = QtWidgets.QLabel("Système Prêt")
        layout.addWidget(self.status_label)
        dock.setWidget(container)

    def action_pause(self):
        banc_code.paused = True
        self.resume_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.status_label.setText("⏸ PAUSE - Moteurs stoppés")
        self.status_label.setStyleSheet("color: orange;")

    def action_resume(self):
        banc_code.paused = False
        self.resume_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.status_label.setText("▶ REPRISE...")
        self.status_label.setStyleSheet("color: blue;")

    def action_abort(self):
        banc_code.paused = True
        banc_code.running = False
        self.status_label.setText("🛑 ABANDON")
        self.status_label.setStyleSheet("color: red;")

    def launch_scan(self, config):
        banc_code.running = True
        banc_code.paused = False
        self.resume_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.status_label.setText(f"Scan en cours: {config}")
        Thread(target=lambda: banc_code.run_sequence(config, self.ser), daemon=True).start()

    def update_plot(self):
        with banc_code.accel_lock:
            t, p = banc_code.latest_theta, banc_code.latest_psi
        if t is not None:
            now = time.time() - self.start_time
            self.time_data.append(now)
            self.theta_data.append(t)
            self.psi_data.append(p)
            if len(self.time_data) > 400:
                self.time_data.pop(0); self.theta_data.pop(0); self.psi_data.pop(0)
            self.theta_curve.setData(self.time_data, self.theta_data)
            self.psi_curve.setData(self.time_data, self.psi_data)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((banc_code.HOST, banc_code.PORT))
    ser = serial.Serial(banc_code.SERIAL_PORT, banc_code.BAUDRATE, timeout=1)
    
    Thread(target=banc_code.accel_reader, args=(sock,), daemon=True).start()
    
    win = MainWindow(sock, ser)
    win.show()
    sys.exit(app.exec_())