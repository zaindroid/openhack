#!/bin/sh
# Run on a sentinel host as the user servingz will log in as:  sh install_probe.sh  (from infra/sentinel/README.md: the
# README command fills PROBE_B64 from app/sentinel/probe_host.py and SERVINGZ_PUBKEY from servingz ~/.ssh/id_ed25519.pub).
set -e
# Mosca sentinel: read-only probe + a forced-command key for servingz (only this probe can run with it)
if [ "$(id -u)" = 0 ]; then DIR=/opt/mosca-sentinel; RUN="python3 $DIR/probe_host.py"; SUDO="";
elif sudo -n true 2>/dev/null; then DIR=/opt/mosca-sentinel; RUN="sudo -n python3 $DIR/probe_host.py"; SUDO="sudo -n";
else DIR=$HOME/.mosca-sentinel; RUN="python3 $DIR/probe_host.py"; SUDO=""; fi
command -v python3 >/dev/null || { echo "no python3"; exit 1; }
$SUDO mkdir -p $DIR
echo "$PROBE_B64" | base64 -d | $SUDO tee $DIR/probe_host.py >/dev/null
$SUDO chmod 755 $DIR/probe_host.py
[ -n "$SUDO" ] && $SUDO chown root:root $DIR $DIR/probe_host.py || true
mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
LINE="command=\"$RUN\",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding $SERVINGZ_PUBKEY  mosca-sentinel@servingz"
grep -v "mosca-sentinel@servingz" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.mosca.tmp || true
echo "$LINE" >> ~/.ssh/authorized_keys.mosca.tmp && cat ~/.ssh/authorized_keys.mosca.tmp > ~/.ssh/authorized_keys && rm ~/.ssh/authorized_keys.mosca.tmp
echo "host=$(hostname) user=$(id -un) dir=$DIR run=$RUN keys=$(grep -c . ~/.ssh/authorized_keys) sentinel_lines=$(grep -c mosca-sentinel@servingz ~/.ssh/authorized_keys)"
$RUN | python3 -c "import sys,json;d=json.load(sys.stdin);print('probe ok root',d['root'],'ports',len(d['ports']),'files',len(d['files']),'containers',len(d['containers']),'pkgs',len(d['packages']['list']),d['probe_s'],'s')"
