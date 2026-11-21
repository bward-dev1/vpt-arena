#!/bin/bash
# Pull cloud RL progress into runs/ every 4 minutes (the publish loop then pushes it to the public site).
cd "$(dirname "$0")/.." || exit 1
while true; do
  ~/homebrew/bin/python3 tools/pull_cloud.py >> runs/.pull_cloud.log 2>&1
  ~/homebrew/bin/python3 tools/deploy_vercel.py >> runs/.pull_cloud.log 2>&1   # only deploys when the front end changed
  tail -n 200 runs/.pull_cloud.log > runs/.pull_cloud.log.tmp 2>/dev/null && mv runs/.pull_cloud.log.tmp runs/.pull_cloud.log
  sleep 240
done
