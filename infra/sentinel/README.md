# Sentinel timers (servingz)

`lab-mosca-sentinel.timer` runs `app/sentinel/sweep.py` every minute for the hosts under `sentinel:` in
`app/data/scanners/targets.yaml` marked `local: true`. Remote hosts get a second timer (`--remote`, every 5 minutes,
one SSH call per host) once SSH from servingz to them is allowed.

    sudo cp infra/sentinel/lab-mosca-sentinel.* /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now lab-mosca-sentinel.timer
    journalctl -u lab-mosca-sentinel -n 20      # one line per host per sweep

The Zetaris tables are registered by the `-- 4. Sentinel` block of `app/zetaris/register_sources.sql`.
