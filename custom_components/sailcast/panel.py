"""The SailCast sidebar panel."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Final

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH: Final = "sailcast"
PANEL_ELEMENT: Final = "sailcast-panel"
PANEL_ICON: Final = "mdi:sail-boat"

# The built panel module. CI builds it into each release; for development,
# run `npm run build` in frontend/.
STATIC_URL: Final = "/sailcast_static"
FRONTEND_DIR: Final = Path(__file__).parent / "frontend"
MODULE_FILE: Final = "sailcast-panel.js"

DATA_STATIC_REGISTERED: HassKey[bool] = HassKey(f"{DOMAIN}_static_registered")


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve the panel's module and add the panel to the sidebar."""
    # A static path can only be registered once while Home Assistant runs,
    # and the entry can be reloaded many times.
    if not hass.data.get(DATA_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[DATA_STATIC_REGISTERED] = True
    # The panel stays while the entry reloads after a settings change, so
    # whoever is using it isn't sent elsewhere.
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        return

    version = await hass.async_add_executor_job(_module_version)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=NAME,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}/{MODULE_FILE}?v={version}",
        embed_iframe=False,
        require_admin=False,
        # The panel pads itself for notches and rounded corners.
        handle_safe_area=True,
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the panel from the sidebar."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


def _module_version() -> str:
    """Return a short hash of the module, so browsers load each new build."""
    try:
        module = (FRONTEND_DIR / MODULE_FILE).read_bytes()
    except FileNotFoundError:
        _LOGGER.warning(
            "The SailCast panel isn't built. Install a release, or run "
            "`npm run build` in the repository's frontend folder"
        )
        return "missing"
    return hashlib.sha256(module).hexdigest()[:12]
