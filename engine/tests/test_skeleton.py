from fastapi.testclient import TestClient
from engine.api import app

def test_health_and_fixture_routes():
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/risks/R1043").json()["risk_id"] == "R1043"
    r = c.post("/pulses/P-0001/reveal").json()
    assert r["n"] >= 5
