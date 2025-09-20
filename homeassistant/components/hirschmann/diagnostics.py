"""Diagnostics support for Hirschmann network switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTH_PASSWORD,
    CONF_COMMUNITY_READ,
    CONF_COMMUNITY_WRITE,
    CONF_PRIV_PASSWORD,
    DOMAIN,
)
from .coordinator import NetworkSwitchCoordinator

TO_REDACT_ENTRY = {
    CONF_HOST,
    CONF_USERNAME,
    CONF_COMMUNITY_READ,
    CONF_COMMUNITY_WRITE,
    CONF_AUTH_PASSWORD,
    CONF_PRIV_PASSWORD,
}

TO_REDACT_DEVICE = {"mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    diagnostics: dict[str, Any] = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
    }

    coordinator: NetworkSwitchCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is None:
        return diagnostics

    device_meta = async_redact_data(coordinator.device_meta, TO_REDACT_DEVICE)

    diagnostics["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "last_exception": repr(coordinator.last_exception)
        if coordinator.last_exception
        else None,
    }

    diagnostics["device"] = {
        "meta": device_meta,
        "temperature_c": device_meta.get("temperature_c"),
        "uptime_seconds": device_meta.get("uptime_seconds"),
    }

    diagnostics["ports"] = {
        str(if_index): data for if_index, data in sorted(coordinator.data.items())
    }

    return diagnostics
