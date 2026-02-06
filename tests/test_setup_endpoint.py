import pytest

from app import app, chromium_install_state


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


ORIGINAL_ROUTES = [
    "/",
    "/api/count",
    "/api/scrape",
    "/api/pause",
    "/api/resume",
    "/api/stop",
    "/api/export-excel",
]


def _get_rules():
    return [
        r.rule for r in app.url_map.iter_rules() if not r.rule.startswith("/static")
    ]


def test_setup_page_route_exists():
    assert "/setup" in _get_rules()


def test_setup_status_route_exists():
    assert "/api/setup-status" in _get_rules()


def test_setup_page_returns_html(client):
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert b"text/html" in resp.content_type.encode()


def test_setup_status_returns_sse(client):
    chromium_install_state["status"] = "done"
    resp = client.get("/api/setup-status")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type


def test_chromium_install_state_exists():
    assert isinstance(chromium_install_state, dict)
    assert "status" in chromium_install_state
    assert "percent" in chromium_install_state
    assert "message" in chromium_install_state


def test_existing_routes_untouched():
    rules = _get_rules()
    for route in ORIGINAL_ROUTES:
        assert route in rules, f"Original route {route} is missing"
