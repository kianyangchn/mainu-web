from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import menu as menu_routes
from app.schemas import MenuDish, MenuSection, MenuTemplate
from app.services.llm import MenuGenerationResult


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_services(monkeypatch):
    menu_routes._share_service.reset()
    menu_routes._expected_output_language = "zh-CN"

    async def fake_generate_menu_template(
        images,
        filenames,
        content_types=None,
        *,
        output_language=None,
    ) -> MenuGenerationResult:
        assert output_language == menu_routes._expected_output_language
        template = MenuTemplate(
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
        return MenuGenerationResult(template=template)

    monkeypatch.setattr(
        menu_routes._menu_service, "generate_menu_template", fake_generate_menu_template
    )
    yield
    menu_routes._share_service.reset()
    delattr(menu_routes, "_expected_output_language")


def test_home_page_renders_template():
    response = client.get("/")
    assert response.status_code == 200
    assert "One menu, zero confusion" in response.text


def test_process_menu_rejects_invalid_type():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.txt", BytesIO(b"invalid"), "text/plain"))],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type"


def test_process_menu_returns_template_without_sharing():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["template"]["sections"][0]["dishes"][0]["translated_name"]
        == "Spicy Mapo Tofu"
    )
    assert payload["detected_language"] is None
    assert "share_token" not in payload


def test_create_share_link_returns_token_and_urls():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    assert response.status_code == 200

    share_response = client.post(
        "/menu/share",
        json={"template": response.json()["template"]},
    )
    assert share_response.status_code == 200
    share_payload = share_response.json()
    assert share_payload["share_token"]
    assert share_payload["share_url"].endswith(share_payload["share_token"])
    assert share_payload["share_api_url"].endswith(share_payload["share_token"])
    assert share_payload["share_qr"].startswith("data:image/png;base64,")
    assert share_payload["share_expires_in_seconds"] > 0
    assert share_payload["share_expires_at"]


def test_get_shared_menu_returns_template():
    process = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    assert process.status_code == 200

    share_response = client.post(
        "/menu/share",
        json={"template": process.json()["template"]},
    )
    token = share_response.json()["share_token"]

    shared = client.get(f"/menu/share/{token}")
    assert shared.status_code == 200
    assert shared.json()["sections"][0]["dishes"][0]["original_name"] == "Mapo Tofu"


def test_share_view_renders_html():
    process = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    assert process.status_code == 200

    share_response = client.post(
        "/menu/share",
        json={"template": process.json()["template"]},
    )
    token = share_response.json()["share_token"]

    viewer = client.get(f"/share/{token}")
    assert viewer.status_code == 200
    assert "Spicy Mapo Tofu" in viewer.text


def test_process_menu_respects_manual_language_selection():
    menu_routes._expected_output_language = "fr"
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        data={"output_language": "fr"},
        headers={"accept-language": "zh-CN"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_language"] is None
