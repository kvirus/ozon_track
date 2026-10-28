import asyncio
import logging
import os
from urllib.parse import unquote, urlencode, urlsplit

from playwright.async_api import BrowserContext, Page, async_playwright

LOG = logging.getLogger(__name__)

TRACK_URL = "https://tracking.ozon.ru/"
API_MARKER = "/p-api/ozon-track-bff/tracking/"

BLOCK_MARKERS = (
    "antibot challenge",
    "похоже, нет соединения",
    "выключите vpn",
    "инцидент:",
)

DEFAULT_UA_VERSION = "131.0.0.0"

def playwright_proxy(url: str | None) -> dict | None:
    if not url:
        return None
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "http").lower()
    if scheme.endswith("h"):
        scheme = scheme[:-1]
    host = parsed.hostname or ""
    server = f"{scheme}://{host}"
    if parsed.port:
        server += f":{parsed.port}"
    result = {"server": server}
    if parsed.username:
        result["username"] = unquote(parsed.username)
    if parsed.password:
        result["password"] = unquote(parsed.password)
    return result


class OzonError(RuntimeError):
    pass


class OzonClient:
    def __init__(
        self,
        headless: bool = True,
        timeout_seconds: int = 90,
        user_data_dir: str = "/data/browser",
        proxy: str | None = None,
    ) -> None:
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._playwright = await async_playwright().start()
        user_agent = await self._build_user_agent()
        kwargs = {
            "headless": self.headless,
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "user_agent": user_agent,
            "viewport": {"width": 1366, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        }
        proxy = playwright_proxy(self.proxy)
        if proxy:
            kwargs["proxy"] = proxy
            LOG.info("Ozon через прокси %s", proxy["server"])
        self._context = await self._playwright.chromium.launch_persistent_context(
            self.user_data_dir, **kwargs
        )
        self._context.set_default_timeout(self.timeout_seconds * 1000)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def _build_user_agent(self) -> str:
        version = DEFAULT_UA_VERSION
        try:
            browser = await self._playwright.chromium.launch(headless=True)
            try:
                version = browser.version
            finally:
                await browser.close()
        except Exception as exc:
            LOG.debug("Не удалось определить версию Chromium: %s", exc)
        LOG.info("Chromium %s", version)
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )

    async def stop(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception as exc:
                LOG.debug("Браузер уже закрыт: %s", exc)
            self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                LOG.debug("Playwright уже остановлен: %s", exc)
            self._playwright = None
        self._page = None

    async def fetch(self, track_number: str) -> dict | None:
        if self._page is None:
            raise OzonError("Браузер не запущен")

        page = self._page
        holder: dict[str, object] = {}
        observed: list[str] = []
        marker = API_MARKER + track_number

        def on_response(response) -> None:
            try:
                url = response.url
                if "tracking.ozon" not in url:
                    return
                if response.request.method == "GET" and marker in url:
                    holder["response"] = response
                status = response.status
                if status >= 400 or "/abt/" in url or API_MARKER in url:
                    short = url.split("?")[0]
                    observed.append(f"{status} {response.request.method} {short}")
                    LOG.info("Ozon: %s %s", status, short)
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
                block = await self._detect_block(page)
                answers = "; ".join(observed[-6:]) or "нет ответов tracking.ozon.ru"
                if block:
                    raise OzonError(
                        f"Ozon заблокировал запрос ({block}). IP сервера не нравится antibot. "
                        "Задайте OZON_PROXY с чистым (резидентным) IP. "
                        f"Ответы: {answers}"
                    )
                raise OzonError(
                    "Не получили ответ API tracking.ozon.ru. "
                    f"Вероятно, не пройден antibot — смотрите /data/debug. Ответы: {answers}"
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

    async def _detect_block(self, page: Page) -> str | None:
        try:
            body = (await page.inner_text("body"))[:2000].lower()
        except Exception:
            return None
        for marker in BLOCK_MARKERS:
            if marker in body:
                return marker
        return None

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
