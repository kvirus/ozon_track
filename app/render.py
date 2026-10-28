import html
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from . import statuses


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fmt_datetime(value: Any, tz: ZoneInfo) -> str:
    dt = parse_dt(value)
    if dt is None:
        return ""
    return dt.astimezone(tz).strftime("%d.%m.%y, %H:%M")


def fmt_date(value: Any, tz: ZoneInfo) -> str:
    dt = parse_dt(value)
    if dt is None:
        return ""
    return dt.astimezone(tz).strftime("%d.%m.%y")


def actual_items(data: dict) -> list[dict]:
    items = data.get("items") or []
    return [it for it in items if isinstance(it, dict) and it.get("event") and it.get("moment")]


def item_key(item: dict) -> str:
    return f"{item.get('event')}|{item.get('moment')}|{statuses.location(item)}"


def _order_index(event: str | None) -> int:
    try:
        return statuses.ORDER.index(event or "")
    except ValueError:
        return -1


def latest_item(data: dict) -> dict | None:
    items = actual_items(data)
    if not items:
        return None

    def sort_key(item: dict) -> tuple[datetime, int]:
        moment = parse_dt(item.get("moment")) or datetime.min.replace(tzinfo=timezone.utc)
        return moment, _order_index(item.get("event"))

    return max(items, key=sort_key)


def next_pending(data: dict) -> str | None:
    events = {
        item.get("event")
        for item in actual_items(data)
    }
    if "Cancelled" in events:
        return None

    last_idx = -1
    for idx, event in enumerate(statuses.ORDER):
        if event in events:
            last_idx = idx

    pvz = data.get("deliveryType") in statuses.PVZ_TYPES
    for event in statuses.ORDER[last_idx + 1:]:
        if event == "SubmittedForCourierDelivery" and pvz:
            continue
        if event == "AvailableForPickup" and not pvz:
            continue
        return event
    return None


def delivery_period(data: dict, tz: ZoneInfo) -> str:
    begin = fmt_date(data.get("deliveryDateBegin"), tz)
    end = fmt_date(data.get("deliveryDateEnd"), tz)
    if begin and end:
        return f"{begin} - {end}"
    return begin or end


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def build_summary(track: str, data: dict, tz: ZoneInfo) -> str:
    last = latest_item(data)
    lines = [f"Заказ <code>{esc(track)}</code>"]
    if last is None:
        lines.append("Пока нет событий по заказу.")
        return "\n".join(lines)

    lines += ["", f"Текущий статус: <b>{esc(statuses.title(last.get('event')))}</b>"]
    moment = fmt_datetime(last.get("moment"), tz)
    if moment:
        lines.append(moment)
    location = statuses.location(last)
    if location:
        lines.append(f"Место: {esc(location)}")

    pending = next_pending(data)
    if pending:
        lines += ["", f"Следующий этап: {esc(statuses.title(pending))}"]

    period = delivery_period(data, tz)
    if period:
        lines.append(f"Период доставки: {period}")

    return "\n".join(lines)


def build_movement(track: str, new_items: list[dict], data: dict, tz: ZoneInfo) -> str:
    lines = [f"Перемещение по заказу <code>{esc(track)}</code>"]
    for item in new_items:
        lines.append("")
        lines.append(f"<b>{esc(statuses.title(item.get('event')))}</b>")
        moment = fmt_datetime(item.get("moment"), tz)
        if moment:
            lines.append(moment)
        location = statuses.location(item)
        if location:
            lines.append(f"Место: {esc(location)}")

    pending = next_pending(data)
    if pending:
        lines += ["", f"Следующий этап: {esc(statuses.title(pending))}"]

    period = delivery_period(data, tz)
    if period:
        lines.append(f"Период доставки: {period}")

    return "\n".join(lines)
