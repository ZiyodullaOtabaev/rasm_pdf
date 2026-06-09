"""
Main entry point for the bot application.
Aiogram 3.x with proper logging and error handling.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.database import db_init
from bot.handlers import get_all_routers
from bot.utils.cleanup import cleanup_worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Reduce noise from third-party libraries
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)


async def on_startup(bot: Bot):
    """Startup tasks."""
    db_init()
    asyncio.create_task(cleanup_worker())
    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username} (id={me.id})")


async def on_shutdown(bot: Bot):
    """Shutdown tasks."""
    logger.info("Bot shutting down...")


async def main():
    """Initialize and run the bot."""
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Register all routers
    for router in get_all_routers():
        dp.include_router(router)

    # Register lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Global error handler
    @dp.error()
    async def error_handler(event, exception):
        logger.error(f"Unhandled error: {exception}", exc_info=True)
        return True

    logger.info("Starting polling...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
