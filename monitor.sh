#!/bin/bash

# Environment variable for filtering
TRADER_ID=${TRADER_ID:-""}  # Defaults to empty if not set
LOGS_DIR=${LOGS_DIR:-"./logs"}  # Default path to logs directory
LOG_QUERY_LIMIT=20  # Number of logs to display

# Function to query DuckDB and display logs
display_logs() {
    echo "Live Logs Viewer (Filtering by TRADER_ID: ${TRADER_ID:-None})"
    echo "----------------------------------------"

    # DuckDB query using JSON log files and filtering by trader_id
    duckdb -c "
    SELECT * FROM read_json_auto('${LOGS_DIR}/*.json')
    ${TRADER_ID:+WHERE trader_id in '${TRADER_ID}'}
    ORDER BY timestamp DESC
    LIMIT ${LOG_QUERY_LIMIT};
    "
}

# Initial display of logs
display_logs

# Monitor for changes in the logs directory and update the display
#fswatch -o "$LOGS_DIR" | while read -r; do
#    clear
#    display_logs
#done
