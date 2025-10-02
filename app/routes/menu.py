"""Menu processing routes."""

from __future__ import annotations

import logging
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from app.config import settings
from app.schemas import MenuProcessingResponse, MenuTemplate
from app.services.llm import LLMMenuService
from app.services.share import ShareService

router = APIRouter(prefix="/menu", tags=["menu"])

logger = logging.getLogger(__name__)

_menu_service = LLMMenuService()
_share_service = ShareService()


def get_menu_service() -> LLMMenuService:
    return _menu_service


def get_share_service() -> ShareService:
    return _share_service


@router.post("/process", response_model=MenuProcessingResponse)
async def process_menu(
    request: Request,
    files: List[UploadFile] = File(...),
    requested_output_language: str | None = Form(
        default=None, alias="output_language"
    ),
    menu_service: LLMMenuService = Depends(get_menu_service),
    share_service: ShareService = Depends(get_share_service),
) -> MenuProcessingResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required")

    contents: List[bytes] = []
    filenames: List[str] = []
    content_types: List[str] = []
    for upload in files:
        if upload.content_type not in {"image/jpeg", "image/png", "image/heic"}:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        contents.append(raw)
        filenames.append(upload.filename or "menu-page")
        content_types.append(upload.content_type)

    output_language = requested_output_language or _detect_language(request)
    logger.debug("Processing menu with output language: %s", output_language)
    template = await menu_service.generate_menu_template(
        contents,
        filenames,
        content_types,
        input_language=settings.input_language,
        output_language=output_language,
    )
    share_service.purge_expired()
    token = share_service.create_template(template)
    record = share_service.describe(token)
    if record is None:
        raise RuntimeError("Share token expired unexpectedly")
    share_url = str(request.url_for("get_shared_menu", token=token))

    return MenuProcessingResponse(
        template=template,
        share_token=token,
        share_url=share_url,
        share_expires_at=record.expires_at,
        share_expires_in_seconds=record.ttl_seconds,
        detected_language=output_language,  # TODO: remove once locale debugging is complete.
    )


@router.get("/share/{token}", response_model=MenuTemplate, name="get_shared_menu")
async def get_shared_menu(
    token: str,
    share_service: ShareService = Depends(get_share_service),
) -> MenuTemplate:
    share_service.purge_expired()
    template = share_service.fetch_template(token)
    if template is None:
        raise HTTPException(status_code=404, detail="Share link expired or invalid")
    return template


def _detect_language(request: Request) -> str:
    """Return the client's preferred language using the Accept-Language header."""
    header = request.headers.get("accept-language", "")
    if header:
        primary = header.split(",")[0].strip()
        if primary:
            return primary
    return settings.default_output_language
