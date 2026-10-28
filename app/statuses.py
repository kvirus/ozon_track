TITLES = {
    "Created": "Заказ создан",
    "TransferringToDelivery": "Передаётся в доставку",
    "WayToCity": "Заказ принят перевозчиком",
    "ParcelDepartureFromCarrier": "Заказ везут на таможню в стране отправления",
    "ArrivedToOutwardExchangeOffice": "Заказ привезли на таможню",
    "OutFromOutwardExchangeOffice": "Заказ покинул зону экспортного оформления",
    "ArrivedAtDestinationCountry": "Заказ привезли в страну назначения",
    "CustomsClearanceStarted": "Заказ передан на импортное оформление",
    "CustomsClearanceInProcess": "Заказ проходит импортное оформление",
    "CustomsRefusedParcelRelease": "Импортная таможня задержала заказ",
    "CustomsClearanceCompleted": "Заказ выпущен импортной таможней",
    "SentToSortingCenter": "Заказ отправили на сортировочный терминал",
    "ReleasedFromSortingCenter": "Заказ покинул сортировочный терминал",
    "AwaitingRecipientCity": "Заказ ожидает отправки в город получателя",
    "InTransitRecipientCity": "Заказ везут в город получателя",
    "ParcelIsOnTheWay": "Заказ везут",
    "AvailableForPickup": "Заказ в пункте выдачи",
    "SubmittedForCourierDelivery": "Заказ передали в курьерскую доставку",
    "Received": "Заказ получен",
    "PickedUpByTheCustomer": "Заказ получен в пункте выдачи",
    "DeliveredByCourier": "Заказ доставлен получателю",
    "Delivered": "Заказ доставлен",
    "Cancelled": "Заказ отменён",
    "FantomDelivery": "Заказ в работе",
    "OnTheWayToImportCustomsClearancePhantomStatus": "Заказ на пути к импортному оформлению",
    "InCustomsClearancePhantomStatus": "Заказ на импортном оформлении",
}

DESCRIPTIONS = {
    "Created": "Мы получили заказ, продавец уже собирает его",
    "TransferringToDelivery": "Продавец собрал заказ и передаёт его в доставку",
    "WayToCity": "Он отвезёт заказ на таможню",
    "ParcelDepartureFromCarrier": "Обычно это занимает до 10 дней",
    "ArrivedToOutwardExchangeOffice": "Скорость оформления зависит от загруженности таможни",
    "OutFromOutwardExchangeOffice": "Заказ спешит в страну назначения",
    "ArrivedAtDestinationCountry": "Его отвезут на таможенное оформление",
    "CustomsClearanceStarted": "Его готовят к оформлению",
    "CustomsClearanceInProcess": "Скорость оформления зависит от загруженности таможни",
    "CustomsRefusedParcelRelease": "Его направили на дополнительную проверку",
    "CustomsClearanceCompleted": "Его готовят к отправке на сортировочный терминал",
    "SentToSortingCenter": "Его подготовят к доставке в город получателя",
    "ReleasedFromSortingCenter": "Его подготовили к доставке в город получателя",
    "AwaitingRecipientCity": "Скорость отправки зависит от загруженности склада",
    "InTransitRecipientCity": "Его доставят в сортировочный центр",
    "ParcelIsOnTheWay": "Мы сообщим, когда его доставят",
    "AvailableForPickup": "Успейте забрать его в течение 14 дней",
    "SubmittedForCourierDelivery": "Курьер свяжется с вами и согласует точное время доставки",
}

FINAL_EVENTS = {"Received", "PickedUpByTheCustomer", "DeliveredByCourier", "Delivered"}

LOCATION_FIELDS = ("location", "city", "warehouse", "place", "address", "facility", "point")


def title(event: str | None) -> str:
    if not event:
        return "Неизвестный статус"
    return TITLES.get(event, event)


def description(event: str | None) -> str | None:
    if not event:
        return None
    return DESCRIPTIONS.get(event)


def location(item: dict) -> str:
    for field in LOCATION_FIELDS:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for key in ("name", "title", "address", "city"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return ""
