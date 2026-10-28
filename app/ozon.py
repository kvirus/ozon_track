import asyncio
import logging
import os
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page, async_playwright

LOG = logging.getLogger(__name__)

TRACK_URL = "https://tracking.ozon.ru/"
API_MARKER = "/p-api/ozon-track-bff/tracking/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class OzonError(RuntimeError):
    pass


class OzonClient:
    def __init__(
        self,
        headless: bool = True,
        timeout_seconds: int = 90,
        user_data_dir: str = "/data/browser",
    ) -> None:
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.user_data_dir = user_data_dir
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=self.headless,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        self._context.set_default_timeout(self.timeout_seconds * 1000)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    async def fetch(self, track_number: str) -> dict | None:
        if self._page is None:
            raise OzonError("Браузер не запущен")

        page = self._page
        holder: dict[str, object] = {}
        marker = API_MARKER + track_number

        def on_response(response) -> None:
            try:
                if response.request.method == "GET" and marker in response.url:
                    holder["response"] = response
            except Exception:
                pass

        page.on("response", on_response)
        url = TRACK_URL + "?" + urlencode({"track": track_number})
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
            except Exception as exc:  # таймаут навигации не фатален: API мог уже ответить
                LOG.debug("Навигация: %s", exc)

            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            while asyncio.get_running_loop().time() < deadline:
                if "response" in holder:
                    break
                await asyncio.sleep(0.5)

            response = holder.get("response")
            if response is None:
                await self._dump_debug(page, track_number)
                raise OzonError(
                    "Не получили ответ API tracking.ozon.ru. "
                    "Вероятно, не пройден Antibot Challenge — смотрите /data/debug."
                )

            status = response.status
            if status == 404:
                return None
            if status != 200:
                raise OzonError(f"API вернул HTTP {status} для {track_number}")

            data = await response.json()
            if not isinstance(data, dict):
                raise OzonError(f"Неожиданный ответ API: {type(data)!r}")
            return data
        finally:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass

    async def _dump_debug(self, page: Page, track_number: str) -> None:
        directory = "/data/debug"
        try:
            os.makedirs(directory, exist_ok=True)
            stamp = str(int(asyncio.get_running_loop().time()))
            await page.screenshot(path=f"{directory}/{track_number}-{stamp}.png", full_page=True)
            html = await page.content()
            with open(f"{directory}/{track_number}-{stamp}.html", "w", encoding="utf-8") as fh:
                fh.write(html)
            LOG.warning("Отладка сохранена в %s (url=%s)", directory, page.url)
        except Exception as exc:
            LOG.debug("Не удалось сохранить отладку: %s", exc)
