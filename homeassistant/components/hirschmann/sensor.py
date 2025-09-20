"""Port status sensors for Network Switch integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetworkSwitchCoordinator, normalize_port_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hirschmann sensors from a config entry."""
    coordinator: NetworkSwitchCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    entities.extend(
        [
            NetworkDeviceTemperatureSensor(coordinator),
            NetworkDeviceUptimeSensor(coordinator),
        ]
    )
    for if_index in sorted(coordinator.data.keys()):
        entities.append(NetworkPortSensor(coordinator, if_index))
        poe = coordinator.data[if_index].get("poe")
        if poe is not None:
            entities.append(NetworkPortPoeDetectionSensor(coordinator, if_index))
            # Only add power sensor if we have a value initially or expect availability later
            entities.append(NetworkPortPoePowerSensor(coordinator, if_index))
    async_add_entities(entities)


class NetworkPortSensor(CoordinatorEntity[NetworkSwitchCoordinator], SensorEntity):
    """Represents a port status sensor (Up/Down)."""

    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator: NetworkSwitchCoordinator, if_index: int) -> None:
        """Initialize the port status sensor."""
        super().__init__(coordinator)
        self._if_index = if_index
        host = coordinator.entry.data["host"]
        port_name = normalize_port_name(coordinator.data[if_index]["name"])
        self._attr_name = f"Port {port_name}"
        self._attr_unique_id = f"{host}-port-{if_index}"

    @property
    def native_value(self) -> StateType:
        """Return current operational status (Up/Down)."""
        data = self.coordinator.data.get(self._if_index)
        if not data:
            return None
        return data["status"]

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
            "manufacturer": "Generic",
            "name": name,
        }
        if connections:
            info["connections"] = connections
        if meta.get("hardware"):
            info["model"] = meta["hardware"]
        if meta.get("firmware"):
            info["sw_version"] = meta["firmware"]
        return info


class NetworkPortPoeDetectionSensor(
    CoordinatorEntity[NetworkSwitchCoordinator], SensorEntity
):
    """PoE detection status sensor for a port."""

    _attr_icon = "mdi:lan-pending"

    def __init__(self, coordinator: NetworkSwitchCoordinator, if_index: int) -> None:
        """Initialize the PoE detection status sensor."""
        super().__init__(coordinator)
        self._if_index = if_index
        host = coordinator.entry.data["host"]
        name = normalize_port_name(coordinator.data[if_index]["name"])
        self._attr_name = f"Port {name} PoE Status"
        self._attr_unique_id = f"{host}-port-poe-detect-{if_index}"

    @property
    def native_value(self) -> StateType:
        """Return PoE detection status text if available."""
        poe = self.coordinator.data.get(self._if_index, {}).get("poe")
        if not poe:
            return None
        return poe.get("detection_status")

    @property
    def device_info(self):
        """Return device info for the parent switch."""
        # Same device info as other entities
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


class NetworkPortPoePowerSensor(
    CoordinatorEntity[NetworkSwitchCoordinator], SensorEntity
):
    """PoE delivered power sensor for a port."""

    _attr_icon = "mdi:flash"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(self, coordinator: NetworkSwitchCoordinator, if_index: int) -> None:
        """Initialize the PoE power sensor."""
        super().__init__(coordinator)
        self._if_index = if_index
        host = coordinator.entry.data["host"]
        name = normalize_port_name(coordinator.data[if_index]["name"])
        self._attr_name = f"Port {name} PoE Power"
        self._attr_unique_id = f"{host}-port-poe-power-{if_index}"

    @property
    def native_value(self) -> StateType:
        """Return delivered power in Watts if available."""
        poe = self.coordinator.data.get(self._if_index, {}).get("poe")
        if not poe:
            return None
        return poe.get("power_w")

    @property
    def available(self) -> bool:
        """Return True if PoE info is available for this port."""
        poe = self.coordinator.data.get(self._if_index, {}).get("poe")
        return poe is not None

    @property
    def device_info(self):
        """Return device info for the parent switch."""
        # Same device info as other entities
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


class NetworkDeviceTemperatureSensor(
    CoordinatorEntity[NetworkSwitchCoordinator], SensorEntity
):
    """Device temperature sensor exposed for diagnostics."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NetworkSwitchCoordinator) -> None:
        """Initialize the device temperature sensor."""
        super().__init__(coordinator)
        host = coordinator.entry.data["host"]
        self._attr_name = "Temperature"
        self._attr_unique_id = f"{host}-device-temperature"

    @property
    def native_value(self) -> StateType:
        """Return the current device temperature if available."""
        return self.coordinator.device_meta.get("temperature_c")

    @property
    def available(self) -> bool:
        """Return true if a temperature reading is currently available."""
        return self.coordinator.device_meta.get("temperature_c") is not None

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
            "manufacturer": "Generic",
            "name": name,
        }
        if connections:
            info["connections"] = connections
        if meta.get("hardware"):
            info["model"] = meta["hardware"]
        if meta.get("firmware"):
            info["sw_version"] = meta["firmware"]
        return info


class NetworkDeviceUptimeSensor(
    CoordinatorEntity[NetworkSwitchCoordinator], SensorEntity
):
    """Device uptime sensor exposed for diagnostics."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NetworkSwitchCoordinator) -> None:
        """Initialize the device uptime sensor."""
        super().__init__(coordinator)
        host = coordinator.entry.data["host"]
        self._attr_name = "Uptime"
        self._attr_unique_id = f"{host}-device-uptime"

    @property
    def native_value(self) -> StateType:
        """Return current device uptime in seconds."""
        return self.coordinator.device_meta.get("uptime_seconds")

    @property
    def available(self) -> bool:
        """Return true if an uptime value is currently available."""
        return self.coordinator.device_meta.get("uptime_seconds") is not None

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
            "manufacturer": "Generic",
            "name": name,
        }
        if connections:
            info["connections"] = connections
        if meta.get("hardware"):
            info["model"] = meta["hardware"]
        if meta.get("firmware"):
            info["sw_version"] = meta["firmware"]
        return info
