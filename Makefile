
- 
+ # Makefile for running the Projet_ZZ2 application
+ # This file should be placed in the parent directory of the "Projet_ZZ2" package.
+ 
+ .PHONY: run fix-permissions
+ 
+ run:
+ 	@echo "☛ launching GUI (force XCB platform)"
+ 	export QT_QPA_PLATFORM=xcb; \
+ 	python -m Projet_ZZ2.ui.main
+ 
+ # fix-permissions will read settings.json and chmod the relevant serial/usb
+ # ports. it uses Python so it automatically adapts when the port changes.
+ fix-permissions:
+ 	@echo "🔐 fixing device permissions (may require sudo)"
+ 	@python - <<'PYCODE'
+ import json, subprocess, os
+ 
+ cfg_path = os.path.join("Projet_ZZ2", "config", "settings.json")
+ try:
+     with open(cfg_path) as f:
+         cfg = json.load(f)
+ except Exception as e:
+     print(f"⚠ could not read settings.json: {e}")
+     raise SystemExit(1)
+ 
+ ports = []
+ # accelerometer usb or serial
+ if isinstance(cfg.get('usb'), dict) and cfg['usb'].get('port'):
+     ports.append(cfg['usb']['port'])
+ if isinstance(cfg.get('serial'), dict) and cfg['serial'].get('port'):
+     ports.append(cfg['serial']['port'])
+ 
+ for p in set(filter(None, ports)):
+     dev = p if p.startswith('/dev/') else f"/dev/{p}"
+     print(f"chmod 666 {dev}")
+     subprocess.run(['sudo','chmod','666',dev])
+ PYCODE
+ 