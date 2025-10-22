"""Menu processing routes."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from io import BytesIO
from typing import List, Sequence, Tuple

import segno
from PIL import Image, UnidentifiedImageError

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.schemas import (
    MenuProcessingResponse,
    MenuTemplate,
    ShareMenuRequest,
    ShareMenuResponse,
    MenuRetryRequest,
)
from app.services.llm import LLMMenuService, MenuProcessingArtifacts
from app.services.tips import Tip, TipService
from app.services.share import ShareService
from app.services.upload_session import UploadSessionService

router = APIRouter(prefix="/menu", tags=["menu"])

logger = logging.getLogger(__name__)

_menu_service = LLMMenuService()
_share_service = ShareService()
_tip_service = TipService()
_upload_session_service = UploadSessionService()

_MAX_IMAGE_DIMENSION = 1280
_JPEG_QUALITY = 80
_PNG_COMPRESS_LEVEL = 6
_TIP_STREAM_INTERVAL_SECONDS = 10.0
_MENU_PROCESSING_TIMEOUT_SECONDS = 120.0
_MENU_SUGGESTION_TIMEOUT_SECONDS = max(
    3.0, float(settings.quick_suggestion_timeout_seconds)
)
_MAX_SESSION_RETRIES = 5
_LANGUAGE_CODE_TO_LABEL = {
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
    "English": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
}


def get_menu_service() -> LLMMenuService:
    return _menu_service


def get_share_service() -> ShareService:
    return _share_service


def get_tip_service() -> TipService:
    return _tip_service


def get_upload_session_service() -> UploadSessionService:
    return _upload_session_service


@router.post("/process", response_model=MenuProcessingResponse)
async def process_menu(
    request: Request,
    files: List[UploadFile] = File(...),
    requested_output_language: str | None = Form(
        default=None, alias="output_language"
    ),
    menu_service: LLMMenuService = Depends(get_menu_service),
    session_service: UploadSessionService = Depends(get_upload_session_service),
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

    await _purge_expired_sessions(menu_service, session_service)

    resolved_language = _resolve_output_language(requested_output_language)
    output_language = resolved_language or _detect_language(request)
    logger.debug("Processing menu with output language: %s", output_language)

    file_ids: List[str] = await menu_service.upload_images(
        contents,
        filenames,
        content_types,
    )

    try:
        artifacts = await _generate_menu_from_file_ids(
            menu_service,
            file_ids,
            output_language=output_language,
        )
    except Exception:
        await menu_service.delete_files(file_ids)
        raise

    try:
        session_token = await session_service.create_session(
            file_ids=file_ids,
            filenames=filenames,
            content_types=content_types,
        )
    except Exception:
        await menu_service.delete_files(file_ids)
        raise

    return MenuProcessingResponse(
        template=artifacts.template,
        quick_suggestion=artifacts.quick_suggestion,
        upload_session_id=session_token,
        detected_language=None,
    )


@router.post("/retry", response_model=MenuProcessingResponse)
async def retry_menu(
    request: Request,
    payload: MenuRetryRequest,
    menu_service: LLMMenuService = Depends(get_menu_service),
    session_service: UploadSessionService = Depends(get_upload_session_service),
) -> MenuProcessingResponse:
    await _purge_expired_sessions(menu_service, session_service)

    record = await session_service.describe(payload.upload_session_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Upload session expired. Please upload the menu again.",
        )

    resolved_language = _resolve_output_language(payload.output_language)
    output_language = resolved_language or _detect_language(request)

    try:
        retry_count = await session_service.increment_retry(record.token)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Upload session expired. Please upload the menu again.",
        ) from exc

    if retry_count > _MAX_SESSION_RETRIES:
        raise HTTPException(
            status_code=429,
            detail="Retry limit reached for this upload session.",
        )

    artifacts = await _generate_menu_from_file_ids(
        menu_service,
        record.file_ids,
        output_language=output_language,
    )

    return MenuProcessingResponse(
        template=artifacts.template,
        quick_suggestion=artifacts.quick_suggestion,
        upload_session_id=record.token,
        detected_language=None,
    )


@router.delete("/session/{session_id}", status_code=204)
async def delete_upload_session(
    session_id: str,
    menu_service: LLMMenuService = Depends(get_menu_service),
    session_service: UploadSessionService = Depends(get_upload_session_service),
) -> Response:
    await _purge_expired_sessions(menu_service, session_service)

    record = await session_service.describe(session_id)
    if record is not None:
        await menu_service.delete_files(record.file_ids)
    await session_service.delete(session_id)
    return Response(status_code=204)


@router.post("/suggest")
async def suggest_menu_highlights(
    request: Request,
    files: List[UploadFile] | None = File(default=None),
    requested_output_language: str | None = Form(
        default=None, alias="output_language"
    ),
    upload_session_id: str | None = Form(default=None),
    menu_service: LLMMenuService = Depends(get_menu_service),
    session_service: UploadSessionService = Depends(get_upload_session_service),
) -> dict[str, str]:
    """Return a quick, friendly suggestion snippet from the uploaded menu images.

    Designed to complete in ~10–30 seconds to improve perceived latency
    while the main extraction runs.
    """

    await _purge_expired_sessions(menu_service, session_service)

    resolved_language = _resolve_output_language(requested_output_language)
    output_language = resolved_language or _detect_language(request)

    if upload_session_id:
        record = await session_service.describe(upload_session_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="Upload session expired. Please upload the menu again.",
            )
        try:
            text: str = await asyncio.wait_for(
                menu_service.generate_quick_suggestions_from_file_ids(
                    record.file_ids, output_language=output_language
                ),
                timeout=_MENU_SUGGESTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            text = ""
        except Exception:  # pragma: no cover - defensive user experience path
            text = ""
        return {"text": text}

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

    try:
        text: str = await asyncio.wait_for(
            menu_service.generate_quick_suggestions(
                contents,
                filenames,
                content_types,
                output_language=output_language,
            ),
            timeout=_MENU_SUGGESTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        # Graceful timeout — front-end treats empty text as "no suggestions".
        text = ""
    except Exception:  # pragma: no cover - defensive user experience path
        text = ""

    return {"text": text}


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


def _resolve_output_language(selection: str | None) -> str | None:
    """Convert a submitted language code into its display label."""

    if selection is None:
        return None

    code = selection.strip()
    if not code:
        return None

    return _LANGUAGE_CODE_TO_LABEL.get(code, selection)


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
    tip_service: TipService = Depends(get_tip_service),
):
    tips = await tip_service.get_tips()
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


async def _generate_menu_from_file_ids(
    menu_service: LLMMenuService,
    file_ids: Sequence[str],
    *,
    output_language: str,
) -> MenuProcessingArtifacts:
    suggestion_task: asyncio.Task[str] | None = None
    if settings.quick_suggestion_model:
        suggestion_task = asyncio.create_task(
            menu_service.generate_quick_suggestions_from_file_ids(
                file_ids,
                output_language=output_language,
            )
        )

    try:
        template_result = await asyncio.wait_for(
            menu_service.generate_template_from_file_ids(
                file_ids,
                output_language=output_language,
            ),
            timeout=_MENU_PROCESSING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        if suggestion_task:
            suggestion_task.cancel()
            with suppress(Exception):
                await suggestion_task
        logger.warning(
            "Menu processing timed out after %s seconds",
            _MENU_PROCESSING_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail="Menu processing took too long. Please try again.",
        ) from exc
    except Exception:
        if suggestion_task:
            suggestion_task.cancel()
            with suppress(Exception):
                await suggestion_task
        raise

    quick_suggestion = ""
    if suggestion_task is not None:
        quick_suggestion = await _await_suggestion_task(
            suggestion_task, _MENU_SUGGESTION_TIMEOUT_SECONDS
        )

    return MenuProcessingArtifacts(
        template=template_result.template,
        quick_suggestion=quick_suggestion,
    )


async def _await_suggestion_task(
    task: asyncio.Task[str],
    timeout_seconds: float | None,
) -> str:
    try:
        if timeout_seconds is not None:
            return await asyncio.wait_for(task, timeout_seconds)
        return await task
    except asyncio.TimeoutError:
        task.cancel()
        with suppress(Exception):
            await task
        return ""
    except Exception:
        return ""


async def _purge_expired_sessions(
    menu_service: LLMMenuService, session_service: UploadSessionService
) -> None:
    expired_records = await session_service.purge_expired()
    if not expired_records:
        return
    await asyncio.gather(
        *(menu_service.delete_files(record.file_ids) for record in expired_records),
        return_exceptions=True,
    )


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
