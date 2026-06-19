#!/usr/bin/env bash
# Wrapper des tâches planifiées SmartStock (cron).
#
# Usage : run_cron.sh <commande_manage_py> [args...]
#
# Se place dans le répertoire du projet (pour que settings.load_dotenv() lise le
# .env) et utilise le Python du virtualenv. Toute la planification (heures) reste
# dans le crontab ; ce script ne fait qu'exécuter UNE commande manage.py.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Le virtualenv s'appelle `venv` (prod VPS) ou `.venv` (local) selon l'environnement.
if [ -x "$PROJECT_DIR/venv/bin/python" ]; then
  PYTHON="$PROJECT_DIR/venv/bin/python"
elif [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON="$PROJECT_DIR/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

exec "$PYTHON" manage.py "$@"
