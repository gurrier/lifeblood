"""Fetch and parse Lifeblood's public blood supply levels page.

There's no API behind the page - the levels are server-rendered HTML. The
national figures come with the plain GET; any other region is what the
page's region dropdown fetches, a Drupal AJAX form POST that returns the
replacement HTML fragment wrapped in a JSON command list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from html.parser import HTMLParser
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from .const import (
    BLOOD_TYPE_KEYS,
    LEVEL_CRITICAL,
    LEVEL_GOOD,
    LEVEL_LOW,
    LEVEL_NEED_MORE,
    LEVEL_NOT_COLLECTED,
    LEVEL_OK,
    LEVEL_VERY_LOW,
    PLASMA,
    REGION_CODES,
    REGION_FORM_VALUES,
    SOURCE_URL,
)

_LOGGER = logging.getLogger(__name__)

AJAX_URL = f"{SOURCE_URL}?ajax_form=1&_wrapper_format=drupal_ajax"

# Without an explicit timeout aiohttp waits around five minutes.
# NOTE: exceeding `total` raises TimeoutError, which is NOT an
# aiohttp.ClientError, so both must be caught wherever this is used.
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# The page's "Updated 6:00am (AEDT)" is Sydney time, AEST or AEDT as the
# season dictates.
LIFEBLOOD_TZ = ZoneInfo("Australia/Sydney")

# The printed label is the primary source: it's what donors read, and it
# means the same thing on red cell and plasma drops.
LABEL_LEVELS: dict[str, str] = {
    "critical": LEVEL_CRITICAL,
    "very low": LEVEL_VERY_LOW,
    "low": LEVEL_LOW,
    "need more": LEVEL_NEED_MORE,
    "ok": LEVEL_OK,
    "good": LEVEL_GOOD,
    "not collected": LEVEL_NOT_COLLECTED,
}

# CSS classes are the fallback if the wording ever changes. They are NOT
# interchangeable between the two kinds of drop: "good" is Ok on a red cell
# drop but Good on the plasma drop (seen side by side in the ACT figures).
RED_CELL_CLASS_LEVELS: dict[str, str] = {
    "appeal-mode": LEVEL_CRITICAL,
    "critical": LEVEL_VERY_LOW,
    "low": LEVEL_LOW,
    "average": LEVEL_NEED_MORE,
    "good": LEVEL_OK,
    "great": LEVEL_GOOD,
    "empty": LEVEL_NOT_COLLECTED,
}

PLASMA_CLASS_LEVELS: dict[str, str] = {
    "need-more": LEVEL_NEED_MORE,
    "okay": LEVEL_OK,
    "good": LEVEL_GOOD,
}

_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_UPDATED_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*([ap]m).*?(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE | re.DOTALL,
)


class LifebloodError(Exception):
    """Base error for the Lifeblood client."""


class LifebloodConnectionError(LifebloodError):
    """The Lifeblood website couldn't be reached or returned an error."""


class LifebloodParseError(LifebloodError):
    """The page came back but didn't contain the levels in a recognised shape."""


@dataclass
class SupplyLevel:
    """One drop on the page: a red cell blood type, or plasma."""

    level: str | None
    # Exactly as printed, kept so an unrecognised level is still visible.
    label: str
    # Lifeblood's own appeal banner is showing for this type.
    appeal: bool = False
    # Only the plasma drop carries this - a percentage hidden in its class
    # list, presumably supply against target.
    percent: float | None = None


@dataclass
class SupplyData:
    """Everything parsed for one region."""

    region: str
    region_code: str | None
    updated: datetime.datetime | None
    levels: dict[str, SupplyLevel] = field(default_factory=dict)


class _StockLevelParser(HTMLParser):
    """Collects each drop-div's label, classes and the "Updated" line."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.drops: list[dict[str, Any]] = []
        self.updated_text: str | None = None
        self.form_build_id: str | None = None
        self._drop: dict[str, Any] | None = None
        self._drop_depth = 0
        self._capture: str | None = None
        self._updated_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()

        if tag == "input" and attr.get("name") == "form_build_id":
            self.form_build_id = attr.get("value")
            return

        if tag != "div" and tag != "strong":
            return

        if tag == "div" and self._updated_depth:
            self._updated_depth += 1
        elif tag == "div" and "last-updated" in classes:
            self._updated_depth = 1
            self.updated_text = ""

        if self._drop is None:
            if tag == "div" and "drop-div" in classes:
                self._drop = {
                    "outer": classes,
                    "inner": [],
                    "name": "",
                    "label": "",
                }
                self._drop_depth = 1
            return

        if tag == "strong":
            self._capture = "name"
            return

        self._drop_depth += 1
        if "drop" in classes or "drop-plasma" in classes:
            self._drop["inner"] = classes
        elif "day-coverage" in classes or "appeal-mode-label" in classes:
            self._capture = "label"

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong":
            self._capture = None
            return
        if tag != "div":
            return

        if self._updated_depth:
            self._updated_depth -= 1

        if self._drop is None:
            return
        self._capture = None
        self._drop_depth -= 1
        if self._drop_depth == 0:
            self.drops.append(self._drop)
            self._drop = None

    def handle_data(self, data: str) -> None:
        if self._updated_depth:
            self.updated_text += data
        if self._drop is not None and self._capture:
            self._drop[self._capture] += data


def _parse_updated(text: str | None) -> datetime.datetime | None:
    """Parse e.g. "Updated 6:00am (AEDT), 14 October 2026"."""
    if not text:
        return None
    match = _UPDATED_RE.search(text)
    if not match:
        return None
    hour, minute, ampm, date_text = match.groups()
    try:
        date = datetime.datetime.strptime(" ".join(date_text.split()), "%d %B %Y")
    except ValueError:
        return None
    hour_24 = int(hour) % 12 + (12 if ampm.lower() == "pm" else 0)
    return date.replace(hour=hour_24, minute=int(minute), tzinfo=LIFEBLOOD_TZ)


def _parse_drop(drop: dict[str, Any]) -> tuple[str, SupplyLevel] | None:
    name = " ".join(drop["name"].split())
    key = BLOOD_TYPE_KEYS.get(name)
    if key is None:
        _LOGGER.debug("Ignoring unrecognised drop %r", name)
        return None

    label = " ".join(drop["label"].split())
    inner = drop["inner"]
    level = LABEL_LEVELS.get(label.lower())
    if level is None:
        class_levels = PLASMA_CLASS_LEVELS if key == PLASMA else RED_CELL_CLASS_LEVELS
        level = next((class_levels[c] for c in inner if c in class_levels), None)
        _LOGGER.warning(
            "Unrecognised Lifeblood level %r for %s (classes %s), read as %s",
            label, name, inner, level,
        )

    percent = None
    for cls in drop["outer"]:
        if match := _PERCENT_RE.match(cls):
            percent = float(match.group(1))

    return key, SupplyLevel(
        level=level,
        label=label,
        appeal="appeal-mode" in inner,
        percent=percent,
    )


def _region_code(drops: list[dict[str, Any]]) -> str | None:
    """Read the region code ("National", "VIC", ...) off the plasma drop."""
    for drop in drops:
        outer = drop["outer"]
        if "plasma-block" in outer:
            idx = outer.index("plasma-block")
            if idx + 1 < len(outer) and not _PERCENT_RE.match(outer[idx + 1]):
                return outer[idx + 1]
    return None


def parse_levels(html: str, region: str) -> tuple[SupplyData, str | None]:
    """Parse a full page or an AJAX fragment.

    Returns the data plus the page's form_build_id (None in a fragment),
    which the AJAX request for another region needs.
    """
    parser = _StockLevelParser()
    parser.feed(html)
    parser.close()

    data = SupplyData(
        region=region,
        region_code=_region_code(parser.drops),
        updated=_parse_updated(parser.updated_text),
    )
    for drop in parser.drops:
        if parsed := _parse_drop(drop):
            data.levels[parsed[0]] = parsed[1]
    return data, parser.form_build_id


def parse_ajax_response(payload: Any, region: str) -> SupplyData:
    """Pull the stock levels fragment out of a Drupal AJAX command list."""
    if not isinstance(payload, list):
        raise LifebloodParseError("Unexpected AJAX response shape")
    for command in payload:
        if (
            isinstance(command, dict)
            and command.get("command") == "insert"
            and isinstance(command.get("data"), str)
            and "lb-stock-levels" in command["data"]
        ):
            data, _ = parse_levels(command["data"], region)
            return data
    raise LifebloodParseError("No stock levels in AJAX response")


class LifebloodClient:
    """Fetches supply levels for a region."""

    def __init__(self, session: aiohttp.ClientSession, user_agent: str) -> None:
        self._session = session
        self._headers = {"User-Agent": user_agent}

    async def async_get_levels(self, region: str) -> SupplyData:
        """Fetch and parse the current levels for one region."""
        try:
            async with self._session.get(
                SOURCE_URL, headers=self._headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                page = await resp.text()

            data, form_build_id = parse_levels(page, region)

            # The plain GET has always been the national figures, but check
            # rather than assume - if the page ever starts defaulting to a
            # region (by geolocation, say) we'd otherwise silently report
            # that as "All Australia".
            if data.region_code != REGION_CODES[region]:
                if not form_build_id:
                    raise LifebloodParseError("No form_build_id on page")
                async with self._session.post(
                    AJAX_URL,
                    headers={**self._headers, "X-Requested-With": "XMLHttpRequest"},
                    data={
                        "lb_region_select": REGION_FORM_VALUES[region],
                        "form_build_id": form_build_id,
                        "form_id": "stock_level_form",
                        "_triggering_element_name": "lb_region_select",
                    },
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    resp.raise_for_status()
                    payload = await resp.json(content_type=None)
                regional = parse_ajax_response(payload, region)
                # The "Updated" line sits outside the fragment the AJAX call
                # replaces, so it's only ever on the full page.
                regional.updated = data.updated
                data = regional
        except (TimeoutError, aiohttp.ClientError) as err:
            raise LifebloodConnectionError(str(err) or type(err).__name__) from err
        except ValueError as err:
            # resp.json() on a body that isn't JSON.
            raise LifebloodParseError(f"Invalid AJAX response: {err}") from err

        if data.region_code != REGION_CODES[region]:
            raise LifebloodParseError(
                f"Asked for {REGION_CODES[region]} but got {data.region_code}"
            )
        if not data.levels:
            raise LifebloodParseError("No blood supply levels found on page")
        return data
