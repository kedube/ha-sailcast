# SailCast settings

SailCast's settings are its spots, boats and sailors, plus a few options. Change them on the **Settings** tab of the SailCast panel, or under **Settings → Devices & services → SailCast**. Both edit the same settings, and only administrators can change them. Saving a change updates the panel, entities and calendars right away.

Adding SailCast itself asks for nothing. Its dialog shows a safety note, and SailCast is ready once you submit it.

## Spots

A spot is a place you sail from. Each one is a device, with its own entities.

| Setting | What it does |
| --- | --- |
| Name | The spot's name in the panel and in entity names, such as Harbor or Lake. |
| Location | A pin on the water where you sail. The circle around it, reaching 15 km from the pin unless you change it (2 to 50 km), sets the area the wind map opens on. |
| Water | Open coast, bay, estuary or river, or lake. Rivers and lakes get waves worked out from the wind and the open water upwind. Open coasts and bays get the ocean model's waves. |
| Offshore wind | The directions wind blows away from the shore from. In a dinghy, an offshore wind of 8 kt or more makes the rating one level worse, and 12 kt or more makes it at least not recommended. |
| Open to waves from | The directions with open water, where waves can build. The ocean model's waves from other directions are reduced. Left empty, SailCast uses the directions it measures on the shoreline. |
| Open water upwind | Rivers and lakes only. SailCast measures how far open water reaches each way from the pin; set this to use one distance instead. |

### Data sources

After the spot, SailCast suggests the nearest sources for its pin. Pick **None** to leave one out. [Outside the US](../README.md#outside-the-us) says what each country has.

| Setting | What it does |
| --- | --- |
| Tide station | Tide heights, highs and lows. The ocean model's rough tide is only there to pick by hand when nothing else covers the spot. |
| Current station | For the rule on wind against the current. Pick one only if it's close to where you sail. |
| Official warnings | Where official warnings, such as a Small Craft Advisory, come from. On a lake with no marine zone, pick the National Weather Service's alerts at the pin. |
| Buoy | Readings of wind, waves and water temperature from a buoy or coastal station. A fresh reading nudges the next few hours. |
| Airport | Hourly reports of wind, visibility and air temperature. If there's a choice, pick one near the water. |
| Your own sensors | Wind speed, gusts, wind direction, air temperature and water temperature from your own weather station or a boat's instruments. They come first, ahead of the buoy and airport, and SailCast takes them to be at the spot. |

## Boats

| Setting | What it does |
| --- | --- |
| Name | The boat's name in the panel and the calendar. |
| Size | Dinghy or beach cat, small keelboat, cruiser or large cruiser. Each size has its own limits for wind, gusts and waves, listed in [the safety limits](safety-limits.md). |
| Length | Shown with the boat. The size sets its limits. |
| Navigation lights | Turn it on if the boat has working navigation lights. Then hours after dark count too: they're rated and scored, and windows can start before sunrise and run past sunset, within the sailor's times. Off by default, so a boat without lights is only rated in daylight. |

## Sailors

A sailor is a person who sails. Each one is a device, with ratings, scores and windows for every spot.

| Setting | What it does |
| --- | --- |
| Name | The sailor's name in the panel, entity names and notifications. |
| Skill | Beginner, up to 10 kt of sustained wind; Intermediate, up to 16 kt; or Advanced, with no wind limit, only guidance. Each sailor rates their own skill. Gusts don't count toward the limit, and skill never loosens an official warning or a rating of dangerous. |
| Usual boat | The boat SailCast rates unless the sailor picks another. |
| Other boats | Other boats the sailor takes out. The panel can rate any of them. |
| Sailing days | The days windows are found on. Every day unless you change it. |
| Hours each day | When windows can start and end, set for each sailing day, such as 5 PM on weekdays and sunrise at weekends. Left empty, they follow sunrise and sunset, or allow any hour in a boat with navigation lights. Sailors saved before each day had its own hours keep their one start and finish on every sailing day. |
| Home Assistant user | The panel opens on this sailor for that user. |

### One day's hours

For one date, such as a day off, change the hours under that day in the week view: **Free all day**, **Not sailing**, or hours of its own. Only that date changes, and SailCast forgets the change once the day has passed. **Back to usual hours** undoes it. Administrators can change any sailor's day, and other users the sailor that's linked to them. These changes are kept by SailCast, not in the sailor's settings.

### Comfort

What the sailor enjoys. These change scores, never a safety rating.

| Setting | What it does |
| --- | --- |
| Ideal wind from, up to | Narrows each boat's ideal wind range. Left empty, the boat's own range is used, up to the skill limit. |
| Coldest air they enjoy | Scores drop in colder air. Left empty, 50 °F (10 °C). |
| Rain | Avoid rain, a little rain is fine, or rain doesn't bother them. A little rain is fine unless you change it. |

### Automatic calendar

Adds the sailor's best window each chosen day to a calendar, at most one event a day, and keeps it in step with the forecast until 6 PM the evening before. [Your own calendar](../README.md#your-own-calendar) explains how it works.

| Setting | What it does |
| --- | --- |
| Calendar | Any calendar that accepts new events, such as Local Calendar, Google Calendar or CalDAV. Leave empty to turn automatic adding off. |
| Days | The days to add a window on. Needed when a calendar is set. |
| Only windows scoring | Good or better, 60 and up, or great, 80 and up. Good or better unless you change it. |
| How far ahead | Today and tomorrow, the next 3 days, the next 5 days, or the whole week. The next 3 days unless you change it, since forecasts change most beyond three days. |
| Spots | The spots to add windows from. When windows at different spots overlap, only the best one is added. Needed when a calendar is set. |

## Options

Under **Settings → Devices & services → SailCast → Configure**. Saving reloads SailCast.

| Option | What it does |
| --- | --- |
| WorldTides API key | Tide predictions anywhere, from [worldtides.info](https://www.worldtides.info), with your own account. A spot that uses it costs about 3 credits every five days. The key stays in Home Assistant and never reaches the panel. Leave empty to remove it. |
| Offer AI summaries | Adds a **Summarize with AI** button to the panel's day view. Off unless you turn it on. See [AI summary](../README.md#ai-summary). |
| AI task | The AI task that writes summaries. Leave empty to use Home Assistant's default, set under **Settings → System → AI**. |
