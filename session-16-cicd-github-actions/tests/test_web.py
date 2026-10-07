import pytest

from app.web import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_home_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"CGPA Calculator" in res.data


def test_health(client, monkeypatch):
    monkeypatch.setenv("BUILD_SHA", "abc123def4567890")
    data = client.get("/health").get_json()
    assert data["status"] == "ok"
    assert data["build"] == "abc123def456"


def test_sgpa_endpoint(client):
    res = client.post("/api/sgpa", json={"courses": [{"grade": "A+", "credits": 4},
                                                     {"grade": "B", "credits": 2}]})
    assert res.status_code == 200
    assert res.get_json() == {"sgpa": 8.0}


def test_sgpa_endpoint_validates_input(client):
    res = client.post("/api/sgpa", json={"courses": [{"grade": "X", "credits": 4}]})
    assert res.status_code == 400
    assert "unknown grade" in res.get_json()["error"]


def test_cgpa_endpoint(client):
    res = client.post("/api/cgpa", json={"semesters": [{"sgpa": 8.0, "credits": 20},
                                                       {"sgpa": 9.0, "credits": 30}]})
    assert res.get_json() == {"cgpa": 8.6, "percentage": 81.7}
