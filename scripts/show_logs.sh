#!/bin/bash

# wrap it in a function and 
duckdb -c "SELECT * FROM read_json_auto('./logs/*.json') ORDER BY timestamp DESC LIMIT 30;"