from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def test_health_and_sources():
    assert c.get("/api/health").json()["status"] == "ok"
    ids = {s["id"] for s in c.get("/api/sources").json()}
    assert {"osm", "drogariasaopaulo", "drogasil"} <= ids


def test_parse_endpoint():
    j = c.get("/api/parse", params={"q": "Amplictil 25mg"}).json()
    assert j["active_ingredients"] == ["clorpromazina"] and j["dose_value"] == 25


def test_search_validation():
    assert c.post("/api/search", json={"medicine": "x"}).status_code == 422
    assert c.post("/api/search", json={"medicine": "dipirona", "sort": "foo"}).status_code == 400


def test_pwa_served():
    assert c.get("/").status_code == 200
    assert c.get("/manifest.webmanifest").status_code == 200
    assert c.get("/sw.js").status_code == 200
