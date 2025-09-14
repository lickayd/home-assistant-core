"""Constants for the network-switch integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "hirschmann"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

DEFAULT_PORT = 161
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# Config keys
CONF_SNMP_VERSION = "snmp_version"
CONF_COMMUNITY_READ = "community_read"
CONF_COMMUNITY_WRITE = "community_write"
CONF_AUTH_TYPE = "auth_type"
CONF_AUTH_PASSWORD = "auth_password"
CONF_PRIV_TYPE = "priv_type"
CONF_PRIV_PASSWORD = "priv_password"

# SNMP versions
SNMP_V1 = "v1"
SNMP_V2C = "v2c"
SNMP_V3 = "v3"

# Auth/Priv types
AUTH_NONE = "none"
AUTH_MD5 = "md5"
AUTH_SHA = "sha"

PRIV_NONE = "none"
PRIV_DES = "des"
PRIV_AES = "aes"

# OIDs
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"
OID_IFTYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IFOPERSTATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IFADMINSTATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IFNAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_BRIDGE_ADDR = "1.3.6.1.2.1.17.1.1.0"  # dot1dBaseBridgeAddress
OID_HW_TYPE_BASE = "1.3.6.1.4.1.248.14.1.1.9.1.3.1"  # Append .0 if needed
OID_FW_VER_BASE = "1.3.6.1.4.1.248.14.1.1.9.1.5.1"  # Append .0 if needed
OID_POE_POWER_W = "1.3.6.1.2.1.105.1.3.1.1.2.1"  # Gauge32 Watts

# PoE (IEEE 802.3af) PSE MIB (pethPsePortTable)
OID_PETH_PORT_TABLE = "1.3.6.1.2.1.105.1.1.1"
OID_PETH_PORT_ADMIN_ENABLE = (
    f"{OID_PETH_PORT_TABLE}.3"  # pethPsePortAdminEnable (true(1)/false(2))
)
OID_PETH_PORT_DETECT_STATUS = f"{OID_PETH_PORT_TABLE}.6"  # pethPsePortDetectionStatus
OID_PETH_PORT_POWER_W = "1.3.6.1.4.1.248.14.2.14.2.1.2"  # Vendor OID, Integer32 Watts

# Detection status map (best-effort common mapping)
PETH_DETECT_STATUS_MAP = {
    1: "Disabled",
    2: "Searching",
    3: "Delivering",
    4: "Fault",
    5: "Test",
    6: "Other",
}
