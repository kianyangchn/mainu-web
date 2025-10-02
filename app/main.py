from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from .routes import router as menu_router
from .routes.menu import get_share_service
from .schemas import MenuTemplate

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="mainu Web", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menu_router)


@app.get("/", include_in_schema=False)
async def home(request: Request):
    """Render the mobile-first home shell."""
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "title": "mainu Web",
            "subtitle": "Translate menus on the go",
        },
    )


@app.get("/share/{token}", include_in_schema=False)
async def share_view(request: Request, token: str):
    """Render a read-only viewer for shared menus."""

    share_service = get_share_service()
    share_service.purge_expired()
    record = share_service.describe(token)
    if record is None:
        return templates.TemplateResponse(
            request,
            "share.html",
            {
                "menu": None,
                "token": token,
                "is_expired": True,
            },
            status_code=410,
        )

    return templates.TemplateResponse(
        request,
        "share.html",
        {
            "menu": record.template,
            "token": token,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "expires_in_seconds": record.ttl_seconds,
            "is_expired": False,
        },
    )
