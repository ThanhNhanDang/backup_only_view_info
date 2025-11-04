#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Checking for existing flask_server.py process..."

PIDS=$(ps aux | grep '[f]lask_server.py' | awk '{print $2}')

if [ -n "$PIDS" ]; then
  echo "Flask server is running with PIDs:"
  echo "$PIDS"
  echo "Killing all matching processes..."
  for PID in $PIDS; do
    kill -9 "$PID"
    echo "Killed process $PID"
  done
else
  echo "No existing Flask server process found."
fi

# VENV_PATH="$SCRIPT_DIR/venv"

# if [ -f "$VENV_PATH/bin/python" ]; then
#   PYTHON="$VENV_PATH/bin/python"
#   echo "Using virtual environment Python: $PYTHON"
# else
#   echo "Virtual environment not found at $VENV_PATH"
#   exit 1
# fi

# echo "Starting Flask server..."
# cd "$SCRIPT_DIR"
# nohup "$PYTHON" -u "$SCRIPT_DIR/flask_server.py" > "$SCRIPT_DIR/flask.log" 2>&1 &

# echo "Flask server restarted at port 8080 and running in background."
