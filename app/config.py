import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo


def normalize_proxy(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered.startswith("socks5h://"):
        value = "socks5://" + value[len("socks5h://"):]
    elif lowered.startswith("socks4a://"):
        value = "socks4://" + value[len("socks4a://"):]
    elif lowered.startswith("socks://"):
        value = "socks5://" + value[len("socks://"):]
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def extract_track_number(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("OZON_TRACK_URL не задан")

    if "://" in value or value.startswith("tracking."):
        url = value if "://" in value else f"https://{value}"
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("track", "trackNumber", "track_number", "number"):
            if query.get(key):
                return query[key][0].strip()
        match = re.search(r"/track(?:ing)?/([^/?#]+)", parsed.path)
        if match:
            return unquote(match.group(1)).strip()
        raise ValueError(f"Не удалось найти трек-номер в ссылке: {value}")

    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: str
    telegram_proxy: str | None
    ozon_proxy: str | None
    track_url: str
    track_number: str
    poll_interval: int
    headless: bool
    nav_timeout: int
    notify_on_start: bool
    state_file: str
    browser_dir: str
    timezone: ZoneInfo

    @classmethod
    def from_env(cls) -> "Config":
        track_url = os.getenv("OZON_TRACK_URL", "")
        track_number = os.getenv("OZON_TRACK_NUMBER", "").strip() or extract_track_number(track_url)
        if not track_number:
            raise ValueError("Не задан OZON_TRACK_URL или OZON_TRACK_NUMBER")

        tz_name = os.getenv("TZ", "Europe/Moscow")
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            telegram_proxy=normalize_proxy(os.getenv("TELEGRAM_PROXY")),
            ozon_proxy=normalize_proxy(os.getenv("OZON_PROXY")),
            track_url=track_url,
            track_number=track_number,
            poll_interval=max(60, _env_int("POLL_INTERVAL_SECONDS", 3600)),
            headless=_env_bool("HEADLESS", True),
            nav_timeout=max(30, _env_int("NAV_TIMEOUT_SECONDS", 90)),
            notify_on_start=_env_bool("NOTIFY_ON_START", True),
            state_file=os.getenv("STATE_FILE", "/data/state.json"),
            browser_dir=os.getenv("BROWSER_DIR", "/data/browser"),
            timezone=ZoneInfo(tz_name),
        )

    def validate_telegram(self) -> None:
        if not self.bot_token:
            raise ValueError("Не задан TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            raise ValueError("Не задан TELEGRAM_CHAT_ID")
