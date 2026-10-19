#!/usr/bin/env bash
# Push main and every idea branch. Usage: scripts/push_all.sh [remote-url]
set -euo pipefail
cd "$(dirname "$0")/.."
if [ $# -ge 1 ]; then git remote remove origin 2>/dev/null || true; git remote add origin "$1"; fi
git push -u origin main
for b in $(git for-each-ref --format='%(refname:short)' refs/heads/idea/); do git push -u origin "$b"; done
git branch -a
