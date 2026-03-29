#!/bin/bash
# run_weekly.sh
# Called by cron every Friday at 5pm PST.
# Runs the full coaching workflow and sends the weekly email.

# Change this to wherever you put the project on your Mac
PROJECT_DIR="$HOME/coachingsessions"

cd "$PROJECT_DIR" || exit 1

# Log output to a file so you can check if something goes wrong
LOG_FILE="$PROJECT_DIR/output/run.log"
mkdir -p "$PROJECT_DIR/output"

echo "========================================" >> "$LOG_FILE"
echo "Run started: $(date)" >> "$LOG_FILE"

python3 run_weekly.py >> "$LOG_FILE" 2>&1

echo "Run finished: $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
