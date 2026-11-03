#!/usr/bin/env python3
"""Write docs/safety-limits.md from the limits table.

Usage: .venv/bin/python scripts/safety_limits_doc.py
A test fails when the page is out of date.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.sailcast import limits  # noqa: E402
from custom_components.sailcast.limits import (  # noqa: E402
    BOAT_LIMITS,
    FOOT,
    SKILL_WIND_LIMITS,
    WARNING_EVENTS,
    WARNING_FLOORS,
    Level,
    WarningGroup,
)
from custom_components.sailcast.profiles import SizeClass  # noqa: E402

PAGE = ROOT / "docs" / "safety-limits.md"

SIZES = {
    SizeClass.DINGHY: "Dinghy and beach cat",
    SizeClass.SMALL_KEELBOAT: "Small keelboat 16–25 ft",
    SizeClass.CRUISER: "Cruiser 25–35 ft",
    SizeClass.LARGE_CRUISER: "Large cruiser 35 ft+",
}
LEVELS = {
    Level.GOOD: "Good",
    Level.CAUTION: "Caution",
    Level.NOT_RECOMMENDED: "Not recommended",
    Level.DANGEROUS: "Dangerous",
}
GROUPS = {
    WarningGroup.ADVISORY: None,
    WarningGroup.FOG_AND_SPRAY: None,
    WarningGroup.GALE: None,
    WarningGroup.STORM: None,
    WarningGroup.WATCH: "Any marine watch",
}

SOURCES = """\
## Where the numbers come from

- **Dinghies.** Community sailing programs and race committees:
  - Milwaukee Community Sailing Center's skill ratings top out at 10, 15 and 20 kt.
  - Australian Optimist fleets use 15, 20 and 25 kt limits.
  - Minneapolis Sailing Center stops all sailing at 21 kt.
  - A Sydney club won't start ILCA 4 races in gusts over 20 kt, or ILCA 6 and 7 races over 25 kt.
  - US Sailing's junior women's championship caps racing at 25 kt.
- **Small keelboats.** A US Sailing championship sailed in J/22s doesn't race above 17 kt sustained or with 22 kt gusts. The J/22 class doesn't start races above 25 kt, which is also where a typical East Coast Small Craft Advisory range begins.
- **Cruisers.** The Recreational Craft Directive's design categories:
  - Category C boats are built for up to Force 6 (22–27 kt) and 2 m waves.
  - Category B boats are built for up to Force 8 (34–40 kt) and 4 m waves.
  - Gale force, 34 kt, is "dangerous" for the large class.
- **Waves.** The largest waves are about twice the significant wave height. Model tests after the 1979 Fastnet race found that breaking waves about 30–35% of a yacht's length capsized some yachts, and waves about 55–60% of its length capsized all of them. "Not recommended" starts where the largest waves approach the first level, and "dangerous" near the second.
- **Skill levels.** The Beginner and Intermediate limits were set by the maintainer. They're close to Milwaukee Community Sailing Center's skill ratings.
- **Official warnings.** NWS warning criteria (directive 10-315). A typical East Coast office issues a Small Craft Advisory for sustained winds or frequent gusts of 25–33 kt for more than 2 hours, or seas of 5 ft or more.
- **Thunderstorms.** The NWS's boating advice: don't go out if thunderstorms are forecast, and wait 30 minutes after the last thunder or lightning.
- **Everything else** is a judgment call, listed in the plan for review.

The plan's [Sources](PLAN.md#18-sources) section links to each of these.
"""


def _number(value: float) -> str:
    return f"{value:g}"


def _feet(meters: float) -> str:
    return f"{meters / FOOT:g} ({meters:.1f})"


def render() -> str:
    """Return the page."""
    sizes = list(SizeClass)
    lines = [
        "# SailCast safety limits",
        "",
        f"Version {limits.VERSION}. This page is generated from "
        "[`limits.py`](../custom_components/sailcast/limits.py) by "
        "`scripts/safety_limits_doc.py`, so don't edit it by hand. Each number "
        "is where that rating starts. SailCast is advisory: official forecasts "
        "and warnings come first, and the skipper decides.",
        "",
        "## Sustained wind (kt)",
        "",
        "| Boat size | Caution | Dangerous |",
        "| --- | --- | --- |",
        *(
            f"| {SIZES[size]} | {_number(BOAT_LIMITS[size].wind[0])} "
            f"| {_number(BOAT_LIMITS[size].wind[1])} |"
            for size in sizes
        ),
        "",
        '"Not recommended" for sustained wind comes from the sailor\'s skill level:',
        "",
        "| Skill | Not recommended when sustained wind is over |",
        "| --- | --- |",
        *(
            f"| {skill.name.title()} | "
            f"{'No limit' if limit is None else f'{_number(limit)} kt'} |"
            for skill, limit in SKILL_WIND_LIMITS.items()
        ),
        "",
        "Gusts never count toward the skill limit. An advanced sailor's rating "
        "from wind and gusts alone stays at caution until the boat's dangerous "
        "level.",
        "",
        "## Gusts (kt)",
        "",
        "| Boat size | Caution | Dangerous | Gusty: one level worse when gusts are this far over the mean |",
        "| --- | --- | --- | --- |",
        *(
            f"| {SIZES[size]} | {_number(BOAT_LIMITS[size].gust[0])} "
            f"| {_number(BOAT_LIMITS[size].gust[1])} "
            f"| {_number(BOAT_LIMITS[size].gusty)} |"
            for size in sizes
        ),
        "",
        "For an advanced sailor, gusty conditions mean at least caution instead.",
        "",
        "## Significant wave height, ft (m)",
        "",
        "| Boat size | Caution | Not recommended | Dangerous |",
        "| --- | --- | --- | --- |",
        *(
            f"| {SIZES[size]} | "
            + " | ".join(_feet(height) for height in BOAT_LIMITS[size].wave)
            + " |"
            for size in sizes
        ),
        "",
        "## Modifiers and minimums",
        "",
        "Each modifier makes the rating one level worse, but modifiers alone "
        "can't push it past not recommended.",
        "",
        "| Rule | Boat sizes | Effect |",
        "| --- | --- | --- |",
        "| Steep, short waves: height in m over period^3.3 / 250, or height in "
        "ft at least the period in s, once waves reach the caution height "
        "| All | One level worse |",
        f"| Wind of {_number(limits.AGAINST_CURRENT_WIND)} kt or more within "
        f"{_number(limits.AGAINST_CURRENT_ANGLE)}° of straight against the "
        f"current, with current of at least "
        f"{_number(limits.AGAINST_CURRENT_MODIFIER)} × wave period (kt) "
        "| All | One level worse |",
        f"| Same, with current of at least {_number(limits.AGAINST_CURRENT_FLOOR)} "
        "× wave period | Dinghy, small keelboat | At least not recommended |",
        f"| Offshore wind, {_number(limits.OFFSHORE_MODIFIER_WIND)} kt or more "
        "| Dinghy | One level worse |",
        f"| Offshore wind, {_number(limits.OFFSHORE_FLOOR_WIND)} kt or more "
        "| Dinghy | At least not recommended |",
        f"| Wind chill {_number(limits.WIND_CHILL * 9 / 5 + 32)} °F "
        f"({_number(limits.WIND_CHILL)} °C) or lower | Dinghy, small keelboat "
        "| One level worse |",
        f"| Visibility below {_number(limits.VISIBILITY_SMALL[0])} nm / below "
        f"{_number(limits.VISIBILITY_SMALL[1])} nm | Dinghy, small keelboat "
        "| Caution / not recommended |",
        f"| Visibility below {_number(limits.VISIBILITY_CRUISER[0])} nm / below "
        f"{_number(limits.VISIBILITY_CRUISER[1])} nm | Cruisers "
        "| Caution / not recommended |",
        "| Thunderstorms forecast | All | Not recommended for dinghies and "
        "small keelboats, caution for cruisers |",
        f"| Thunderstorms possible: CAPE of {_number(limits.THUNDERSTORM_CAPE)} "
        f"J/kg and a {_number(limits.THUNDERSTORM_RAIN)}% chance of rain or "
        "more | Dinghy, small keelboat | At least caution |",
        "",
        "The current rules use a wave period of at least "
        f"{_number(limits.AGAINST_CURRENT_MIN_PERIOD)} s. Forecast visibility "
        "never makes an hour dangerous on its own.",
        "",
        "## Official warnings",
        "",
        "The lowest rating while a warning is in effect, at every skill level.",
        "",
        "| Warning | " + " | ".join(SIZES[size] for size in sizes) + " |",
        "| --- |" + " --- |" * len(sizes),
    ]
    for group, label in GROUPS.items():
        events = [event for event, g in WARNING_EVENTS.items() if g is group]
        name = label or "; ".join(events)
        floors = " | ".join(LEVELS[WARNING_FLOORS[group][size]] for size in sizes)
        lines.append(f"| {name} | {floors} |")
    lines += ["", SOURCES]
    return "\n".join(lines)


def main() -> None:
    """Write the page."""
    PAGE.write_text(render())
    print(f"wrote {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
