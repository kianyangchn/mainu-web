"""Menu processing routes."""

from __future__ import annotations

import logging
from typing import List

import segno

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.config import settings
from app.schemas import (
    MenuProcessingResponse,
    MenuTemplate,
    ShareMenuRequest,
    ShareMenuResponse,
)
from app.services.llm import LLMMenuService, MenuGenerationResult
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
    generation_result: MenuGenerationResult = await menu_service.generate_menu_template(
        contents,
        filenames,
        content_types,
        input_language=settings.input_language,
        output_language=output_language,
    )
    return MenuProcessingResponse(
        template=generation_result.template,
        detected_language=(
            generation_result.detected_input_language or output_language
        ),
    )


@router.post("/share", response_model=ShareMenuResponse)
async def create_share_link(
    request: Request,
    payload: ShareMenuRequest,
    share_service: ShareService = Depends(get_share_service),
) -> ShareMenuResponse:
    await share_service.purge_expired()
    token = await share_service.create_template(payload.template)
    record = await share_service.describe(token)
    if record is None:
        raise RuntimeError("Share token expired unexpectedly")

    share_html_url = str(request.url_for("share_view", token=token))
    share_api_url = str(request.url_for("get_shared_menu", token=token))
    qr = segno.make_qr(share_html_url)
    qr_data = qr.png_data_uri(scale=4, dark="#1d5bdb", light="#f8fafc")

    return ShareMenuResponse(
        share_token=token,
        share_url=share_html_url,
        share_api_url=share_api_url,
        share_qr=qr_data,
        share_expires_at=record.expires_at,
        share_expires_in_seconds=record.ttl_seconds,
    )


@router.get("/share/{token}", response_model=MenuTemplate, name="get_shared_menu")
async def get_shared_menu(
    token: str,
    share_service: ShareService = Depends(get_share_service),
) -> MenuTemplate:
    await share_service.purge_expired()
    template = await share_service.fetch_template(token)
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
