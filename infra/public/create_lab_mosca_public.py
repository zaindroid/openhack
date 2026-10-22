"""Create (idempotently) the lab-mosca-public Coolify application on servingz and route mosca-public.zaindroid.me to it
WITHOUT Cloudflare Access: zaindroid/openhack branch idea/mosca, app/public/Dockerfile, port 8080, network
groundswell-net (alias lab-mosca-public), where it reads the private app as http://lab-mosca:8080.

The service is read-only and pseudonymised (app/public/server.py); the private app keeps its Access gate. Before the
route opens this checks that no Access application already covers the host name, so the result is what it claims.
Uses the zorc deploy helpers.  Run:  cd ~/zorc/deploy && ~/apps/openhack-mosca/.venv/bin/python \
    ~/apps/openhack-mosca/infra/public/create_lab_mosca_public.py"""
import os, sys

sys.path.insert(0, os.path.expanduser("~/zorc/deploy"))
import agent  # noqa: E402
import httpx  # noqa: E402

NAME = "lab-mosca-public"
SUB = "mosca-public"
HOST = f"{SUB}.zaindroid.me"
DESTINATION = "anxumm5olvxni6em8r3wj08p"     # Coolify StandaloneDocker on network groundswell-net (same as lab-mosca)
ENV = {"UPSTREAM": "http://lab-mosca:8080", "MAX_SUBSCRIBERS": "200"}


def main() -> int:
    h = agent._coolify_headers()
    node = agent.node_config("servingz")
    with httpx.Client(timeout=60) as c:
        acc = c.get(f"{agent.CLOUDFLARE_API}/accounts/{agent.CLOUDFLARE_ACCOUNT_ID}/access/apps", headers=agent._cloudflare_headers()).json()["result"]
        cover = [a.get("domain") for a in acc if a.get("domain") in (HOST, "*.zaindroid.me", "zaindroid.me/*")]
        print("access apps covering", HOST, ":", cover or "none (public)")
        apps = c.get(f"{agent.COOLIFY_URL}/applications", headers=h).json()
        existing = [a for a in apps if a.get("name") == NAME]
        if existing:
            uuid = existing[0]["uuid"]
            print("exists", uuid)
        else:
            r = c.post(f"{agent.COOLIFY_URL}/applications/public", headers=h, json={
                "project_uuid": agent.COOLIFY_PROJECT_UUID, "server_uuid": node["server_uuid"],
                "environment_name": agent.COOLIFY_ENVIRONMENT_NAME, "destination_uuid": DESTINATION,
                "git_repository": "https://github.com/zaindroid/openhack", "git_branch": "idea/mosca",
                "build_pack": "dockerfile", "dockerfile_location": "/app/public/Dockerfile", "name": NAME,
                "description": "Mosca public view: read-only, pseudonymised live view of lab-mosca",
                "domains": f"https://{HOST}", "ports_exposes": "8080", "limits_memory": "192m",
                "is_auto_deploy_enabled": True, "is_force_https_enabled": True,
                "health_check_enabled": True, "health_check_path": "/healthz",
                "custom_network_aliases": NAME, "instant_deploy": False})
            print("create", r.status_code, r.text[:300])
            r.raise_for_status()
            uuid = r.json()["uuid"]
        agent.set_coolify_env_vars(uuid, ENV)
        r = c.post(f"{agent.COOLIFY_URL}/deploy", headers=h, params={"uuid": uuid, "force": "false"})
        print("deploy", r.status_code, r.text[:200])
        agent.record_resource(NAME, kind="coolify-app", coolify_uuid=uuid, domains=[HOST])
    if cover:
        print("not routing: an Access app covers the host; the view would not be public")
        return 1
    try:
        agent.create_dns_record(SUB)
        print("dns: CNAME", SUB, "-> tunnel")
    except httpx.HTTPStatusError as e:
        if "already exists" not in e.response.text and "81053" not in e.response.text:
            raise
        print("dns: already exists")
    agent.add_tunnel_route(HOST)
    print("tunnel: route present -> https://localhost:443 (Traefik)")
    print("uuid", uuid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
