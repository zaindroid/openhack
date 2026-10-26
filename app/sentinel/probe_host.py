"""Sentinel host probe: one read-only snapshot of a host the owner operates, printed as JSON.

Standard library only, so the same file runs on any of the owner's hosts (`sudo -n python3 - < probe_host.py`). It reads;
it never writes, kills, blocks or reconfigures anything. Containers are read from `docker inspect` metadata only:
nothing runs inside a container and no container file is opened.

  ports       listening TCP/UDP sockets (ss), with the owning process name
  auth        sshd journal of the last SINCE minutes: failed attempts per source, accepted logins (user, source, method)
  files       sha256 of the files an intruder edits to stay: sshd config, accounts, sudoers, cron, systemd units,
              authorized_keys, ld.so.preload, cloudflared and Coolify proxy config
  units       enabled systemd services and timers
  procs       host processes whose executable lives in /tmp, /dev/shm or /var/tmp, or was deleted after start
              (host mount namespace only, so container processes are not looked at)
  containers  name, image, privileged, host network / pid, added capabilities, docker.sock or / mounted, public ports
  packages    dpkg name + version (for the CVE check), and the OS release"""
from __future__ import annotations
import glob, hashlib, json, os, re, socket, subprocess, time

SINCE = int(os.environ.get("SENTINEL_SINCE_MIN", "6"))
FILES = ["/etc/ssh/sshd_config", "/etc/ssh/sshd_config.d/*", "/etc/passwd", "/etc/group", "/etc/shadow", "/etc/sudoers",
         "/etc/sudoers.d/*", "/etc/crontab", "/etc/cron.d/*", "/var/spool/cron/crontabs/*", "/etc/systemd/system/*.service",
         "/etc/systemd/system/*.timer", "/etc/ld.so.preload", "/etc/rc.local", "/root/.ssh/authorized_keys",
         "/home/*/.ssh/authorized_keys", "/etc/cloudflared/config.yml", "/data/coolify/proxy/dynamic/*.yaml",
         "/data/coolify/proxy/dynamic/*.yml", "/data/coolify/proxy/docker-compose.yml"]


def sh(cmd: list[str], timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, text=True, errors="replace").stdout
    except Exception:
        return ""


def ports() -> list[dict]:
    out = []
    for ln in sh(["ss", "-H", "-ltunp"]).splitlines():
        f = ln.split()
        if len(f) < 5:
            continue
        addr, _, port = f[4].rpartition(":")
        proc = re.search(r'\(\("([^"]+)"', ln)
        out.append({"proto": f[0], "addr": addr.strip("[]"), "port": int(port) if port.isdigit() else port, "proc": proc.group(1) if proc else ""})
    return sorted({(p["proto"], p["addr"], p["port"]): p for p in out}.values(), key=lambda p: (p["proto"], str(p["port"]), p["addr"]))


def auth() -> dict:
    text = sh(["journalctl", "-q", "--no-pager", "-o", "short-iso", "--since", f"-{SINCE}min", "_COMM=sshd"])
    fails: dict[str, int] = {}
    accepted = []
    for ln in text.splitlines():
        m = re.search(r"(?:Failed \S+ for (?:invalid user )?\S+|Invalid user \S*|authentication failure).*? from (\S+)", ln)
        if m:
            fails[m.group(1)] = fails.get(m.group(1), 0) + 1
            continue
        m = re.search(r"Accepted (\S+) for (\S+) from (\S+) port \d+(?:.*?(SHA256:\S+))?", ln)
        if m:
            accepted.append({"t": ln.split()[0], "method": m.group(1), "user": m.group(2), "src": m.group(3), "key": m.group(4) or ""})
    return {"since_min": SINCE, "failed": fails, "accepted": accepted}


def files() -> dict:
    out = {}
    for pat in FILES:
        for p in sorted(glob.glob(pat)):
            try:
                with open(p, "rb") as f:
                    out[p] = hashlib.sha256(f.read()).hexdigest()
            except (IsADirectoryError, PermissionError, FileNotFoundError):
                pass
    return out


def units() -> list[str]:
    return sorted(ln.split()[0] for ln in sh(["systemctl", "list-unit-files", "--state=enabled", "--no-legend", "--no-pager",
                                               "--type=service,timer"]).splitlines() if ln.strip())


def procs() -> list[dict]:
    try:
        mine = os.readlink("/proc/1/ns/mnt")
    except OSError:
        return []
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if os.readlink(d + "/ns/mnt") != mine:
                continue                       # another mount namespace: a container's process, not looked at
            exe = os.readlink(d + "/exe")
        except OSError:
            continue
        if exe.startswith(("/tmp/", "/dev/shm/", "/var/tmp/")) or exe.endswith(" (deleted)"):
            name = open(d + "/comm").read().strip() if os.path.exists(d + "/comm") else ""
            out.append({"pid": int(d[6:]), "exe": exe, "comm": name})
    return out


def containers() -> list[dict]:
    ids = sh(["docker", "ps", "-q"]).split()
    if not ids:
        return []
    try:
        js = json.loads(sh(["docker", "inspect", *ids], timeout=60) or "[]")
    except ValueError:
        return []
    out = []
    for c in js:
        hc = c.get("HostConfig") or {}
        mounts = [m.get("Source", "") for m in c.get("Mounts") or []]
        pub = sorted({f"{b.get('HostIp') or '0.0.0.0'}:{b.get('HostPort')}" for bs in (hc.get("PortBindings") or {}).values() for b in (bs or [])
                      if (b.get("HostIp") or "0.0.0.0") in ("0.0.0.0", "::", "")})
        out.append({"name": c.get("Name", "").lstrip("/"), "image": (c.get("Config") or {}).get("Image", ""), "image_id": c.get("Image", "")[:19],
                    "privileged": bool(hc.get("Privileged")), "net_host": hc.get("NetworkMode") == "host", "pid_host": hc.get("PidMode") == "host",
                    "cap_add": sorted(hc.get("CapAdd") or []), "docker_sock": any(m.endswith("docker.sock") for m in mounts),
                    "root_mount": "/" in mounts, "public_ports": pub})
    return sorted(out, key=lambda c: c["name"])


def packages() -> dict:
    rel = {}
    try:
        for ln in open("/etc/os-release"):
            k, _, v = ln.strip().partition("=")
            rel[k] = v.strip('"')
    except OSError:
        pass
    pk = dict(ln.split("\t", 1) for ln in sh(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"]).splitlines() if "\t" in ln)
    return {"os": rel.get("ID", ""), "version": rel.get("VERSION_ID", ""), "list": pk,
            "sha256": hashlib.sha256(json.dumps(pk, sort_keys=True).encode()).hexdigest()}


def main() -> None:
    t0 = time.time()
    snap = {"host": socket.gethostname(), "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "root": os.geteuid() == 0,
            "ports": ports(), "auth": auth(), "files": files(), "units": units(), "procs": procs(), "containers": containers(),
            "packages": packages()}
    snap["probe_s"] = round(time.time() - t0, 2)
    print(json.dumps(snap, sort_keys=True))


if __name__ == "__main__":
    main()
