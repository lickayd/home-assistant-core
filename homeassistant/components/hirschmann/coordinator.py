"""Coordinator and SNMP helpers for Hirschmann integration (SNMP)."""

from __future__ import annotations

import importlib
import logging
from typing import Any, cast

from pysnmp.error import PySnmpError
import pysnmp.hlapi.v3arch.asyncio as hlapi
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    Udp6TransportTarget,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
    set_cmd,
)
from pysnmp.proto.rfc1902 import Integer

from homeassistant.components import snmp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTH_MD5,
    AUTH_NONE,
    AUTH_SHA,
    CONF_SNMP_VERSION,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    OID_BRIDGE_ADDR,
    OID_FW_VER_BASE,
    OID_HW_TYPE_BASE,
    OID_IFADMINSTATUS,
    OID_IFNAME,
    OID_IFOPERSTATUS,
    OID_IFTYPE,
    OID_PETH_PORT_ADMIN_ENABLE,
    OID_PETH_PORT_DETECT_STATUS,
    OID_PETH_PORT_POWER_W,
    OID_PETH_PORT_TABLE,
    OID_POE_POWER_W,
    OID_SYSNAME,
    PETH_DETECT_STATUS_MAP,
    PRIV_AES,
    PRIV_DES,
    PRIV_NONE,
    SNMP_V1,
    SNMP_V2C,
)

_LOGGER = logging.getLogger(__name__)

# Resolve component submodules via attribute access to satisfy hassfest + mypy
importlib.import_module("homeassistant.components.snmp.const")
importlib.import_module("homeassistant.components.snmp.util")
snmp_const = cast(Any, snmp).const
snmp_util = cast(Any, snmp).util


def _safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return repr(value)


class _V3ArchBackend:
    """Async pysnmp v3arch backend (v1/v2c/v3), aligned with snmp integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        version: str,
        entry_data: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.version = version
        self.entry_data = entry_data
        self._auth_data: UsmUserData | CommunityData | None = None
        self._target: UdpTransportTarget | Udp6TransportTarget | None = None
        self._cmd_args: tuple | None = None

    async def async_init(self) -> None:
        try:
            target = await UdpTransportTarget.create((self.host, self.port), timeout=8)
        except PySnmpError:
            target = Udp6TransportTarget((self.host, self.port), timeout=8)

        if self.version in (SNMP_V1, SNMP_V2C):
            mp_model = 0 if self.version == SNMP_V1 else 1
            auth_data = CommunityData(
                self.entry_data["community_read"], mpModel=mp_model
            )
        else:
            auth_type = self.entry_data.get("auth_type", AUTH_NONE)
            priv_type = self.entry_data.get("priv_type", PRIV_NONE)
            username = self.entry_data["username"]
            map_auth = {AUTH_NONE: "none", AUTH_MD5: "hmac-md5", AUTH_SHA: "hmac-sha"}[
                auth_type
            ]
            map_priv = {PRIV_NONE: "none", PRIV_DES: "des", PRIV_AES: "aes-cfb-128"}[
                priv_type
            ]
            auth_data = UsmUserData(
                username,
                authKey=self.entry_data.get("auth_password") or None,
                privKey=self.entry_data.get("priv_password") or None,
                authProtocol=getattr(hlapi, snmp_const.MAP_AUTH_PROTOCOLS[map_auth]),
                privProtocol=getattr(hlapi, snmp_const.MAP_PRIV_PROTOCOLS[map_priv]),
            )

        self._auth_data = auth_data
        self._target = target
        self._cmd_args = await snmp_util.async_create_command_cmd_args(
            self.hass, auth_data, target
        )

    async def async_get(self, oid: str):
        if self._cmd_args is None:
            await self.async_init()
        assert self._cmd_args is not None
        engine, auth, target, context = self._cmd_args
        req_args = (
            engine,
            auth,
            target,
            context,
            hlapi.ObjectType(hlapi.ObjectIdentity(oid)),
        )
        return await get_cmd(*req_args)

    async def async_walk(self, base_oid: str) -> list[tuple[Any, Any]]:
        if self._cmd_args is None:
            await self.async_init()
        assert self._cmd_args is not None
        engine, auth, target, context = self._cmd_args
        walker = bulk_walk_cmd(
            engine,
            auth,
            target,
            context,
            0,
            50,
            hlapi.ObjectType(hlapi.ObjectIdentity(base_oid)),
            lexicographicMode=False,
        )
        results: list[tuple[Any, Any]] = []
        async for errind, errstat, _erridx, res in walker:
            if errind or errstat:
                raise UpdateFailed(str(errind or errstat))
            results.extend([(vb[0], vb[1]) for vb in res])
        return results

    async def async_set_integer(self, oid: str, value: int) -> None:
        """Perform an SNMP SET for an integer value."""
        if self._cmd_args is None:
            await self.async_init()
        assert self._cmd_args is not None
        engine, auth, target, context = self._cmd_args
        # For v1/v2c, use write community if provided
        if self.version in (SNMP_V1, SNMP_V2C):
            write_comm = (self.entry_data.get("community_write") or "").strip()
            if write_comm:
                auth = CommunityData(
                    write_comm, mpModel=(0 if self.version == SNMP_V1 else 1)
                )
        obj = hlapi.ObjectType(hlapi.ObjectIdentity(oid), Integer(value))
        err, status, _idx, _rest = await set_cmd(engine, auth, target, context, obj)
        if err or status:
            raise UpdateFailed(str(err or status))


class NetworkSwitchCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Coordinator to manage SNMP polling and interface discovery."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator with Home Assistant and config entry."""
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name="Hirschmann",
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.entry = entry
        self._host = entry.data["host"]
        self._port = entry.data.get("port", DEFAULT_PORT)
        self._version = entry.data[CONF_SNMP_VERSION]
        self._backend: _V3ArchBackend | None = _V3ArchBackend(
            hass, self._host, self._port, self._version, dict(entry.data)
        )

        # Discovered Ethernet ports: index -> name
        self._ports: dict[int, str] = {}
        self._device_meta: dict[str, Any] = {}
        # Map ifIndex -> "group.port" for pethPsePortTable rows
        self._poe_index: dict[int, str] = {}

    async def async_close(self) -> None:
        """Close resources (no-op for pysnmp asyncio)."""
        # pysnmp asyncio engine does not require explicit close
        return

    async def _async_snmp_get(self, oid: str) -> tuple[Any, Any, Any, Any]:
        if not self._backend:
            raise UpdateFailed("SNMP backend not initialized")
        return await self._backend.async_get(oid)

    async def _async_snmp_walk(self, base_oid: str) -> list[tuple[Any, Any]]:
        if not self._backend:
            raise UpdateFailed("SNMP backend not initialized")
        return await self._backend.async_walk(base_oid)

    async def _discover_ports(self) -> None:
        """Discover Ethernet ports (ifType=6) and get their names."""
        ethernet_indexes: set[int] = set()
        for oid, value in await self._walk_simple(OID_IFTYPE):
            # OID ends with .<index>
            try:
                index = int(_safe_str(oid).split(".")[-1])
                if int(value) == 6:  # ethernetCsmacd(6)
                    ethernet_indexes.add(index)
            except (ValueError, IndexError, TypeError):
                continue

        names: dict[int, str] = {}
        for oid, value in await self._walk_simple(OID_IFNAME):
            try:
                index = int(_safe_str(oid).split(".")[-1])
            except (ValueError, IndexError, TypeError):
                continue
            if index in ethernet_indexes:
                names[index] = _safe_str(value)
        self._ports = names

    async def _discover_poe(self) -> None:
        """Discover PoE-capable ports by walking pethPsePortInterfaceIndex and matching to ifIndex."""
        mapping: dict[int, str] = {}
        try:
            rows = await self._async_snmp_walk(OID_PETH_PORT_TABLE)
        except UpdateFailed:
            rows = []
        for oid, _value in rows:
            try:
                # suffix is group.port
                suffix = str(oid).split(".")[-2:]
                gp = ".".join(suffix)
                mapping[int(suffix[1])] = gp
            except (ValueError, IndexError, TypeError):
                continue
        self._poe_index = mapping

    async def _get_scalar_str(self, oid_base: str) -> str | None:
        """Get a scalar value as string; try OID and OID.0."""
        for candidate in (oid_base, f"{oid_base}.0"):
            try:
                err, status, _idx, var_binds = await self._async_snmp_get(candidate)
            except UpdateFailed:
                continue
            if err or status or not var_binds:
                continue
            return _safe_str(var_binds[0][1])
        return None

    async def _populate_device_meta(self) -> None:
        """Fetch device-level meta info: sysName, MAC, HW type, FW version."""
        # sysName
        sys_name = None
        try:
            err, status, _idx, var_binds = await self._async_snmp_get(OID_SYSNAME)
            if not (err or status) and var_binds:
                sys_name = _safe_str(var_binds[0][1])
        except UpdateFailed:
            sys_name = None

        # bridge MAC address
        mac_str: str | None = None
        try:
            err, status, _idx, var_binds = await self._async_snmp_get(OID_BRIDGE_ADDR)
            if not (err or status) and var_binds:
                raw = var_binds[0][1]
                try:
                    b = bytes(raw)
                    mac_str = ":".join(f"{x:02x}" for x in b)
                except (TypeError, ValueError):
                    mac_str = _safe_str(raw)
        except UpdateFailed:
            mac_str = None

        # Hardware type
        hw_type = await self._get_scalar_str(OID_HW_TYPE_BASE)

        # Firmware version: trim before "RAM:"
        fw_ver_raw = await self._get_scalar_str(OID_FW_VER_BASE)
        fw_version = None
        if fw_ver_raw is not None:
            fw_version = fw_ver_raw.split("RAM:", 1)[0].strip()

        self._device_meta = {
            "sys_name": sys_name,
            "mac": mac_str,
            "hardware": hw_type,
            "firmware": fw_version,
        }
        # PoE power budget (Watts), optional
        try:
            err, status, _idx, var_binds = await self._async_snmp_get(OID_POE_POWER_W)
            if not (err or status) and var_binds:
                try:
                    poe_w = int(var_binds[0][1])
                except (TypeError, ValueError):
                    poe_w = None
                if poe_w is not None:
                    self._device_meta["poe_power_w"] = poe_w
        except UpdateFailed:
            # Ignore if not available
            pass

    async def _walk_simple(self, base_oid: str) -> list[tuple[Any, Any]]:
        vbs = await self._async_snmp_walk(base_oid)
        return [(vb[0], vb[1]) for vb in vbs]

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        """Fetch latest port statuses.

        Returns a mapping: ifIndex -> {"name": str, "status": "Up"|"Down", "admin_on": bool}
        """
        if not self._backend:
            raise UpdateFailed("SNMP backend not available")
        # On first run, discover ports
        if not self._ports:
            await self._discover_ports()
            await self._populate_device_meta()

        # Read operational statuses
        statuses: dict[int, str] = {}
        for oid, value in await self._walk_simple(OID_IFOPERSTATUS):
            try:
                index = int(_safe_str(oid).split(".")[-1])
                statuses[index] = "Up" if int(value) == 1 else "Down"
            except (ValueError, IndexError, TypeError):
                continue

        # Read admin statuses
        admin: dict[int, bool] = {}
        for oid, value in await self._walk_simple(OID_IFADMINSTATUS):
            try:
                index = int(_safe_str(oid).split(".")[-1])
                admin[index] = int(value) == 1  # up(1)=on, down(2)=off
            except (ValueError, IndexError, TypeError):
                continue

        # Discover PoE mapping once
        if not self._poe_index:
            await self._discover_poe()

        result: dict[int, dict[str, Any]] = {}
        for idx, name in self._ports.items():
            state = statuses.get(idx, "Down")
            poe: dict[str, Any] | None = None
            if idx in self._poe_index:
                poe = {}
                gp = self._poe_index[idx]
                # peth admin enable
                try:
                    err, st, _ix, vb = await self._async_snmp_get(
                        f"{OID_PETH_PORT_ADMIN_ENABLE}.{gp}"
                    )
                    poe["enabled"] = not err and not st and vb and int(vb[0][1]) == 1
                except UpdateFailed:
                    poe["enabled"] = None
                # detection status
                try:
                    err, st, _ix, vb = await self._async_snmp_get(
                        f"{OID_PETH_PORT_DETECT_STATUS}.{gp}"
                    )
                    if not err and not st and vb:
                        code = int(vb[0][1])
                        poe["detection_status"] = PETH_DETECT_STATUS_MAP.get(
                            code, str(code)
                        )
                    else:
                        poe["detection_status"] = None
                except UpdateFailed:
                    poe["detection_status"] = None
                # delivered power (vendor OID per ifIndex)
                try:
                    err, st, _ix, vb = await self._async_snmp_get(
                        f"{OID_PETH_PORT_POWER_W}.{idx}"
                    )
                    if not err and not st and vb:
                        poe["power_w"] = int(vb[0][1])
                except UpdateFailed:
                    pass

            result[idx] = {
                "name": name,
                "status": state,
                "admin_on": admin.get(idx, False),
                "poe": poe,
            }
        return result

    async def async_test_connection(self) -> str:
        """Test connectivity by querying sysName and return it."""
        err, status, _idx, var_binds = await self._async_snmp_get(OID_SYSNAME)
        if err or status:
            raise UpdateFailed(str(err or status))
        if not var_binds:
            raise UpdateFailed("No data returned")
        # var_binds: [(ObjectType(ObjectIdentity(...), value))]
        return _safe_str(var_binds[0][1])

    async def async_set_admin_status(self, if_index: int, enable: bool) -> None:
        """Set ifAdminStatus for a given interface index to up/down."""
        # Build full OID
        oid = f"{OID_IFADMINSTATUS}.{if_index}"
        if not self._backend:
            raise UpdateFailed("SNMP backend not initialized")
        # Delegate to backend
        await self._backend.async_set_integer(oid, 1 if enable else 2)

    async def async_set_poe_admin(self, if_index: int, enable: bool) -> None:
        """Enable/disable PoE at pethPsePortAdminEnable for given interface."""
        if if_index not in self._poe_index:
            raise UpdateFailed("PoE not supported on this port")
        gp = self._poe_index[if_index]
        oid = f"{OID_PETH_PORT_ADMIN_ENABLE}.{gp}"
        if not self._backend:
            raise UpdateFailed("SNMP backend not initialized")
        await self._backend.async_set_integer(oid, 1 if enable else 2)
