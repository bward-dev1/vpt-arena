#!/bin/bash
# Push the current HEAD tree to the public repo as one new commit (local history stays private).
# Refuses if a private word from configs/scrub.local.json appears in tracked files.
set -euo pipefail
cd "$(dirname "$0")/.."
STATE=.git/public-head
words=$(python3 -c "import json;print('|'.join(json.load(open('configs/scrub.local.json'))['words']))")
if git grep -n -i -w -E "$words" -- . ':!third_party' ':!tools/push_public.sh'; then echo "refusing: private words found"; exit 1; fi
T=$(git rev-parse 'HEAD^{tree}')
P=$(cat "$STATE" 2>/dev/null || git ls-remote public refs/heads/main | cut -f1)
MSG=$(git log -1 --format=%s)
C=$(printf '%s\n' "$MSG" | GIT_AUTHOR_NAME=bward-dev1 GIT_AUTHOR_EMAIL=blwlego@gmail.com \
    GIT_COMMITTER_NAME=bward-dev1 GIT_COMMITTER_EMAIL=blwlego@gmail.com git commit-tree "$T" -p "$P")
git push -q public "${C}:refs/heads/main"
echo "$C" > "$STATE"
echo "pushed $C"
