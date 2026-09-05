LIVE_MATCH_STATUSES = frozenset({"1H", "HT", "2H", "ET", "PEN_LIVE", "ET_BREAK", "LIVE"})
FINAL_MATCH_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO"})
UPCOMING_MATCH_STATUSES = frozenset({"TBD", "NS", "PST"})
CANCELLED_MATCH_STATUSES = frozenset({"CANC", "ABD", "SUSP"})


def normalize_status(status: str | None) -> str:
    return (status or "UNKNOWN").upper()


def is_live_status(status: str | None) -> bool:
    return normalize_status(status) in LIVE_MATCH_STATUSES


def is_final_status(status: str | None) -> bool:
    return normalize_status(status) in FINAL_MATCH_STATUSES


def status_group(status: str | None) -> str:
    value = normalize_status(status)
    if value in LIVE_MATCH_STATUSES:
        return "live"
    if value in FINAL_MATCH_STATUSES:
        return "finished"
    if value in CANCELLED_MATCH_STATUSES:
        return "cancelled"
    return "upcoming"


def status_label_ru(status: str | None) -> str:
    labels = {
        "TBD": "Время уточняется",
        "NS": "Не начался",
        "1H": "1-й тайм",
        "HT": "Перерыв",
        "2H": "2-й тайм",
        "ET": "Доп. время",
        "PEN_LIVE": "Пенальти",
        "ET_BREAK": "Перерыв",
        "LIVE": "Идёт матч",
        "FT": "Завершён",
        "AET": "Завершён в доп. время",
        "PEN": "Завершён по пенальти",
        "AWD": "Технический результат",
        "WO": "Техническая победа",
        "SUSP": "Приостановлен",
        "ABD": "Прерван",
        "PST": "Перенесён",
        "CANC": "Отменён",
    }
    return labels.get(normalize_status(status), "Статус уточняется")
