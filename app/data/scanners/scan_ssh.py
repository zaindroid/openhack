"""SSH inventory of your own hosts: host-key algorithms via `ssh-keyscan` and the server's key-exchange offer read
straight from its unencrypted SSH_MSG_KEXINIT (RFC 4253 §7.1). No user name is sent and no authentication is
attempted, so nothing lands in auth logs or fail2ban.

negotiated_kex = the first algorithm in the local OpenSSH client's KexAlgorithms that the server also offers (what
`ssh` from this machine would use); the note lists whether the server offers mlkem768x25519-sha256 /
sntrup761x25519-sha512 at all."""
from __future__ import annotations
import socket, struct, subprocess
from common import append, log_probe, targets

PQ = ("mlkem768x25519-sha256", "sntrup761x25519-sha512", "sntrup761x25519-sha512@openssh.com")


def server_kexinit(host: str, port: int) -> tuple[str, list[str], list[str]]:
    with socket.create_connection((host, port), timeout=8) as s:
        f = s.makefile("rb")
        banner = b""
        while not banner.startswith(b"SSH-"):
            banner = f.readline(512)
            if not banner:
                raise ConnectionError("no SSH banner")
        s.sendall(b"SSH-2.0-mosca_inventory\r\n")
        plen, padlen = struct.unpack(">IB", f.read(5))
        payload = f.read(plen - 1)[: plen - 1 - padlen]
    if payload[0] != 20:
        raise ValueError(f"expected KEXINIT, got message {payload[0]}")
    off, lists = 17, []
    for _ in range(2):          # kex_algorithms, server_host_key_algorithms
        n = struct.unpack(">I", payload[off:off + 4])[0]
        lists.append(payload[off + 4:off + 4 + n].decode().split(","))
        off += 4 + n
    return banner.decode(errors="ignore").strip(), lists[0], lists[1]


def client_order(host: str, option: str) -> list[str]:
    out = subprocess.run(["ssh", "-G", host], capture_output=True, timeout=10).stdout.decode()
    for ln in out.splitlines():
        if ln.startswith(option + " "):
            return ln.split(None, 1)[1].split(",")
    return []


def key_sizes(keyscan_out: str) -> dict[str, int]:
    """bits per host-key type, from ssh-keygen -l over the keyscan lines (e.g. {'RSA': 3072, 'ED25519': 256})."""
    out = subprocess.run(["ssh-keygen", "-lf", "-"], input=keyscan_out.encode(), capture_output=True, timeout=10).stdout.decode()
    return {ln.rsplit("(", 1)[1].rstrip(")"): int(ln.split()[0]) for ln in out.splitlines() if "(" in ln}


def main() -> None:
    rows = []
    for t in targets().get("ssh", []):
        host, port = t["host"], int(t.get("port", 22))
        try:
            banner, kex_offer, hk_offer = server_kexinit(host, port)
        except Exception as e:
            log_probe("ssh_scan", f"{host}:{port}", f"no SSH handshake: {type(e).__name__}: {str(e)[:100]}")
            print(host, "unreachable:", type(e).__name__)
            continue
        keys = subprocess.run(["ssh-keyscan", "-p", str(port), "-T", "8", host], capture_output=True, timeout=30).stdout.decode(errors="ignore")
        algs = sorted({ln.split()[1] for ln in keys.splitlines() if ln and not ln.startswith("#") and len(ln.split()) > 2})
        kex = next((k for k in client_order(host, "kexalgorithms") if k in kex_offer), "none in common")
        pq_offer = [k for k in kex_offer if k in PQ]
        used_hk = next((a for a in client_order(host, "hostkeyalgorithms") if a in hk_offer), "")
        hk = "Ed25519" if "ed25519" in used_hk else "ECDSA" if "ecdsa" in used_hk else "RSA" if ("rsa" in used_hk) else "unknown"
        bits = key_sizes(keys).get({"Ed25519": "ED25519", "ECDSA": "ECDSA", "RSA": "RSA"}.get(hk, ""), "")
        rows.append({"name": t.get("name", host), "host": host, "port": port, "kind": "ssh", "algorithm": hk, "key_bits": bits,
                     "purpose": "both", "negotiated_kex": kex, "negotiated_sig": ",".join(algs), "data_class": t.get("data_class", "credentials"),
                     "note": f"{banner}; host key used: {used_hk}; all host keys: {','.join(f'{k}-{v}' for k, v in key_sizes(keys).items())}; server PQ kex offered: {','.join(pq_offer) or 'none'}"})
        print(host, banner, kex, "pq offered:", pq_offer, algs)
    print("written:", append(rows, "ssh_scan"))


if __name__ == "__main__":
    main()
