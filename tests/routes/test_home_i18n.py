import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_cookies():
    client.cookies.clear()


def test_home_respects_simplified_chinese_accept_language() -> None:
    response = client.get("/", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert response.status_code == 200
    body = response.text
    assert "轻松点餐" in body
    assert "添加菜单照片" in body


def test_home_defaults_to_english_without_header() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Make it easy to order" in body
    assert "Add menu photos" in body


def test_ui_language_override_sets_cookie_and_changes_locale() -> None:
    response = client.get(
        "/ui-language/zh_Hans",
        headers={"referer": "http://testserver/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "ui_locale=zh_Hans" in response.headers.get("set-cookie", "")

    follow = client.get("/")
    assert follow.status_code == 200
    assert "轻松点餐" in follow.text


def test_ui_language_browser_option_clears_override() -> None:
    client.cookies.set("ui_locale", "zh_Hans")
    response = client.get(
        "/ui-language/browser",
        headers={"referer": "http://testserver/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "ui_locale=" in response.headers.get("set-cookie", "")
    client.cookies.pop("ui_locale", None)

    follow = client.get("/", headers={"Accept-Language": "en-US,en;q=0.8"})
    assert follow.status_code == 200
    assert "Make it easy to order" in follow.text
