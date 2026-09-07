"""
Relative-date resolution, per MASTER BUILD PROMPT §43.

Rule: never silently guess when a booking could be affected. Every resolver
function returns a Resolution with `needs_confirmation` set whenever the
phrase is genuinely ambiguous, plus a ready-to-speak clarification question.
The caller (a Vapi tool handler) must surface that question instead of
proceeding straight to search/booking.

All times are handled explicitly with zoneinfo (stdlib, IANA tz database) —
never naive datetimes, per §42.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


@dataclass(frozen=True)
class DateResolution:
    resolved_date: date | None
    needs_confirmation: bool
    clarification_prompt: str | None
    matched_phrase: str


def now_in_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def _next_weekday(reference: date, target_weekday: int, *, treat_today_as_next_week: bool) -> date:
    """Closest future occurrence of `target_weekday`. If today already *is*
    that weekday: `treat_today_as_next_week=False` returns today, `True`
    rolls forward 7 days (used for explicit 'next <weekday>' phrasing)."""
    days_ahead = (target_weekday - reference.weekday()) % 7
    if days_ahead == 0 and treat_today_as_next_week:
        days_ahead = 7
    return reference + timedelta(days=days_ahead)


def resolve_relative_date(phrase: str, reference_dt: datetime) -> DateResolution:
    """
    reference_dt must be tz-aware (the caller's/call's local "now").
    Supports: 'today', 'tomorrow', 'this weekend', '<weekday>',
    'next <weekday>', 'the Nth' (of the current or next month).
    Anything unrecognised comes back as needs_confirmation=True.
    """
    text = phrase.strip().lower()
    today = reference_dt.date()

    if text == "today":
        return DateResolution(today, False, None, phrase)

    if text == "tomorrow":
        return DateResolution(today + timedelta(days=1), False, None, phrase)

    if text == "this weekend":
        # Convention: nearest upcoming Saturday. Flag it — "weekend" is a
        # 2-day span, so ask which day rather than silently picking one.
        saturday = _next_weekday(today, _WEEKDAYS["saturday"], treat_today_as_next_week=False)
        return DateResolution(
            saturday, True,
            f"Do you mean Saturday, {saturday.strftime('%B %-d')}, or Sunday, "
            f"{(saturday + timedelta(days=1)).strftime('%B %-d')}?",
            phrase,
        )

    m = re.match(r"^next (\w+)$", text)
    if m and m.group(1) in _WEEKDAYS:
        # Common airline-chatbot convention: "next Friday" = the closest
        # upcoming Friday (same as bare "Friday"). This IS genuinely
        # ambiguous in everyday English, so we resolve it but still ask
        # the customer to confirm the concrete date before it drives a
        # search or booking.
        resolved = _next_weekday(today, _WEEKDAYS[m.group(1)], treat_today_as_next_week=False)
        return DateResolution(
            resolved, True,
            f"Do you mean {m.group(1).capitalize()}, {resolved.strftime('%B %-d')}?",
            phrase,
        )

    if text in _WEEKDAYS:
        resolved = _next_weekday(today, _WEEKDAYS[text], treat_today_as_next_week=False)
        return DateResolution(
            resolved, True,
            f"Do you mean {text.capitalize()}, {resolved.strftime('%B %-d')}?",
            phrase,
        )

    m = re.match(r"^the (\d{1,2})(st|nd|rd|th)?$", text)
    if m:
        day_num = int(m.group(1))
        if 1 <= day_num <= 31:
            candidate = today.replace(day=1)
            try:
                candidate = candidate.replace(day=day_num)
            except ValueError:
                return DateResolution(
                    None, True,
                    f"The {day_num}{'th' if day_num not in (1, 2, 3, 21, 22, 23, 31) else ''} "
                    "doesn't fall in the current month — which month did you mean?",
                    phrase,
                )
            if candidate < today:
                # Already passed this month -> roll to next month.
                next_month = (candidate.replace(day=28) + timedelta(days=4)).replace(day=1)
                try:
                    candidate = next_month.replace(day=day_num)
                except ValueError:
                    return DateResolution(
                        None, True,
                        f"Could you confirm the exact date and month for the {day_num}?",
                        phrase,
                    )
            return DateResolution(
                candidate, True,
                f"Do you mean {candidate.strftime('%B %-d')}?",
                phrase,
            )

    m = re.match(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday) morning$", text)
    if m:
        resolved = _next_weekday(today, _WEEKDAYS[m.group(1)], treat_today_as_next_week=False)
        return DateResolution(
            resolved, True,
            f"Do you mean {m.group(1).capitalize()} morning, {resolved.strftime('%B %-d')}?",
            phrase,
        )

    return DateResolution(
        None, True,
        f"Sorry, could you give me a specific date for \"{phrase}\"?",
        phrase,
    )


def try_parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
