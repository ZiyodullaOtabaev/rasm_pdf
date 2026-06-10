"""
Bot handlers package.
"""
from aiogram import Router

from bot.handlers.start import router as start_router
from bot.handlers.text_pdf import router as text_pdf_router
from bot.handlers.img_pdf import router as img_pdf_router
from bot.handlers.upscale import router as upscale_router
from bot.handlers.merge_pdf import router as merge_pdf_router
from bot.handlers.admin import router as admin_router
from bot.handlers.menu import router as menu_router


def get_all_routers() -> list[Router]:
    """Return all handler routers in priority order."""
    return [
        start_router,
        admin_router,
        text_pdf_router,
        img_pdf_router,
        upscale_router,
        merge_pdf_router,
        menu_router,
    ]
