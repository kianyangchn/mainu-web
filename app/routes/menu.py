"""Menu processing routes."""

from __future__ import annotations

import asyncio
import json
import logging
from io import BytesIO
from typing import List, Tuple

import segno
from PIL import Image, UnidentifiedImageError

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.schemas import (
    MenuProcessingResponse,
    MenuTemplate,
    ShareMenuRequest,
    ShareMenuResponse,
)
from app.services.llm import LLMMenuService, MenuGenerationResult
from app.services.location import LocationService, Place
from app.services.tips import Tip, TipService
from app.services.share import ShareService

router = APIRouter(prefix="/menu", tags=["menu"])

logger = logging.getLogger(__name__)

_menu_service = LLMMenuService()
_share_service = ShareService()
_tip_service = TipService()
_location_service = LocationService()

_MAX_IMAGE_DIMENSION = 1280
_JPEG_QUALITY = 80
_PNG_COMPRESS_LEVEL = 6
_TIP_STREAM_INTERVAL_SECONDS = 10.0


def get_menu_service() -> LLMMenuService:
    return _menu_service


def get_share_service() -> ShareService:
    return _share_service


def get_tip_service() -> TipService:
    return _tip_service


def get_location_service() -> LocationService:
    return _location_service


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
        optimised, content_type = _optimise_image_payload(raw, upload.content_type)
        contents.append(optimised)
        filenames.append(upload.filename or "menu-page")
        content_types.append(content_type)

    output_language = requested_output_language or _detect_language(request)
    logger.debug("Processing menu with output language: %s", output_language)
    generation_result: MenuGenerationResult = await menu_service.generate_menu_template(
        contents,
        filenames,
        content_types,
        output_language=output_language,
    )
    return MenuProcessingResponse(
        template=generation_result.template,
        detected_language=None,
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


@router.get("/tips", name="stream_menu_tips")
async def stream_menu_tips(
    request: Request,
    cuisine: str | None = Query(default=None, alias="topic"),
    lang: str | None = Query(default=None, alias="lang"),
    tip_service: TipService = Depends(get_tip_service),
):
    tips = await tip_service.get_tips(cuisine, lang)
    tip_count = len(tips)

    if request is not None and "text/event-stream" in request.headers.get("accept", ""):

        async def event_generator():
            try:
                for index, tip in enumerate(tips):
                    yield _tip_event("tip", tip)
                    if index < tip_count - 1:
                        await asyncio.sleep(_TIP_STREAM_INTERVAL_SECONDS)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.exception("Failed to stream tips: %s", exc)
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Unable to load tips"}),
                }
            else:
                yield {"event": "complete", "data": "{}"}

        return EventSourceResponse(event_generator())

    return JSONResponse([_tip_to_dict(tip) for tip in tips])


@router.get("/location/reverse", name="reverse_location")
async def reverse_location(
    lat: float = Query(..., alias="lat"),
    lon: float = Query(..., alias="lon"),
    location_service: LocationService = Depends(get_location_service),
) -> JSONResponse:
    place = await location_service.reverse_geocode(lat, lon)
    payload = {
        "city": place.city,
        "country": place.country,
    }
    return JSONResponse(payload)


def _tip_event(event: str, tip: Tip) -> dict[str, str]:
    payload = {
        "title": tip.title,
        "body": tip.body,
    }
    if tip.image_url:
        payload["image_url"] = tip.image_url
    if tip.source_name:
        payload["source_name"] = tip.source_name
    if tip.source_url:
        payload["source_url"] = tip.source_url
    return {"event": event, "data": json.dumps(payload)}


def _tip_to_dict(tip: Tip) -> dict[str, str | None]:
    return {
        "title": tip.title,
        "body": tip.body,
        "image_url": tip.image_url,
        "source_name": tip.source_name,
        "source_url": tip.source_url,
    }


def _optimise_image_payload(raw: bytes, content_type: str) -> Tuple[bytes, str]:
    """Downscale and recompress menu images to reduce upload latency."""

    if content_type not in {"image/jpeg", "image/png"}:
        return raw, content_type

    try:
        with Image.open(BytesIO(raw)) as image:
            image.load()
            original_size = image.size
            processed = image.copy()
    except (UnidentifiedImageError, OSError):
        return raw, content_type

    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    if max(processed.size) > _MAX_IMAGE_DIMENSION:
        processed.thumbnail((_MAX_IMAGE_DIMENSION, _MAX_IMAGE_DIMENSION), resampling)

    buffer = BytesIO()
    if content_type == "image/jpeg":
        if processed.mode not in {"RGB", "L"}:
            processed = processed.convert("RGB")
        processed.save(
            buffer,
            format="JPEG",
            quality=_JPEG_QUALITY,
            optimize=True,
        )
        optimised_type = "image/jpeg"
    else:  # image/png
        if processed.mode == "P":
            processed = processed.convert("RGBA")
        processed.save(
            buffer,
            format="PNG",
            optimize=True,
            compress_level=_PNG_COMPRESS_LEVEL,
        )
        optimised_type = "image/png"

    optimised_bytes = buffer.getvalue()
    if max(processed.size) == max(original_size) and len(optimised_bytes) >= len(raw):
        return raw, content_type
    return optimised_bytes, optimised_type
