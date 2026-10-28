import argparse
import asyncio
import json
import logging
import os
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from .config import Config
from .ozon import OzonClient
from .render import build_summary
from .tracker import Tracker

LOG = logging.getLogger("ozon_track")


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def run_once(cfg: Config, dump: bool) -> int:
    client = OzonClient(
        headless=cfg.headless,
        timeout_seconds=cfg.nav_timeout,
        user_data_dir=cfg.browser_dir,
        proxy=cfg.ozon_proxy,
    )
    await client.start()
    try:
        data = await client.fetch(cfg.track_number)
        if data is None:
            print(f"Заказ {cfg.track_number} не найден")
            return 2
        if dump:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        print(build_summary(cfg.track_number, data, cfg.timezone))
        return 0
    finally:
        await client.stop()


async def monitor(tracker: Tracker, interval: int) -> None:
    while True:
        started = time.monotonic()
        LOG.info("Проверяю заказ %s", tracker.cfg.track_number)
        try:
            await tracker.poll()
        except Exception:
            LOG.exception("Ошибка проверки заказа")
        elapsed = time.monotonic() - started
        delay = max(5, interval - int(elapsed))
        LOG.info("Следующая проверка через %s мин", max(1, delay // 60))
        await asyncio.sleep(delay)


def register_handlers(dp: Dispatcher, tracker: Tracker) -> None:
    @dp.message(Command("start", "help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "Бот следит за посылкой Ozon и присылает сообщение, когда меняется статус или место.\n\n"
            "/status — текущий статус из кеша\n"
            "/check — проверить сейчас\n"
            "/id — показать chat_id этой группы"
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        await message.answer(tracker.cached_summary())

    @dp.message(Command("check"))
    async def cmd_check(message: Message) -> None:
        try:
            await tracker.poll()
        except Exception as exc:
            LOG.exception("Ошибка проверки по команде")
            await message.answer(f"Ошибка проверки: {exc}")
            return
        await message.answer(tracker.cached_summary())

    @dp.message(Command("id"))
    async def cmd_id(message: Message) -> None:
        await message.answer(f"chat_id: <code>{message.chat.id}</code>")


async def run_bot(cfg: Config) -> None:
    LOG.info(
        "Запуск: заказ %s, интервал %s с, прокси Telegram: %s, прокси Ozon: %s",
        cfg.track_number,
        cfg.poll_interval,
        "да" if cfg.telegram_proxy else "нет",
        "да" if cfg.ozon_proxy else "нет",
    )
    session = AiohttpSession(proxy=cfg.telegram_proxy) if cfg.telegram_proxy else None
    bot = Bot(
        cfg.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    tracker = Tracker(cfg, bot)
    register_handlers(dp, tracker)

    await tracker.notify_startup()
    await tracker.start()
    LOG.info("Браузер запущен, начинаю опрос заказа")
    monitor_task = asyncio.create_task(monitor(tracker, cfg.poll_interval))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except (asyncio.CancelledError, Exception):
            pass
        await tracker.stop()
        await bot.session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ozon Track -> Telegram")
    parser.add_argument("--once", action="store_true", help="одна проверка без Telegram")
    parser.add_argument("--dump", action="store_true", help="напечатать сырой JSON API")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    try:
        cfg = Config.from_env()
        if args.once:
            sys.exit(asyncio.run(run_once(cfg, args.dump)))
        cfg.validate_telegram()
        asyncio.run(run_bot(cfg))
    except KeyboardInterrupt:
        LOG.info("Остановлено пользователем")
    except ValueError as exc:
        LOG.error("%s", exc)
        sys.exit(1)
    except Exception:
        LOG.exception("Фатальная ошибка")
        sys.exit(1)


if __name__ == "__main__":
    main()
