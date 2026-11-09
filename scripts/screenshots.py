"""Take the README's screenshots of the panel demo, in light and dark.

The week view and Saturday's day view at the River in the Day sailer, the
wind map, and the AI briefing, from the recorded San Diego week. They're
WebP at twice the size they're shown, so they stay sharp on dense screens.

Write the demo's data, serve the demo on 127.0.0.1, and start Chrome with
DevTools on a port, then run this with the development environment:

    .venv/bin/python scripts/demo_data.py
    npm run demo --prefix frontend -- --host 127.0.0.1
    "<Chrome>" --headless=new --remote-debugging-port=9222 about:blank
    .venv/bin/python scripts/screenshots.py

The images go in docs/images, named like week-light.webp.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
WIDTH = 1280
SCALE = 2
QUALITY = 82
PANEL = "document.querySelector('sailcast-panel')"
SHADOW = PANEL + ".shadowRoot"
# The River in the Day sailer, which has this week's windows.
RIVER = (
    "(async () => { const p = " + PANEL + "; p.spotId = 'river'; p.boatId = 'keelboat';"
    " await p.loadForecast(); await p.updateComplete; return p.forecast?.spot; })()"
)
SATURDAY = 5


def box(selector: str) -> str:
    """Return a script that measures an element in the panel, on the page."""
    return (
        "(() => { const el = " + SHADOW + ".querySelector('" + selector + "');"
        " if (!el) return null; const r = el.getBoundingClientRect();"
        " return JSON.stringify({x: r.x + scrollX, y: r.y + scrollY,"
        " w: r.width, h: r.height}); })()"
    )


# The wind chart: the card with a chart under the heading "Wind".
WIND_CHART = (
    "(() => { const s = [..." + SHADOW + ".querySelectorAll('section.card')]"
    ".find((el) => el.querySelector('svg')"
    " && el.querySelector('h2')?.textContent.trim() === 'Wind');"
    " if (!s) return null; const r = s.getBoundingClientRect();"
    " return JSON.stringify({x: r.x + scrollX, y: r.y + scrollY,"
    " w: r.width, h: r.height}); })()"
)


class Page:
    """A Chrome tab, driven over DevTools."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse, demo: str) -> None:
        """Drive a tab whose DevTools socket is open."""
        self.ws = ws
        self.demo = demo
        self.ids = iter(range(1, 1_000_000))
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.problems: list[str] = []

    async def read(self) -> None:
        """Hand replies to the calls waiting for them, and keep script errors."""
        async for raw in self.ws:
            msg = json.loads(raw.data)
            if "id" in msg and msg["id"] in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
            elif msg.get("method") == "Runtime.exceptionThrown":
                self.problems.append(
                    json.dumps(msg["params"]["exceptionDetails"])[:300]
                )

    async def send(self, method: str, **params: Any) -> dict[str, Any]:
        """Call a DevTools method and return its reply."""
        msg_id = next(self.ids)
        future = asyncio.get_running_loop().create_future()
        self.pending[msg_id] = future
        await self.ws.send_json({"id": msg_id, "method": method, "params": params})
        return await future

    async def run(self, script: str) -> Any:
        """Run a script in the page and return its value."""
        res = await self.send("Runtime.evaluate", expression=script, awaitPromise=True)
        return res["result"].get("result", {}).get("value")

    async def measure(self, script: str) -> dict[str, float] | None:
        """Return the box a measuring script found, or None."""
        found = await self.run(script)
        return json.loads(found) if found else None

    async def open(self, query: str, height: int, width: int = WIDTH) -> None:
        """Open the demo with a query, at the River in the Day sailer."""
        await self.send(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=SCALE,
            mobile=False,
        )
        await self.send("Page.navigate", url=f"{self.demo}?{query}")
        await asyncio.sleep(3)
        await self.run(RIVER)

    async def capture(self, path: Path, x: float, y: float, w: float, h: float) -> None:
        """Save part of the page as a WebP image."""
        data = await self.send(
            "Page.captureScreenshot",
            format="webp",
            quality=QUALITY,
            captureBeyondViewport=True,
            clip={"x": x, "y": y, "width": w, "height": h, "scale": 1},
        )
        image = base64.b64decode(data["result"]["data"])
        await asyncio.to_thread(path.write_bytes, image)
        print(f"{path.relative_to(ROOT)}: {len(image) // 1024} KB")


async def shoot(page: Page, theme: str, mode: str, out: Path) -> None:
    """Take one theme's screenshots."""

    def query(*parts: str) -> str:
        return "&".join(part for part in (*parts, mode) if part)

    # The week, without AI, down to the calendar's sunset row.
    await page.open(query(), 1500)
    await asyncio.sleep(1.5)
    hours = await page.measure(box(".cal-hours"))
    bottom = hours["y"] + hours["h"] + 12 if hours else 1150
    await page.capture(out / f"week-{theme}.webp", 0, 0, WIDTH, bottom)

    # Saturday, hour by hour, down to the wind chart.
    await page.open(query("view=day"), 1700)
    await page.run(
        "(async () => { const p = " + PANEL + f"; p.day = {SATURDAY};"
        " await p.updateComplete; })()"
    )
    await asyncio.sleep(1.5)
    chart = await page.measure(WIND_CHART)
    bottom = chart["y"] + chart["h"] + 16 if chart else 1100
    await page.capture(out / f"day-{theme}.webp", 0, 0, WIDTH, bottom)

    # The wind map, once its tiles and particles are drawn.
    await page.open(query("view=map"), 860)
    await asyncio.sleep(9)
    await page.capture(out / f"map-{theme}.webp", 0, 0, WIDTH, 860)

    # The AI briefing, narrower, so its text reads at the size it's shown.
    await page.open(query("ai"), 1200, width=900)
    await asyncio.sleep(1.5)
    brief = await page.measure(box(".brief"))
    if brief:
        pad = 12
        await page.capture(
            out / f"briefing-{theme}.webp",
            brief["x"] - pad,
            brief["y"] - pad,
            brief["w"] + 2 * pad,
            brief["h"] + 2 * pad,
        )


async def main() -> int:
    """Take both themes' screenshots, and fail if the panel had a script error."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--demo", default="http://127.0.0.1:5173/")
    parser.add_argument("--devtools", default="http://127.0.0.1:9222")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "images")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    problems = []
    async with aiohttp.ClientSession() as http:
        for theme, mode in (("light", ""), ("dark", "mode=night")):
            async with http.put(f"{args.devtools}/json/new?about:blank") as response:
                target = await response.json()
            async with http.ws_connect(
                target["webSocketDebuggerUrl"], max_msg_size=0
            ) as ws:
                page = Page(ws, args.demo)
                reader = asyncio.create_task(page.read())
                await page.send("Page.enable")
                await page.send("Runtime.enable")
                await shoot(page, theme, mode, args.out)
                problems += page.problems
                reader.cancel()
    for problem in problems:
        print("Script error:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
