"""Check the integration still understands Lifeblood's live page, every region.

Run daily by .github/workflows/live-check.yaml, so a page change shows up as
a failed run (and an email) the same morning, rather than as a user report.
Exits non-zero if any region fails to fetch or parse cleanly: an error, any
warning the parser logs, an unrecognised level, a missing blood type, or no
"Updated" date.

    python scripts/check_live_site.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.lifeblood.api import LifebloodClient, LifebloodError  # noqa: E402
from custom_components.lifeblood.const import ALL_BLOOD_TYPES, REGION_CODES  # noqa: E402


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def main() -> int:
    collected = _Collect()
    logging.getLogger("custom_components.lifeblood").addHandler(collected)
    problems: list[str] = []

    async with aiohttp.ClientSession() as session:
        client = LifebloodClient(session, "ha-lifeblood-live-check (+https://github.com/gurrier/lifeblood)")
        for region in REGION_CODES:
            before = len(collected.records)
            try:
                data = await client.async_get_levels(region)
            except LifebloodError as err:
                problems.append(f"{region}: {type(err).__name__}: {err}")
                print(f"{region:9} FAILED  {err}")
                continue

            missing = [t for t in ALL_BLOOD_TYPES if t not in data.levels]
            # NT doesn't collect some red cells; that's a level, not a gap.
            unknown = [t for t, lvl in data.levels.items() if lvl.level is None]
            if missing:
                problems.append(f"{region}: missing {', '.join(missing)}")
            if unknown:
                problems.append(
                    f"{region}: unrecognised level for "
                    + ", ".join(f"{t} ({data.levels[t].label!r})" for t in unknown)
                )
            if data.updated is None:
                problems.append(f"{region}: no 'Updated' date (raw: {data.updated_text!r})")
            for record in collected.records[before:]:
                problems.append(f"{region}: logged {record.levelname}: {record.getMessage()}")

            levels = " ".join(f"{t}={lvl.level}" for t, lvl in data.levels.items())
            print(f"{region:9} {data.updated:%Y-%m-%d %H:%M} {levels}")
            # Be gentle with a public site.
            await asyncio.sleep(1)

    if problems:
        print("\nProblems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nAll regions parsed cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
