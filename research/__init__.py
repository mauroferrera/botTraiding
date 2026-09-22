"""Pipeline de research (offline/backtesting/calibración).

Deliberadamente SEPARADO del runtime: app/agent/watcher no importan nada de aquí.
Las dependencias obligatorias (numpy, PyYAML) ya viven en requirements.txt; las
opcionales (p. ej. vectorbt) van en research/requirements-research.txt.
"""