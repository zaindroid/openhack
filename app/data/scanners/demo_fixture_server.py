"""The demo fixture: a throwaway TLS endpoint on servingz that starts classical-only, so the video can show a real LATE
asset being found, approved, fixed and re-scanned. Runs in the container lab-mosca-demo-tls (see demo_fixture.sh).

  :8443  openssl s_server, RSA-2048 self-signed certificate made at start (never reused), groups X25519:P-256
  :8080  control: GET /state; POST /apply {"groups": "X25519MLKEM768:X25519"} with "Authorization: Bearer
         $DEMO_APPLY_TOKEN" restarts s_server with that group list. Only the two lists in GROUPS are accepted.

Nothing else on the host is touched; the container is on groundswell-net with no host port."""
from __future__ import annotations
import datetime, hmac, json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLASSICAL, HYBRID = "X25519:P-256", "X25519MLKEM768:X25519"
GROUPS = {CLASSICAL, HYBRID}
TOKEN = os.environ.get("DEMO_APPLY_TOKEN", "")
D = "/tmp/fixture"
state = {"groups": CLASSICAL, "changed_at": None, "proc": None}
lock = threading.Lock()


def make_cert() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    os.makedirs(D, exist_ok=True)
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "lab-mosca-demo-tls")])
    now = datetime.datetime.now(datetime.timezone.utc)
    c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30)).sign(k, hashes.SHA256()))
    open(f"{D}/key.pem", "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    open(f"{D}/cert.pem", "wb").write(c.public_bytes(serialization.Encoding.PEM))


def start(groups: str) -> None:
    if state["proc"]:
        state["proc"].terminate(); state["proc"].wait(10)
    state["proc"] = subprocess.Popen(["openssl", "s_server", "-accept", "8443", "-cert", f"{D}/cert.pem", "-key", f"{D}/key.pem",
                                      "-groups", groups, "-www", "-quiet"], stdin=subprocess.DEVNULL)
    state["groups"] = groups
    print(f"s_server :8443 groups {groups}", flush=True)


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def _state(self) -> dict:
        return {"groups": state["groups"], "changed_at": state["changed_at"], "cert": "RSA-2048 self-signed, CN=lab-mosca-demo-tls"}

    def do_GET(self):
        self._send(200, self._state()) if self.path == "/state" else self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/apply":
            return self._send(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("authorization", ""), f"Bearer {TOKEN}"):
            return self._send(401, {"error": "bad token"})
        try:
            groups = json.loads(self.rfile.read(int(self.headers.get("content-length", "0")) or 0) or b"{}").get("groups")
        except ValueError:
            groups = None
        if groups not in GROUPS:
            return self._send(400, {"error": f"groups must be one of {sorted(GROUPS)}"})
        with lock:
            start(groups)
            state["changed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"applied groups {groups} at {state['changed_at']}", flush=True)
        self._send(200, self._state())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if len(TOKEN) < 24:
        sys.exit("DEMO_APPLY_TOKEN (>= 24 chars) required")
    make_cert()
    start(CLASSICAL)
    ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
