"""Constants for the Wingto integration."""

CONF_BROKER_PORT = "broker_port"
CONF_GATEWAY_MODEL = "gateway_model"
CONF_IP_RANGE = "ip_range"
CONF_AUTO_CONFIG = "auto_config"

WINGTO_ZIGBEE_BRIDGE_EVENT = "wingto_zigbee_bridge_event"
WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_RECALL_SCENE = "recall_scene_message_received"
WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_SENSOR_ALARM = "sensor_alarm_message_received"
WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_ALARM = "lock_alarm_message_received"

WZB_LOCK_ALARM_TYPE = "alarm_type_of_lock"

WZB_LOCK_ALARM_DOORBELL = "doorbell went"  # {01 82}
WZB_LOCK_ALARM_FACTORY_RESET = "lock reset to factory defaults"  # {02 83}, 01
WZB_LOCK_ALARM_DEADBOLT_JAMMED = "deadbolt jammed"  # 00
WZB_LOCK_ALARM_POWER_CYCLED = "RF module power cycled"  # 03
WZB_LOCK_ALARM_TAMPER_CODE_LIMIT = "tamper: wrong code entry limit"  # 04
WZB_LOCK_ALARM_TAMPER_REMOVED = "tamper: front escutcheon removed from main"  # 05
WZB_LOCK_ALARM_FORCED_OPEN = "forced door open under door locked condition"  # 06
WZB_LOCK_ALARM_HELD = "be held"  # 0x80
WZB_LOCK_ALARM_NOT_FULLY_LOCKED = "not fully locked"  # 0x81
WZB_LOCK_ALARM_DOOR_OPEN = "door kept open for a too long time"  # 0x82
WZB_LOCK_ALARM_KEY_REMAINED = "forgot to pull out the key"  # 0x83

CONF_BRIGHTNESS_RANGE_MODE = "brightness_range_mode"
CONF_COUNTRYCODE = "country_code"
CONF_CURR_TEMP_DIVIDER = "curr_temp_divider"
CONF_DISCOVERY_INTERVAL = "discovery_interval"
CONF_MAX_KELVIN = "max_kelvin"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_KELVIN = "min_kelvin"
CONF_MIN_TEMP = "min_temp"
CONF_QUERY_DEVICE = "query_device"
CONF_QUERY_INTERVAL = "query_interval"
CONF_SET_TEMP_DIVIDED = "set_temp_divided"
CONF_SUPPORT_COLOR = "support_color"
CONF_TEMP_DIVIDER = "temp_divider"
CONF_TEMP_STEP_OVERRIDE = "temp_step_override"

DOMAIN = "wingto_zigbee_bridge"

SIGNAL_CONFIG_ENTITY = "wingto_config"
SIGNAL_DELETE_ENTITY = "wingto_delete"
SIGNAL_UPDATE_ENTITY = "wingto_update"

WINGTO_API = "wingto_api"
WINGTO_DISCOVERY_NEW = "wingto_discovery_new_{}"

WINGTO_PLATFORMS = {
    "wingto": "Wingto",
    "smart_life": "Smart Life",
    "jinvoo_smart": "Jinvoo Smart",
}
