import asyncio
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routes import menu as menu_routes
from app.schemas import MenuDish, MenuSection, MenuTemplate
from app.services.llm import MenuProcessingArtifacts
from app.services.tips import Tip


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_services(monkeypatch):
    menu_routes._share_service.reset()
    menu_routes._expected_output_language = "zh-CN"

    async def fake_process_menu(
        images,
        filenames,
        content_types=None,
        *,
        output_language=None,
        include_quick_suggestion=True,
        suggestion_timeout=None,
    ) -> MenuProcessingArtifacts:  # noqa: ARG001
        assert output_language == menu_routes._expected_output_language
        menu_routes._last_uploads = [bytes(blob) for blob in images]
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
        quick_suggestion = (
            "Try the Mapo Tofu tonight!"
            if include_quick_suggestion
            else ""
        )
        return MenuProcessingArtifacts(
            template=template,
            quick_suggestion=quick_suggestion,
        )

    monkeypatch.setattr(
        menu_routes._menu_service,
        "process_menu",
        fake_process_menu,
    )
    yield
    menu_routes._share_service.reset()
    delattr(menu_routes, "_expected_output_language")
    if hasattr(menu_routes, "_last_uploads"):
        delattr(menu_routes, "_last_uploads")


def test_home_page_renders_template():
    response = client.get("/")
    assert response.status_code == 200
    assert "Make it easy to order" in response.text


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
    assert payload["quick_suggestion"] == "Try the Mapo Tofu tonight!"
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


def test_share_view_respects_browser_language():
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

    viewer = client.get(
        f"/share/{token}", headers={"Accept-Language": "zh-CN,zh;q=0.9"}
    )
    assert viewer.status_code == 200
    assert "菜单准备就绪" in viewer.text
    assert "分享此菜单" in viewer.text


def test_process_menu_respects_manual_language_selection():
    menu_routes._expected_output_language = "Français"
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        data={"output_language": "fr"},
        headers={"accept-language": "zh-CN"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_language"] is None


def test_process_menu_times_out(monkeypatch):
    async def slow_process_menu(
        images,
        filenames,
        content_types=None,
        *,
        output_language=None,
        include_quick_suggestion=True,
        suggestion_timeout=None,
    ):  # noqa: ARG001
        await asyncio.sleep(0.05)
        return MenuProcessingArtifacts(
            template=MenuTemplate(sections=[]),
            quick_suggestion="",
        )

    monkeypatch.setattr(
        menu_routes, "_MENU_PROCESSING_TIMEOUT_SECONDS", 0.01, raising=False
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "process_menu",
        slow_process_menu,
    )

    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "Menu processing took too long. Please try again."


def test_process_menu_downscales_large_images():
    img = Image.new("RGB", (3000, 2000), color="white")
    original_bytes = BytesIO()
    img.save(original_bytes, format="JPEG", quality=95)
    raw = original_bytes.getvalue()

    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(raw), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )

    assert response.status_code == 200
    assert hasattr(menu_routes, "_last_uploads")
    processed = menu_routes._last_uploads[0]
    assert len(processed) < len(raw)

    with Image.open(BytesIO(processed)) as downsized:
        downsized.load()
        assert max(downsized.size) <= 1280


def test_stream_menu_tips(monkeypatch):
    async def fake_get_tips(*args, limit=6, **kwargs):  # noqa: ARG001
        return [
            Tip(
                title="Pad Thai",
                body="Sweet, tangy rice noodles popular across Bangkok night markets.",
                image_url="https://example.com/pad-thai.jpg",
                source_name="Test Source",
                source_url="https://example.com",
            )
        ]

    monkeypatch.setattr(menu_routes._tip_service, "get_tips", fake_get_tips)

    with client.stream(
        "GET",
        "/menu/tips",
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        body = "".join(chunk for chunk in response.iter_text())

    assert "event: tip" in body
    assert "Pad Thai" in body
    assert "event: complete" in body
