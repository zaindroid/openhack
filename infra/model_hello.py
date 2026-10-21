#!/usr/bin/env python3
"""Smoke-test one model route for both roles (reason, fast): which route and host answered, the model id the server
reports, latency, tokens/s. Uses the same endpoint resolution as whycore.model (see its docstring).

  python infra/model_hello.py --route nim                 # NIM_BASE_URL (default https://integrate.api.nvidia.com/v1), NIM_API_KEY
  python infra/model_hello.py --route meterless           # METERLESS_BASE_URL, METERLESS_API_KEY, METERLESS_REASON/FAST
  python infra/model_hello.py --route local               # LOCAL_REASON_BASE_URL/KEY, LOCAL_FAST_BASE_URL/KEY (or LOCAL_BASE_URL)
  python infra/model_hello.py --route nim --record docs/sponsors.md     # also upsert the rows in that file's results table
Variables come from the environment, then infra/.env. Keys are never printed. Exit 1 if any role fails."""
from __future__ import annotations
import argparse, os, re, sys, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PROMPT = ("In about 120 words, explain to an engineering manager why data with a 10-year confidentiality requirement, "
          "protected today by classical key exchange, is already a post-quantum migration problem. Plain prose.")
TABLE_HDR = "| route | role | host | model (as reported) | latency s | completion tokens | tokens/s | measured (UTC) |"


def load_env() -> None:
    p = os.path.join(ROOT, "infra", ".env")
    if os.path.exists(p):
        for line in open(p).read().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def hello(route: str, role: str) -> dict:
    import httpx
    from whycore.model import resolve
    from whycore.settings import settings
    e = resolve(role, route)
    row = {"route": route, "role": role, "host": e.host or "(unset)", "model": e.model, "ok": False}
    if not e.base:
        row["error"] = f"no base URL for route {route} ({route.upper()}_BASE_URL or {route.upper()}_{role.upper()}_BASE_URL)"
        return row
    try:
        m = httpx.get(e.base + "/models", headers=e.headers(), timeout=20)
        row["models_status"] = m.status_code
        body = {"model": e.model, "temperature": 0.2, "max_tokens": 400, "messages": [{"role": "user", "content": PROMPT}]}
        if settings.model_thinking == "off" and route != "meterless":
            body["chat_template_kwargs"] = {"enable_thinking": False}
        t0 = time.time()
        r = httpx.post(e.base + "/chat/completions", json=body, headers=e.headers(), timeout=180)
        dt = time.time() - t0
        r.raise_for_status()
        js = r.json()
        text = (js["choices"][0]["message"].get("content") or "").strip()
        ct = (js.get("usage") or {}).get("completion_tokens") or 0
        row.update({"ok": bool(text), "model": js.get("model") or e.model, "latency_s": round(dt, 2), "completion_tokens": ct,
                    "tokens_s": round(ct / dt, 1) if dt and ct else None, "sample": text[:160].replace("\n", " ")})
        if not text:
            row["error"] = "empty content"
    except Exception as ex:
        row["error"] = f"{type(ex).__name__}: {str(ex)[:160]}"
    return row


def record(path: str, rows: list[dict]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    lines = open(path).read().splitlines() if os.path.exists(path) else ["# Sponsors", "", "## Model routes (measured by infra/model_hello.py)", "", TABLE_HDR, "|---|---|---|---|---|---|---|---|"]
    if TABLE_HDR not in lines:
        lines += ["", "## Model routes (measured by infra/model_hello.py)", "", TABLE_HDR, "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [r["route"], r["role"], r["host"], r["model"], str(r.get("latency_s", "–")), str(r.get("completion_tokens", "–")),
                 str(r.get("tokens_s", "–")), now if r["ok"] else f"FAILED {now}: {r.get('error', '')[:80]}"]
        new = "| " + " | ".join(cells) + " |"
        pat = re.compile(rf"^\| {re.escape(r['route'])} \| {r['role']} \|")
        idx = next((i for i, l in enumerate(lines) if pat.match(l)), None)
        if idx is None:
            sep = lines.index(TABLE_HDR) + 1
            end = sep + 1
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            lines.insert(end, new)
        else:
            lines[idx] = new
    open(path, "w").write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True, choices=["local", "meterless", "nim"])
    ap.add_argument("--record", help="markdown file whose results table gets these rows (upsert by route+role)")
    a = ap.parse_args()
    load_env()
    rows = [hello(a.route, role) for role in ("reason", "fast")]
    for r in rows:
        status = "OK " if r["ok"] else "FAIL"
        print(f"{status} route={r['route']} role={r['role']} host={r['host']} model={r['model']} "
              f"latency={r.get('latency_s')}s tokens={r.get('completion_tokens')} tok/s={r.get('tokens_s')}"
              + (f" error={r['error']}" if r.get("error") else f"\n     {r.get('sample', '')}"))
    if a.record:
        record(a.record, rows)
        print("recorded in", a.record)
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
