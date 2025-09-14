"""Config flow for the Network Switch (SNMP) integration."""

from __future__ import annotations

import importlib
from typing import Any, cast

from pysnmp.error import PySnmpError
import pysnmp.hlapi.v3arch.asyncio as hlapi
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    Udp6TransportTarget,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
)
import voluptuous as vol

from homeassistant import requirements as ha_requirements
from homeassistant.components import snmp
from homeassistant.config_entries import ConfigFlow as HAConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_get_integration

from .const import (
    AUTH_MD5,
    AUTH_NONE,
    AUTH_SHA,
    CONF_AUTH_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_COMMUNITY_READ,
    CONF_COMMUNITY_WRITE,
    CONF_PRIV_PASSWORD,
    CONF_PRIV_TYPE,
    CONF_SNMP_VERSION,
    DOMAIN,
    PRIV_AES,
    PRIV_DES,
    PRIV_NONE,
    SNMP_V1,
    SNMP_V2C,
    SNMP_V3,
)

# Ensure submodules are imported so attributes exist at runtime
importlib.import_module("homeassistant.components.snmp.const")
importlib.import_module("homeassistant.components.snmp.util")
# Resolve component submodules via attribute access to satisfy hassfest + mypy
snmp_const = cast(Any, snmp).const
snmp_util = cast(Any, snmp).util

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.178.46"): str,
        vol.Required(CONF_SNMP_VERSION, default=SNMP_V2C): vol.In(
            [SNMP_V1, SNMP_V2C, SNMP_V3]
        ),
    }
)


async def validate_connection(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate that the provided data works by doing a simple SNMP get."""
    host: str = str(data[CONF_HOST])
    version = data.get(CONF_SNMP_VERSION)
    # Ensure requirements are installed
    integration = await async_get_integration(hass, DOMAIN)
    await ha_requirements.async_process_requirements(
        hass, integration.domain, integration.requirements
    )

    # Create SNMP target
    try:
        target = await UdpTransportTarget.create(
            (host, int(data.get("port", 161))), timeout=8
        )
    except PySnmpError:
        target = Udp6TransportTarget((host, int(data.get("port", 161))), timeout=8)

    # Build auth
    if version in (SNMP_V1, SNMP_V2C):
        mp_model = 0 if version == SNMP_V1 else 1
        auth_data = CommunityData(data["community_read"], mpModel=mp_model)
    else:
        auth_type = data.get("auth_type", "none")
        priv_type = data.get("priv_type", "none")
        username = data.get("username")
        auth_key = data.get("auth_password") or None
        priv_key = data.get("priv_password") or None
        map_auth = {"none": "none", "md5": "hmac-md5", "sha": "hmac-sha"}[auth_type]
        map_priv = {"none": "none", "des": "des", "aes": "aes-cfb-128"}[priv_type]
        auth_data = UsmUserData(
            username,
            authKey=auth_key,
            privKey=priv_key,
            authProtocol=getattr(hlapi, snmp_const.MAP_AUTH_PROTOCOLS[map_auth]),
            privProtocol=getattr(hlapi, snmp_const.MAP_PRIV_PROTOCOLS[map_priv]),
        )

    # Validate sysName
    request_args = await snmp_util.async_create_request_cmd_args(
        hass, auth_data, target, "1.3.6.1.2.1.1.5.0"
    )
    err, status, _idx, var_binds = await get_cmd(*request_args)
    if err or status:
        raise CannotConnect
    return str(var_binds[0][1]) if var_binds else host


class ConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a config flow for network-switch."""

    VERSION = 1
    _host: str | None = None
    _version: str | None = None
    _data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._version = user_input[CONF_SNMP_VERSION]
            # Ensure uniqueness per host
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            self._data.update(user_input)
            if self._version in (SNMP_V1, SNMP_V2C):
                return await self.async_step_v2c()
            return await self.async_step_v3()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_v2c(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle SNMP v1/v2c credential step."""
        errors: dict[str, str] = {}
        schema = vol.Schema(
            {
                vol.Required(CONF_COMMUNITY_READ, default="public"): str,
                vol.Optional(CONF_COMMUNITY_WRITE, default="private"): str,
            }
        )
        if user_input is not None:
            self._data.update(user_input)
            # validate connection
            try:
                title = await validate_connection(self.hass, self._data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=title, data=self._data)
        return self.async_show_form(step_id="v2c", data_schema=schema, errors=errors)

    async def async_step_v3(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle SNMP v3 credential step."""
        errors: dict[str, str] = {}
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Required(CONF_AUTH_TYPE, default=AUTH_MD5): vol.In(
                    [AUTH_NONE, AUTH_MD5, AUTH_SHA]
                ),
                vol.Optional(CONF_AUTH_PASSWORD, default="privateprivate"): str,
                vol.Required(CONF_PRIV_TYPE, default=PRIV_DES): vol.In(
                    [PRIV_NONE, PRIV_DES, PRIV_AES]
                ),
                vol.Optional(CONF_PRIV_PASSWORD, default="privateprivate"): str,
            }
        )
        if user_input is not None:
            self._data.update(user_input)
            try:
                title = await validate_connection(self.hass, self._data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(title=title, data=self._data)
        return self.async_show_form(step_id="v3", data_schema=schema, errors=errors)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
