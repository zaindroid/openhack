# Sentinel timers and remote hosts (servingz)

`lab-mosca-sentinel.timer` runs `app/sentinel/sweep.py` every minute for the hosts under `sentinel:` in
`app/data/scanners/targets.yaml` marked `local: true`.

    sudo cp infra/sentinel/lab-mosca-sentinel.* /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now lab-mosca-sentinel.timer
    journalctl -u lab-mosca-sentinel -n 20      # one line per host per sweep

## Remote hosts (hostinger-vps, ged25-ki)

The owner installs, on each host, the read-only probe and one `authorized_keys` line for servingz's key, pinned to a
forced command (`no-pty`, no forwarding): with that key servingz can only run the probe and read its JSON.

    # on servingz, build the filled script once
    PROBE_B64=$(base64 -w0 app/sentinel/probe_host.py) SERVINGZ_PUBKEY="$(cat ~/.ssh/id_ed25519.pub)" \
      envsubst '$PROBE_B64 $SERVINGZ_PUBKEY' < infra/sentinel/install_probe.sh > /tmp/install_probe.sh
    # then, from a machine that can already log in to the host (one SSH call; hostinger has fail2ban)
    ssh root@<hostinger> 'sh -s' < install_probe.sh
    ssh zulhaq@<ged25-ki> 'sh -s' < install_probe.sh

servingz pins both host keys in `~/.ssh/known_hosts` (copied from the owner's machine) and has `hostinger-vps` /
`ged25-ki` aliases in `~/.ssh/config`. After the install, enable the 5-minute remote timer:

    sudo cp infra/sentinel/lab-mosca-sentinel-remote.* /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now lab-mosca-sentinel-remote.timer

The first sweep of each host sets its baseline; the sentinel then reports its own new authorized_keys line on the
next change only if it changes again. The Zetaris tables are registered by the `-- 4. Sentinel` block of
`app/zetaris/register_sources.sql`.
