import asyncio
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routes import menu as menu_routes
from app.schemas import MenuDish, MenuSection, MenuTemplate
from app.services.llm import MenuGenerationResult, MenuProcessingArtifacts
from app.services.tips import Tip


client = TestClient(app)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def reset_services(monkeypatch):
    menu_routes._share_service.reset()
    menu_routes._upload_session_service.reset()
    menu_routes._expected_output_language = "zh-CN"
    menu_routes._upload_call_count = 0

    async def fake_upload_images(
        images,
        filenames,
        content_types=None,
    ):
        menu_routes._last_uploads = [bytes(blob) for blob in images]
        menu_routes._upload_call_count += 1
        return [f"file-{index}" for index in range(len(images))]

    async def fake_generate_template_from_file_ids(
        file_ids,
        *,
        output_language=None,
    ) -> MenuGenerationResult:
        assert output_language == menu_routes._expected_output_language
        template = MenuTemplate(
            sections=[
                MenuSection(
                    translated_section_name="Chef's Picks",
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

    async def fake_generate_quick_suggestions_from_file_ids(
        file_ids,
        *,
        output_language=None,
    ) -> str:
        assert output_language == menu_routes._expected_output_language
        return "Try the Mapo Tofu tonight!"

    async def fake_generate_quick_suggestions(
        images,
        filenames,
        content_types=None,
        *,
        output_language=None,
    ):
        menu_routes._last_uploads = [bytes(blob) for blob in images]
        return "Try the Mapo Tofu tonight!"

    async def fake_delete_files(file_ids):
        menu_routes._deleted_file_ids = list(file_ids)

    monkeypatch.setattr(
        menu_routes._menu_service,
        "upload_images",
        fake_upload_images,
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "generate_template_from_file_ids",
        fake_generate_template_from_file_ids,
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "generate_quick_suggestions_from_file_ids",
        fake_generate_quick_suggestions_from_file_ids,
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "generate_quick_suggestions",
        fake_generate_quick_suggestions,
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "delete_files",
        fake_delete_files,
    )

    yield

    menu_routes._share_service.reset()
    menu_routes._upload_session_service.reset()
    delattr(menu_routes, "_expected_output_language")
    if hasattr(menu_routes, "_last_uploads"):
        delattr(menu_routes, "_last_uploads")
    if hasattr(menu_routes, "_deleted_file_ids"):
        delattr(menu_routes, "_deleted_file_ids")
    if hasattr(menu_routes, "_upload_call_count"):
        delattr(menu_routes, "_upload_call_count")


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
    assert payload["upload_session_id"]
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
    async def slow_generate_template_from_file_ids(
        file_ids,
        *,
        output_language=None,
    ):
        await asyncio.sleep(0.05)
        return MenuGenerationResult(template=MenuTemplate(sections=[]))

    monkeypatch.setattr(
        menu_routes, "_MENU_PROCESSING_TIMEOUT_SECONDS", 0.01, raising=False
    )
    monkeypatch.setattr(
        menu_routes._menu_service,
        "generate_template_from_file_ids",
        slow_generate_template_from_file_ids,
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


def test_retry_menu_reuses_existing_session():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    assert response.status_code == 200
    payload = response.json()
    session_id = payload["upload_session_id"]

    retry_response = client.post(
        "/menu/retry",
        json={"upload_session_id": session_id},
        headers={"accept-language": "zh-CN"},
    )
    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["upload_session_id"] == session_id
    assert (
        retry_payload["template"]["sections"][0]["dishes"][0]["translated_name"]
        == "Spicy Mapo Tofu"
    )
    assert menu_routes._upload_call_count == 1
    record = run(menu_routes._upload_session_service.describe(session_id))
    assert record is not None
    assert record.retry_count == 1


def test_delete_upload_session_releases_files():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    session_id = response.json()["upload_session_id"]
    delete_response = client.delete(f"/menu/session/{session_id}")
    assert delete_response.status_code == 204
    assert menu_routes._deleted_file_ids == ["file-0"]
    record = run(menu_routes._upload_session_service.describe(session_id))
    assert record is None


def test_quick_suggest_with_session_reuses_file_ids():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    session_id = response.json()["upload_session_id"]

    suggest_response = client.post(
        "/menu/suggest",
        data={"upload_session_id": session_id},
        headers={"accept-language": "zh-CN"},
    )
    assert suggest_response.status_code == 200
    assert suggest_response.json()["text"] == "Try the Mapo Tofu tonight!"
    assert menu_routes._upload_call_count == 1


def test_retry_menu_enforces_limit():
    response = client.post(
        "/menu/process",
        files=[("files", ("menu.jpg", BytesIO(b"fake-image"), "image/jpeg"))],
        headers={"accept-language": "zh-CN"},
    )
    session_id = response.json()["upload_session_id"]

    for _ in range(5):
        retry_response = client.post(
            "/menu/retry",
            json={"upload_session_id": session_id},
            headers={"accept-language": "zh-CN"},
        )
        assert retry_response.status_code == 200

    final_attempt = client.post(
        "/menu/retry",
        json={"upload_session_id": session_id},
        headers={"accept-language": "zh-CN"},
    )
    assert final_attempt.status_code == 429
    assert menu_routes._upload_call_count == 1


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
