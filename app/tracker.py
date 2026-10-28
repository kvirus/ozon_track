import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from . import state
from .config import Config
from .ozon import OzonClient
from .render import actual_items, build_movement, build_summary, esc, fmt_datetime, item_key

if TYPE_CHECKING:
    from aiogram import Bot

LOG = logging.getLogger(__name__)


class Tracker:
    def __init__(self, cfg: Config, bot: "Bot | None" = None) -> None:
        self.cfg = cfg
        self.bot = bot
        self.state = state.load(cfg.state_file)
        self.lock = asyncio.Lock()
        self.client = OzonClient(
            headless=cfg.headless,
            timeout_seconds=cfg.nav_timeout,
            user_data_dir=cfg.browser_dir,
            proxy=cfg.ozon_proxy,
        )

    async def start(self) -> None:
        await self.client.start()

    async def stop(self) -> None:
        await self.client.stop()

    async def notify_startup(self) -> None:
        if not self.cfg.notify_on_start:
            return
        sent = await self._notify("Бот запущен и следит за заказом.\n\n" + self.cached_summary())
        if sent:
            LOG.info("Стартовое сообщение отправлено в Telegram")

    def cached_summary(self) -> str:
        record = self.state.get("tracks", {}).get(self.cfg.track_number)
        if not record or not record.get("data"):
            return f"Заказ <code>{esc(self.cfg.track_number)}</code>\nДанных пока нет, идёт первая проверка."
        text = build_summary(self.cfg.track_number, record["data"], self.cfg.timezone)
        updated = fmt_datetime(record.get("updated"), self.cfg.timezone)
        if updated:
            text += f"\nПроверено: {updated}"
        return text

    async def poll(self) -> dict | None:
        async with self.lock:
            data = await self.client.fetch(self.cfg.track_number)
            tracks = self.state.setdefault("tracks", {})
            record = tracks.get(self.cfg.track_number)

            if data is None:
                if record and not record.get("not_found"):
                    record["not_found"] = True
                    record["updated"] = self._now()
                    self._save()
                    await self._notify(
                        f"Заказ <code>{esc(self.cfg.track_number)}</code> не найден на tracking.ozon.ru."
                    )
                return None

            actual = actual_items(data)
            if record is None:
                record = {
                    "seen": [item_key(item) for item in actual],
                    "not_found": False,
                    "updated": self._now(),
                    "data": data,
                }
                tracks[self.cfg.track_number] = record
                self._save()
                if self.cfg.notify_on_start:
                    await self._notify(
                        "Беру заказ под наблюдение.\n\n"
                        + build_summary(self.cfg.track_number, data, self.cfg.timezone)
                    )
                return data

            previous = set(record.get("seen") or [])
            new_items = [item for item in actual if item_key(item) not in previous]
            if not previous:
                new_items = []

            record["seen"] = sorted(previous | {item_key(item) for item in actual})
            record["not_found"] = False
            record["updated"] = self._now()
            record["data"] = data
            self._save()

            if new_items:
                LOG.info("Новых событий: %s (%s)", len(new_items), self.cfg.track_number)
                await self._notify(
                    build_movement(self.cfg.track_number, new_items, data, self.cfg.timezone)
                )

            return data

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _save(self) -> None:
        try:
            state.save(self.cfg.state_file, self.state)
        except OSError as exc:
            LOG.error("Не удалось сохранить состояние: %s", exc)

    async def _notify(self, text: str) -> bool:
        if self.bot is None:
            return False
        try:
            await self.bot.send_message(self.cfg.chat_id, text)
            return True
        except Exception as exc:
            LOG.error("Не удалось отправить сообщение в Telegram: %s", exc)
            return False
