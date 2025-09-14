"""Test the Network Switch (SNMP) config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.components.hirschmann.config_flow import CannotConnect
from homeassistant.components.hirschmann.const import (
    AUTH_MD5,
    CONF_AUTH_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_COMMUNITY_READ,
    CONF_COMMUNITY_WRITE,
    CONF_PRIV_PASSWORD,
    CONF_PRIV_TYPE,
    CONF_SNMP_VERSION,
    DOMAIN,
    PRIV_AES,
    SNMP_V2C,
    SNMP_V3,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry


async def test_show_user_form(hass: HomeAssistant) -> None:
    """Test we get the initial form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_v2c_flow_success(hass: HomeAssistant) -> None:
    """Test a full successful v2c user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "homeassistant.components.hirschmann.config_flow.validate_connection",
            return_value="My Switch",
        ),
        patch(
            "homeassistant.components.hirschmann.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "1.2.3.4", CONF_SNMP_VERSION: SNMP_V2C}
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "v2c"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_COMMUNITY_READ: "public", CONF_COMMUNITY_WRITE: ""},
        )

        assert result3["type"] == FlowResultType.CREATE_ENTRY
        assert result3["title"] == "My Switch"
        data = result3["data"]
        assert data["host"] == "1.2.3.4"
        assert data[CONF_SNMP_VERSION] == SNMP_V2C
        assert data[CONF_COMMUNITY_READ] == "public"
        assert data.get(CONF_COMMUNITY_WRITE) == ""
        assert mock_setup_entry.called


async def test_v3_flow_success(hass: HomeAssistant) -> None:
    """Test a full successful v3 user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "homeassistant.components.hirschmann.config_flow.validate_connection",
            return_value="SNMPv3 Switch",
        ),
        patch(
            "homeassistant.components.hirschmann.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "5.6.7.8", CONF_SNMP_VERSION: SNMP_V3}
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "v3"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                "username": "user1",
                CONF_AUTH_TYPE: AUTH_MD5,
                CONF_AUTH_PASSWORD: "apass",
                CONF_PRIV_TYPE: PRIV_AES,
                CONF_PRIV_PASSWORD: "ppass",
            },
        )

        assert result3["type"] == FlowResultType.CREATE_ENTRY
        assert result3["title"] == "SNMPv3 Switch"
        data = result3["data"]
        assert data["host"] == "5.6.7.8"
        assert data[CONF_SNMP_VERSION] == SNMP_V3
        assert data["username"] == "user1"
        assert data[CONF_AUTH_TYPE] == AUTH_MD5
        assert data[CONF_AUTH_PASSWORD] == "apass"
        assert data[CONF_PRIV_TYPE] == PRIV_AES
        assert data[CONF_PRIV_PASSWORD] == "ppass"
        assert mock_setup_entry.called


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.hirschmann.config_flow.validate_connection",
        side_effect=CannotConnect(),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "1.2.3.4", CONF_SNMP_VERSION: SNMP_V2C}
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "v2c"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_COMMUNITY_READ: "public", CONF_COMMUNITY_WRITE: ""},
        )
        assert result3["type"] == FlowResultType.FORM
        assert result3["errors"]["base"] == "cannot_connect"


async def test_already_configured(hass: HomeAssistant) -> None:
    """Test abort when already configured for host (unique_id)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "1.2.3.4",
            CONF_SNMP_VERSION: SNMP_V2C,
            CONF_COMMUNITY_READ: "public",
        },
        title="Existing",
        unique_id="1.2.3.4",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # We abort right at user step when host matches unique_id
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "1.2.3.4", CONF_SNMP_VERSION: SNMP_V2C}
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
