"""Tests for the two notification blueprints, run as automations."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import shutil
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant.common import MockConfigEntry

BLUEPRINTS = Path(__file__).parent.parent / "blueprints" / "automation" / "sailcast"


@pytest.fixture
def phone(hass: HomeAssistant, tmp_path: Path) -> str:
    """Return a phone with the Home Assistant app, in a config folder of its own."""
    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(domain="mobile_app", title="Phone")
    entry.add_to_hass(hass)
    return (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("mobile_app", "phone")}
        )
        .id
    )


@pytest.fixture
def notified() -> Iterator[AsyncMock]:
    """Catch the notifications the app would get."""
    with patch(
        "homeassistant.components.mobile_app.device_action.async_call_action_from_config"
    ) as call:
        yield call


async def use_blueprint(hass: HomeAssistant, name: str, **inputs: Any) -> None:
    """Set up an automation from one of SailCast's blueprints."""
    folder = Path(hass.config.path("blueprints", "automation", "sailcast"))
    await hass.async_add_executor_job(_copy, name, folder)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": name.removesuffix(".yaml"),
                "use_blueprint": {"path": f"sailcast/{name}", "input": inputs},
            }
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get(f"automation.{name.removesuffix('.yaml')}") is not None


def _copy(name: str, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINTS / name, folder / name)


def sent(notified: AsyncMock) -> list[tuple[str, str]]:
    """Return each notification's title and message."""
    found = []
    for call in notified.mock_calls:
        _hass, config, variables, _context = call.args
        title, message = (
            value.async_render(variables) if isinstance(value, Template) else value
            for value in (config["title"], config["message"])
        )
        found.append((str(title), str(message)))
    return found


async def test_planned_sail_changed(
    hass: HomeAssistant, phone: str, notified: AsyncMock
) -> None:
    """SailCast's own message reaches the phone, for the chosen sailor only."""
    await use_blueprint(
        hass, "planned_sail_changed.yaml", notify_device=phone, sailor="alex"
    )
    for sailor in ("Alex", "Sam"):
        hass.bus.async_fire(
            "sailcast_planned_sail_changed",
            {"sailor": sailor, "message": f"The forecast for {sailor}'s sail..."},
        )
    await hass.async_block_till_done()
    assert sent(notified) == [
        ("SailCast: forecast changed", "The forecast for Alex's sail...")
    ]


@pytest.mark.parametrize(
    "case",
    [
        (
            "calendar.sam_sailing",
            [
                (
                    "Sailing tomorrow",
                    "River: Keelboat: 2 PM to 4:56 PM, score 92 (great). "
                    "NW 6 to 8 kt, gusts to 17 kt.",
                )
            ],
        ),
        # Alex sails at weekends, so Tuesday brings nothing.
        ("calendar.alex_sailing", []),
    ],
)
async def test_windows_tomorrow(
    hass: HomeAssistant,
    phone: str,
    loaded: MockConfigEntry,
    notified: AsyncMock,
    case: tuple[str, list[tuple[str, str]]],
) -> None:
    """The evening before, each of tomorrow's windows is sent, one a line."""
    calendar, expected = case
    await use_blueprint(
        hass, "windows_tomorrow.yaml", calendar=calendar, notify_device=phone
    )
    for action in ("trigger", "turn_off"):
        # Turned off, the automation stops waiting for 7 PM.
        await hass.services.async_call(
            "automation",
            action,
            {"entity_id": "automation.windows_tomorrow"},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert sent(notified) == expected
