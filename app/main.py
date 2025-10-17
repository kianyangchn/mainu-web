from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import segno
from .i18n import (
    determine_locale,
    get_gettext_functions,
    get_html_lang,
    list_supported_ui_locales,
    normalize_locale,
)
from .routes import router as menu_router
from .routes.menu import get_share_service
from .schemas import MenuTemplate

templates = Jinja2Templates(directory="app/templates")
templates.env.add_extension("jinja2.ext.i18n")

app = FastAPI(title="mainu Web", version="0.1.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menu_router)


@app.middleware("http")
async def set_request_locale(request: Request, call_next):
    """Attach the resolved UI locale to the request state."""
    cookie_locale = request.cookies.get("ui_locale")
    resolved_locale = determine_locale(
        cookie_locale, request.headers.get("accept-language")
    )
    request.state.locale = resolved_locale
    request.state.locale_override = normalize_locale(cookie_locale)
    response = await call_next(request)
    return response


def _template_context(request: Request, extra: dict) -> dict:
    """Build a template context with localisation helpers for the request."""
    locale = getattr(request.state, "locale", None) or determine_locale(
        request.cookies.get("ui_locale"), request.headers.get("accept-language")
    )
    gettext_func, ngettext_func = get_gettext_functions(locale)
    override_locale = getattr(request.state, "locale_override", None)
    language_options: list[dict[str, str | bool]] = []
    browser_label = gettext_func("Follow browser language")
    try:
        browser_href = request.url_for("set_ui_language", locale_code="browser")
    except Exception:  # pragma: no cover - defensive, url_for should succeed
        browser_href = "/ui-language/browser"
    language_options.append(
        {
            "code": "browser",
            "label": browser_label,
            "active": override_locale is None,
            "href": browser_href,
        }
    )
    for code, label in list_supported_ui_locales():
        try:
            href = request.url_for("set_ui_language", locale_code=code)
        except Exception:  # pragma: no cover
            href = f"/ui-language/{code}"
        language_options.append(
            {
                "code": code,
                "label": gettext_func(label),
                "active": locale == code,
                "href": href,
            }
        )
    context = {
        "request": request,
        "_": gettext_func,
        "gettext": gettext_func,
        "ngettext": ngettext_func,
        "ui_locale": get_html_lang(locale),
        "ui_language_options": language_options,
    }
    context.update(extra)
    return context


@app.get("/", include_in_schema=False)
async def home(request: Request):
    """Render the mobile-first home shell."""
    return templates.TemplateResponse(
        request,
        "home.html",
        _template_context(
            request,
            {
                "title": "Mainu on-the-go",
                "subtitle": "Make it easy to order",
            },
        ),
    )


@app.get("/share/{token}", include_in_schema=False)
async def share_view(request: Request, token: str):
    """Render a read-only viewer for shared menus."""

    share_service = get_share_service()
    await share_service.purge_expired()
    record = await share_service.describe(token)
    if record is None:
        return templates.TemplateResponse(
            request,
            "share.html",
            _template_context(
                request,
                {
                    "menu": None,
                    "token": token,
                    "is_expired": True,
                },
            ),
            status_code=410,
    )

    return templates.TemplateResponse(
        request,
        "share.html",
        _template_context(
            request,
            {
                "menu": record.template,
                "token": token,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
                "expires_in_seconds": record.ttl_seconds,
                "share_url": str(request.url),
                "share_qr": segno.make_qr(str(request.url)).png_data_uri(
                    scale=4, dark="#1d5bdb", light="#f8fafc"
                ),
                "is_expired": False,
            },
        ),
    )


@app.get("/ui-language/{locale_code}", include_in_schema=False, name="set_ui_language")
async def set_ui_language(request: Request, locale_code: str):
    """Persist a UI language selection and redirect back to the referring page."""
    referer = request.headers.get("referer")
    default_target = str(request.url_for("home"))
    target = default_target
    if referer:
        parsed = urlparse(referer)
        if not parsed.netloc or parsed.netloc == request.url.netloc:
            target = referer

    normalized = normalize_locale(locale_code)
    response = RedirectResponse(target, status_code=303)
    if locale_code.lower() == "browser":
        response.delete_cookie("ui_locale", path="/")
    elif normalized:
        response.set_cookie(
            "ui_locale",
            normalized,
            max_age=60 * 60 * 24 * 365,
            path="/",
            httponly=False,
            samesite="lax",
        )
    else:
        response.delete_cookie("ui_locale", path="/")
    return response
