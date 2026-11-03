# SailCast safety limits

Version 1. This page is generated from [`limits.py`](../custom_components/sailcast/limits.py) by `scripts/safety_limits_doc.py`, so don't edit it by hand. Each number is where that rating starts. SailCast is advisory: official forecasts and warnings come first, and the skipper decides.

## Sustained wind (kt)

| Boat size | Caution | Dangerous |
| --- | --- | --- |
| Dinghy and beach cat | 15 | 21 |
| Small keelboat 16–25 ft | 18 | 25 |
| Cruiser 25–35 ft | 22 | 28 |
| Large cruiser 35 ft+ | 25 | 34 |

"Not recommended" for sustained wind comes from the sailor's skill level:

| Skill | Not recommended when sustained wind is over |
| --- | --- |
| Beginner | 10 kt |
| Intermediate | 16 kt |
| Advanced | No limit |

Gusts never count toward the skill limit. An advanced sailor's rating from wind and gusts alone stays at caution until the boat's dangerous level.

## Gusts (kt)

| Boat size | Caution | Dangerous | Gusty: one level worse when gusts are this far over the mean |
| --- | --- | --- | --- |
| Dinghy and beach cat | 20 | 25 | 10 |
| Small keelboat 16–25 ft | 22 | 30 | 10 |
| Cruiser 25–35 ft | 28 | 34 | 15 |
| Large cruiser 35 ft+ | 34 | 41 | 15 |

For an advanced sailor, gusty conditions mean at least caution instead.

## Significant wave height, ft (m)

| Boat size | Caution | Not recommended | Dangerous |
| --- | --- | --- | --- |
| Dinghy and beach cat | 1 (0.3) | 2 (0.6) | 4 (1.2) |
| Small keelboat 16–25 ft | 2 (0.6) | 4 (1.2) | 6.5 (2.0) |
| Cruiser 25–35 ft | 3 (0.9) | 6 (1.8) | 10 (3.0) |
| Large cruiser 35 ft+ | 4 (1.2) | 8 (2.4) | 12 (3.7) |

## Modifiers and minimums

Each modifier makes the rating one level worse, but modifiers alone can't push it past not recommended.

| Rule | Boat sizes | Effect |
| --- | --- | --- |
| Steep, short waves: height in m over period^3.3 / 250, or height in ft at least the period in s, once waves reach the caution height | All | One level worse |
| Wind of 10 kt or more within 60° of straight against the current, with current of at least 0.25 × wave period (kt) | All | One level worse |
| Same, with current of at least 0.5 × wave period | Dinghy, small keelboat | At least not recommended |
| Offshore wind, 8 kt or more | Dinghy | One level worse |
| Offshore wind, 12 kt or more | Dinghy | At least not recommended |
| Wind chill 32 °F (0 °C) or lower | Dinghy, small keelboat | One level worse |
| Visibility below 2 nm / below 1 nm | Dinghy, small keelboat | Caution / not recommended |
| Visibility below 1 nm / below 0.5 nm | Cruisers | Caution / not recommended |
| Visibility measured nearby below 0.5 nm | Dinghy, small keelboat | Dangerous, for the hour under way |
| Visibility measured nearby below 0.25 nm | Cruisers | Dangerous, for the hour under way |
| Thunderstorms forecast | All | Not recommended for dinghies and small keelboats, caution for cruisers |
| Thunderstorms possible: CAPE of 1000 J/kg and a 40% chance of rain or more | Dinghy, small keelboat | At least caution |

The current rules use a wave period of at least 3 s. Forecast visibility never makes an hour dangerous on its own; a visibility measured at the spot's airport or buoy can, for the hour under way.

## Official warnings

The lowest rating while a warning is in effect, at every skill level.

| Warning | Dinghy and beach cat | Small keelboat 16–25 ft | Cruiser 25–35 ft | Large cruiser 35 ft+ |
| --- | --- | --- | --- | --- |
| Small Craft Advisory; Brisk Wind Advisory; Lake Wind Advisory; Wind Advisory; Strong wind warning; MeteoAlarm yellow wind, yellow thunderstorm, yellow coastal event warning | Not recommended | Not recommended | Caution | Caution |
| Dense Fog Advisory; Dense Smoke Advisory; Freezing Spray Advisory; Freezing Fog Advisory; MeteoAlarm yellow fog, orange fog, red fog warning | Not recommended | Not recommended | Caution | Caution |
| Gale Warning; Hazardous Seas Warning; Heavy Freezing Spray Warning; High Wind Warning; Freezing spray warning; MeteoAlarm orange wind, orange coastal event warning | Dangerous | Dangerous | Dangerous | Not recommended |
| Storm Warning; Hurricane Force Wind Warning; Tropical Storm Warning; Hurricane Warning; Storm Surge Warning; Special Marine Warning; Tsunami Warning; Extreme Wind Warning; Severe Thunderstorm Warning; Tornado Warning; Snow Squall Warning; Squall warning; Waterspout warning; MeteoAlarm red wind, orange thunderstorm, red thunderstorm, red coastal event warning | Dangerous | Dangerous | Dangerous | Dangerous |
| Any watch for wind, storms, squalls, waves, spray, surge or tsunamis | Caution | Caution | Caution | Caution |

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
