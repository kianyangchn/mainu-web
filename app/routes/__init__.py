"""Application routes."""

from fastapi import APIRouter

from . import menu

router = APIRouter()
router.include_router(menu.router)

__all__ = ["router"]
