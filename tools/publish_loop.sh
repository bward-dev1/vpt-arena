#!/bin/bash
# Runs the VPT Arena publisher every 5 minutes. Start detached, for example:
#   nohup tools/publish_loop.sh > /dev/null 2>&1 &
# Needs CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_AUTH_EMAIL and CLOUDFLARE_GLOBAL_API_KEY in the environment.
# Use --once to run a single publish in the foreground.
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-$HOME/homebrew/bin/python3}"
LOG="runs/.publish.log"
mkdir -p runs
run_once() {
  { date '+%Y-%m-%d %I:%M:%S %p'; "$PY" tools/publish_site.py; echo "exit $?"; } 2>&1 | tail -n 12 >> "$LOG"
  # keep the log small
  if [ "$(wc -l < "$LOG")" -gt 400 ]; then tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
}
if [ "$1" = "--once" ]; then "$PY" tools/publish_site.py; exit $?; fi
while true; do
  run_once
  sleep 300
done
