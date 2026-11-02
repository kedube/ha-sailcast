<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/sailcast/brand/dark_logo.png">
    <img alt="SailCast" src="custom_components/sailcast/brand/logo.png" width="360">
  </picture>
</p>

SailCast is a Home Assistant integration for sailors. It turns wind, gust, wave, tide, current and weather forecasts into:

- a safety rating for every boat size, hour by hour
- a 0–100 sailing score for each sailor and boat
- the best sailing windows of the week
- plain-language advice

It adds a SailCast page to the sidebar, with a week calendar, a day view, an animated wind map and settings, plus entities and a calendar for automations.

> [!IMPORTANT]
> SailCast is advisory. Official forecasts and warnings come first, and the skipper always decides.

## Status

SailCast is in early development. Milestone 0 is done: you can set SailCast up, add spots, boats and sailors, and open its panel, which lists them. Forecasts and safety ratings come in milestone 1. The [plan](docs/PLAN.md) describes everything SailCast will do and the order of work.

## Install

SailCast needs Home Assistant 2026.11 or newer. It isn't in the Marketplace's default catalog yet. Once a release is published, add `https://github.com/kedube/ha-sailcast` as a custom repository in Marketplace, with the type **Integration**. Then install SailCast and restart Home Assistant.

## Set up

1. Go to **Settings → Devices & services → Add integration** and pick **SailCast**.
2. On SailCast's page, add your spots, boats and sailors:
   - **Spot:** a pin on the water, the kind of water, and which directions are offshore and open to waves.
   - **Boat:** a name, a size and a length.
   - **Sailor:** their skill, their usual boat and others, and when they can sail.
3. Open **SailCast** in the sidebar.

Each sailor rates their own skill, which sets their limit for sustained wind: up to 10 kt for Beginner, 16 kt for Intermediate, and no limit for Advanced. Gusts don't count toward it.

## Development

You need [uv](https://docs.astral.sh/uv/) and Node 24 or newer.

| Command | What it does |
| --- | --- |
| `scripts/setup` | Creates `.venv` with Python 3.14, Home Assistant and the test tools, installs and builds the panel, and turns on the git hooks. |
| `scripts/develop` | Starts Home Assistant from `config/` with this integration, at <http://localhost:8123>. |
| `scripts/lint` | Formats and lints the Python and TypeScript. |
| `.venv/bin/pytest` | Runs the integration's tests. |
| `npm run dev` in `frontend/` | Rebuilds the panel on save. |
| `npm run demo` in `frontend/` | Serves the panel with made-up data. Add `?mode=night`, `?units=metric`, `?admin=0` or `?empty`. |
| `npm test` in `frontend/` | Runs the panel's tests. |

On macOS, the python.org build of Python ships without SSL certificates. If you use it, run its "Install Certificates" command once, or Home Assistant can't reach any API.

### Privacy

The repository holds no personal data. Test data uses neutral names and shifted coordinates. The git hooks that `scripts/setup` turns on check every commit and commit message against a list of private terms kept outside the repository, in `~/.config/sailcast/private-terms.txt` or the file named by `SAILCAST_PRIVATE_TERMS`. Put one term per line, matched as a whole word. Lines starting with `re:` are regular expressions.

## Credits

- Wordmark: [Outfit](https://github.com/Outfitio/Outfit-Fonts), under the SIL Open Font License 1.1. More in [docs/brand](docs/brand/README.md).

## License

[GPL-3.0](LICENSE)
