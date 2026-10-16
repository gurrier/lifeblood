"""Constants for the Lifeblood integration."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

DOMAIN = "lifeblood"

USER_AGENT_TEMPLATE = "ha-lifeblood/{version} (+https://github.com/gurrier/lifeblood)"

CONF_REGION = "region"
CONF_BLOOD_TYPES = "blood_types"

SOURCE_URL = (
    "https://www.lifeblood.com.au/donors/blood-plasma-platelets/blood-supply-levels"
)

# Lifeblood publishes once a day, around 6:00am Sydney time. Rather than
# polling a public website on a fixed interval - which, counting from
# whenever Home Assistant started, could land at 5:59am and then sit on
# yesterday's figures for the rest of the interval - check at fixed Sydney
# times: shortly after publication, and again in the evening to catch a
# late update. Plus once at startup.
CHECK_TIMES: tuple[datetime.time, ...] = (
    datetime.time(6, 30),
    datetime.time(18, 30),
)

# Home Assistant fires a scheduled refresh anywhere from ~1s early to ~0.5s
# late (it rounds the loop clock down to a whole second, then adds a random
# sub-second stagger). A slot this close is treated as already reached, so
# an early refresh counts as that slot instead of being followed by a
# second fetch a moment later.
SCHEDULE_MARGIN = datetime.timedelta(minutes=1)

# A failed check is retried after this, doubling on each further failure,
# rather than waiting for the next scheduled check up to 12 hours away - but
# never retrying harder than that while the site is already struggling.
RETRY_INTERVAL = datetime.timedelta(minutes=30)

# A fetch the config flow just made to validate the region is reused by the
# coordinator's first refresh if it's younger than this.
VALIDATION_CACHE_TTL = datetime.timedelta(minutes=5)

# Region keys are what we store in the config entry. Each maps to the value
# Lifeblood's own region <select> posts, and to the short code it writes into
# the plasma drop's class list - which is how we check the page we got back
# is actually for the region we asked for.
REGION_FORM_VALUES: dict[str, str] = {
    "national": "national",
    "act": "australian capital territory",
    "nsw": "new south wales",
    "nt": "northern territory",
    "qld": "queensland",
    "sa": "south australia",
    "tas": "tasmania",
    "vic": "victoria",
    "wa": "western australia",
}

REGION_CODES: dict[str, str] = {
    "national": "National",
    "act": "ACT",
    "nsw": "NSW",
    "nt": "NT",
    "qld": "QLD",
    "sa": "SA",
    "tas": "TAS",
    "vic": "VIC",
    "wa": "WA",
}

# Device names, which prefix every entity's friendly name, so they're kept
# short: "VIC O positive" fits a dashboard button where "Victoria O positive"
# doesn't. The config flow's dropdown shows the full names (translations).
REGION_NAMES: dict[str, str] = {
    "national": "Australia",
    "act": "ACT",
    "nsw": "NSW",
    "nt": "NT",
    "qld": "QLD",
    "sa": "SA",
    "tas": "TAS",
    "vic": "VIC",
    "wa": "WA",
}

PLASMA = "plasma"

# Keyed by the label Lifeblood prints under each drop.
BLOOD_TYPE_KEYS: dict[str, str] = {
    "O+": "o_positive",
    "O-": "o_negative",
    "A+": "a_positive",
    "A-": "a_negative",
    "B+": "b_positive",
    "B-": "b_negative",
    "AB+": "ab_positive",
    "AB-": "ab_negative",
    "Plasma": PLASMA,
}

ALL_BLOOD_TYPES: list[str] = list(BLOOD_TYPE_KEYS.values())

LEVEL_CRITICAL = "critical"
LEVEL_VERY_LOW = "very_low"
LEVEL_LOW = "low"
LEVEL_NEED_MORE = "need_more"
LEVEL_OK = "ok"
LEVEL_GOOD = "good"
LEVEL_NOT_COLLECTED = "not_collected"

# Worst first. "Critical" isn't in Lifeblood's own legend - it's an appeal
# banner laid over "Very low" (the drop's aria-label still says very low) -
# but it's what donors see, so it's kept as its own, worse, state.
RED_CELL_LEVELS: list[str] = [
    LEVEL_CRITICAL,
    LEVEL_VERY_LOW,
    LEVEL_LOW,
    LEVEL_NEED_MORE,
    LEVEL_OK,
    LEVEL_GOOD,
    LEVEL_NOT_COLLECTED,
]

PLASMA_LEVELS: list[str] = [LEVEL_NEED_MORE, LEVEL_OK, LEVEL_GOOD]


def selected_blood_types(config_entry: ConfigEntry) -> list[str]:
    """The blood types this entry tracks - options win over initial setup."""
    return config_entry.options.get(
        CONF_BLOOD_TYPES,
        config_entry.data.get(CONF_BLOOD_TYPES, ALL_BLOOD_TYPES),
    )
