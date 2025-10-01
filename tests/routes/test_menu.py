from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import menu as menu_routes
from app.schemas import MenuDish, MenuSection, MenuTemplate


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_services(monkeypatch):
    menu_routes._share_service.reset()

    async def fake_generate_menu_template(images, filenames, content_types=None):
        return MenuTemplate(
            sections=[
                MenuSection(
                    title="Chef's Picks",
                    dishes=[
                        MenuDish(
                            original_name="Mapo Tofu",
                            translated_name="Spicy Mapo Tofu",
                            description="Classic Sichuan tofu",
                            price="12",
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        menu_routes._menu_service, "generate_menu_template", fake_generate_menu_template
    )
    yield
    menu_routes._share_service.reset()


def test_home_page_renders_template():
    response = client.get("/")
    assert response.status_code == 200
    assert "Capture or upload menu photos" in response.text


def test_process_menu_rejects_invalid_type():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.txt", BytesIO(b"invalid"), "text/plain"))],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type"


def test_process_menu_returns_share_token():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
    )
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["template"]["sections"][0]["dishes"][0]["translated_name"]
        == "Spicy Mapo Tofu"
    )
    assert payload["share_token"]
    assert payload["share_url"].endswith(payload["share_token"])


def test_get_shared_menu_returns_template():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
    )
    token = response.json()["share_token"]

    shared = client.get(f"/menu/share/{token}")
    assert shared.status_code == 200
    assert shared.json()["sections"][0]["dishes"][0]["original_name"] == "Mapo Tofu"


def test_share_view_renders_html():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
    )
    token = response.json()["share_token"]

    viewer = client.get(f"/share/{token}")
    assert viewer.status_code == 200
    assert "Spicy Mapo Tofu" in viewer.text
