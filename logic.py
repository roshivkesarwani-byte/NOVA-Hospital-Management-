"""Pure business rules for NOVA. No database or UI code lives here, so every
rule can be unit-tested in isolation."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import config

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def hospital_now() -> datetime:
    """Current wall-clock time in the hospital timezone (naive datetime)."""
    return datetime.now(ZoneInfo(config.HOSPITAL_TIMEZONE)).replace(tzinfo=None, microsecond=0)


def ts(value: datetime) -> str:
    return value.strftime(TS_FORMAT)


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FORMAT)


def is_valid_temperature(temp_c) -> bool:
    try:
        value = float(temp_c)
    except (TypeError, ValueError):
        return False
    if value != value:  # NaN
        return False
    return config.TEMP_MIN_C <= value <= config.TEMP_MAX_C


def is_fever(temp_c: float, threshold: float | None = None) -> bool:
    threshold = config.FEVER_THRESHOLD_C if threshold is None else threshold
    return float(temp_c) >= threshold


def classify(temp_c: float, threshold: float | None = None) -> str:
    return "Fever" if is_fever(temp_c, threshold) else "No Fever"


def fever_free_streak(readings_by_day: dict[date, float], today: date,
                      threshold: float | None = None) -> int:
    """Number of COMPLETE consecutive fever-free calendar days ending yesterday.

    * A day counts only if it has a reading and that reading is below threshold.
    * A fever reading or a day with no reading ends the streak.
    * Today is a partial day and never counts, but a fever recorded today
      resets the streak to zero immediately.
    """
    todays = readings_by_day.get(today)
    if todays is not None and is_fever(todays, threshold):
        return 0
    streak = 0
    day = today - timedelta(days=1)
    while day in readings_by_day and not is_fever(readings_by_day[day], threshold):
        streak += 1
        day -= timedelta(days=1)
    return streak


def is_discharge_eligible(streak: int, status: str) -> bool:
    """Administrative eligibility flag only - a doctor must still approve."""
    return status == "Admitted" and streak >= config.REQUIRED_FEVER_FREE_DAYS


def success_rate(cured: int, deceased: int) -> float | None:
    """Cured / (Cured + Deceased) x 100, or None when nothing is finalised."""
    total = cured + deceased
    if total <= 0:
        return None
    return cured / total * 100.0


def benchmark_status(rate: float | None) -> str:
    if rate is None:
        return "N/A"
    return "Above benchmark" if rate >= config.SUCCESS_BENCHMARK_PCT else "Below benchmark"
