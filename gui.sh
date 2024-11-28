#!/bin/bash
conda activate base

# Set your DuckDB database path
DB_PATH="./central.duckdb"
LOGS_DIR="logs"

# Session name
SESSION_NAME="my_gui_session"

# Check if the session already exists and kill it if so
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
  echo "Session $SESSION_NAME already exists. Killing the existing session."
  tmux kill-session -t $SESSION_NAME
fi 

# Create a new tmux session
tmux new-session -d -s $SESSION_NAME

# Create the first pane for live log updates
tmux split-window -h -t $SESSION_NAME:0 "tail -f $LOGS_DIR/*.json"

echo "Starting the DuckDB CLI..."

tmux split-window -v -t $SESSION_NAME:0 "watch -n 0.1 ./scripts/show_logs.sh"

# Select the first pane
tmux select-pane -t $SESSION_NAME:0

tmux attach -t $SESSION_NAME
