"""Menu processing routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.schemas import MenuProcessingResponse, MenuTemplate
from app.services.llm import LLMMenuService
from app.services.share import ShareService

router = APIRouter(prefix="/menu", tags=["menu"])

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
    menu_service: LLMMenuService = Depends(get_menu_service),
    share_service: ShareService = Depends(get_share_service),
) -> MenuProcessingResponse:
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required")

    contents: List[bytes] = []
    filenames: List[str] = []
    for upload in files:
        if upload.content_type not in {"image/jpeg", "image/png", "image/heic"}:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        contents.append(raw)
        filenames.append(upload.filename or "menu-page")

    template = await menu_service.generate_menu_template(contents, filenames)
    share_service.purge_expired()
    token = share_service.create_template(template)
    share_url = str(request.url_for("get_shared_menu", token=token))

    return MenuProcessingResponse(
        template=template, share_token=token, share_url=share_url
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
