"""Switch entities for enabling/disabling switch ports via SNMP ifAdminStatus."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetworkSwitchCoordinator, normalize_port_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hirschmann switches from a config entry."""
    coordinator: NetworkSwitchCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for if_index in sorted(coordinator.data.keys()):
        entities.append(NetworkPortSwitch(coordinator, if_index))
        poe = coordinator.data[if_index].get("poe")
        if poe is not None:
            entities.append(NetworkPortPoeSwitch(coordinator, if_index))
    async_add_entities(entities)


class NetworkPortSwitch(CoordinatorEntity[NetworkSwitchCoordinator], SwitchEntity):
    """Represents a switch to control ifAdminStatus (on=up, off=down)."""

    _attr_icon = "mdi:server-network"

    def __init__(self, coordinator: NetworkSwitchCoordinator, if_index: int) -> None:
        """Initialize the admin-status switch."""
        super().__init__(coordinator)
        self._if_index = if_index
        host = coordinator.entry.data["host"]
        name = normalize_port_name(coordinator.data[if_index]["name"])
        self._attr_name = f"Port {name}"
        self._attr_unique_id = f"{host}-port-admin-{if_index}"

    @property
    def is_on(self) -> bool:
        """Return True if admin status is up (on)."""
        data = self.coordinator.data.get(self._if_index)
        if not data:
            return False
        return bool(data.get("admin_on", False))

    @property
    def device_info(self):
        """Return device info for the parent switch."""
        host = self.coordinator.entry.data["host"]
        meta = getattr(self.coordinator, "_device_meta", {})
        connections = set()
        if mac := meta.get("mac"):
            connections.add((CONNECTION_NETWORK_MAC, mac))
        name = meta.get("sys_name") or f"Network Switch {host}"
        info = {
            "identifiers": {(DOMAIN, host)},
            "manufacturer": "Hirschmann Automation and Control GmbH",
            "name": name,
        }
        if connections:
            info["connections"] = connections
        if meta.get("hardware"):
            info["model"] = meta["hardware"]
        if meta.get("firmware"):
            info["sw_version"] = meta["firmware"]
        return info

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (set admin status up)."""
        await self.coordinator.async_set_admin_status(self._if_index, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (set admin status down)."""
        await self.coordinator.async_set_admin_status(self._if_index, False)
        await self.coordinator.async_request_refresh()


class NetworkPortPoeSwitch(CoordinatorEntity[NetworkSwitchCoordinator], SwitchEntity):
    """Switch to control PoE enable/disable for a PoE-capable port."""

    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator: NetworkSwitchCoordinator, if_index: int) -> None:
        """Initialize the PoE control switch."""
        super().__init__(coordinator)
        self._if_index = if_index
        host = coordinator.entry.data["host"]
        name = normalize_port_name(coordinator.data[if_index]["name"])
        self._attr_name = f"Port {name} PoE"
        self._attr_unique_id = f"{host}-port-poe-{if_index}"

    @property
    def available(self) -> bool:
        """Return True if PoE is available on this port."""
        return self.coordinator.data.get(self._if_index, {}).get("poe") is not None

    @property
    def is_on(self) -> bool:
        """Return True if PoE admin is enabled for this port."""
        poe = self.coordinator.data.get(self._if_index, {}).get("poe")
        if not poe:
            return False
        enabled = poe.get("enabled")
        return bool(enabled) if enabled is not None else False

    @property
    def device_info(self):
        """Return device info for the parent switch."""
        # Reuse device info from base switch
        host = self.coordinator.entry.data["host"]
        meta = getattr(self.coordinator, "_device_meta", {})
        connections = set()
        if mac := meta.get("mac"):
            connections.add((CONNECTION_NETWORK_MAC, mac))
        name = meta.get("sys_name") or f"Network Switch {host}"
        info = {
            "identifiers": {(DOMAIN, host)},
            "manufacturer": "Generic",
            "name": name,
        }
        if connections:
            info["connections"] = connections
        poe = meta.get("poe_power_w")
        if poe is not None:
            info["model"] = f"PoE budget: {poe} W"
        elif meta.get("hardware"):
            info["model"] = meta["hardware"]
        if meta.get("firmware"):
            info["sw_version"] = meta["firmware"]
        return info

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PoE on this port."""
        await self.coordinator.async_set_poe_admin(self._if_index, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PoE on this port."""
        await self.coordinator.async_set_poe_admin(self._if_index, False)
        await self.coordinator.async_request_refresh()
