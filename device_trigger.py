"""Provides device triggers for dev_trigger."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.automation import (
    AutomationActionType,
    AutomationTriggerInfo,
)
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry
from homeassistant.helpers.typing import ConfigType
from . import DOMAIN
# TODO specify your supported trigger types.
from .const import (
    WINGTO_ZIGBEE_BRIDGE_EVENT,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_RECALL_SCENE,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_SENSOR_ALARM,
    # WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_DOORBELL,
    # WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_RESET,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_ALARM,
    WZB_LOCK_ALARM_DOORBELL,
    WZB_LOCK_ALARM_FACTORY_RESET,
    WZB_LOCK_ALARM_DEADBOLT_JAMMED,
    WZB_LOCK_ALARM_POWER_CYCLED,
    WZB_LOCK_ALARM_TAMPER_CODE_LIMIT,
    WZB_LOCK_ALARM_TAMPER_REMOVED,
    WZB_LOCK_ALARM_FORCED_OPEN,
    WZB_LOCK_ALARM_HELD,
    WZB_LOCK_ALARM_NOT_FULLY_LOCKED,
    WZB_LOCK_ALARM_DOOR_OPEN,
    WZB_LOCK_ALARM_KEY_REMAINED,
    WZB_LOCK_ALARM_TYPE
)

TRIGGER_TYPE_ON_RECALL_SCENE_MSG = "on_recall_scene_msg"
TRIGGER_TYPE_SENSOR_ALARM_SCENE_MSG = "on_sensor_alarm_msg"
# TRIGGER_TYPE_LOCK_DOORBELL = "on_lock_doorbell"
# TRIGGER_TYPE_LOCK_RESET = "on_lock_reset"
TRIGGER_TYPE_LOCK_ALARM = "on_lock_alarm"

vol_lock_alarm_type = vol.In((
    WZB_LOCK_ALARM_DOORBELL,
    WZB_LOCK_ALARM_FACTORY_RESET,
    WZB_LOCK_ALARM_DEADBOLT_JAMMED,
    WZB_LOCK_ALARM_POWER_CYCLED,
    WZB_LOCK_ALARM_TAMPER_CODE_LIMIT,
    WZB_LOCK_ALARM_TAMPER_REMOVED,
    WZB_LOCK_ALARM_FORCED_OPEN,
    WZB_LOCK_ALARM_HELD,
    WZB_LOCK_ALARM_NOT_FULLY_LOCKED,
    WZB_LOCK_ALARM_DOOR_OPEN,
    WZB_LOCK_ALARM_KEY_REMAINED,
))

TRIGGER_TYPES = {
    TRIGGER_TYPE_ON_RECALL_SCENE_MSG,
    TRIGGER_TYPE_SENSOR_ALARM_SCENE_MSG,
    # TRIGGER_TYPE_LOCK_DOORBELL,
    # TRIGGER_TYPE_LOCK_RESET,
    TRIGGER_TYPE_LOCK_ALARM
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(WZB_LOCK_ALARM_TYPE): vol_lock_alarm_type,
    }
)


async def async_get_triggers(
        hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for dev_trigger devices."""
    registry = await entity_registry.async_get_registry(hass)
    triggers = []

    # TODO Read this comment and remove it.
    # This example shows how to iterate over the entities of this device
    # that match this integration. If your triggers instead rely on
    # events fired by devices without entities, do something like:
    # zha_device = await _async_get_zha_device(hass, device_id)
    # return zha_device.device_triggers

    # Get all the integrations entities for this device
    for entry in entity_registry.async_entries_for_device(registry, device_id):
        if entry.platform != DOMAIN:
            continue
        # Add triggers for each entity that belongs to this integration
        # TODO add your own triggers.
        base_trigger = {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: entry.entity_id,
        }
        if entry.domain in ('switch', 'scene'):
            triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_ON_RECALL_SCENE_MSG})
        elif entry.supported_features == 'sensor_alarm':
            triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_SENSOR_ALARM_SCENE_MSG})
        elif entry.domain == 'lock':
            # triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_LOCK_DOORBELL})
            # triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_LOCK_RESET})
            triggers.append({**base_trigger, CONF_TYPE: TRIGGER_TYPE_LOCK_ALARM})

    return triggers


async def async_attach_trigger(
        hass: HomeAssistant,
        config: ConfigType,
        action: AutomationActionType,
        automation_info: AutomationTriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    # TODO Implement your own logic to attach triggers.
    # Use the existing state or event triggers from the automation integration.

    if config[CONF_TYPE] not in TRIGGER_TYPES:
        raise ValueError(f'{config[CONF_TYPE]} is unknown.')

    registry = await entity_registry.async_get_registry(hass)
    for entry in entity_registry.async_entries_for_device(registry, config[CONF_DEVICE_ID]):
        if entry.platform != DOMAIN:
            continue
        if entry.entity_id != config[CONF_ENTITY_ID]:
            continue
        unique_id = entry.unique_id
        break
    else:
        raise ValueError(f'{config[CONF_ENTITY_ID]} is unknown.')

    if config[CONF_TYPE] == TRIGGER_TYPE_ON_RECALL_SCENE_MSG:
        event_config = {
            event.CONF_PLATFORM: "event",
            event.CONF_EVENT_TYPE: WINGTO_ZIGBEE_BRIDGE_EVENT,
            event.CONF_EVENT_DATA: {
                "subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_RECALL_SCENE,
                "unique_id": unique_id,
                "std_scene_id": 0,
            },
        }
    elif config[CONF_TYPE] == TRIGGER_TYPE_SENSOR_ALARM_SCENE_MSG:
        event_config = {
            event.CONF_PLATFORM: "event",
            event.CONF_EVENT_TYPE: WINGTO_ZIGBEE_BRIDGE_EVENT,
            event.CONF_EVENT_DATA: {
                "subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_SENSOR_ALARM,
                "unique_id": unique_id,
            },
        }
    # elif config[CONF_TYPE] == TRIGGER_TYPE_LOCK_DOORBELL:
    #     event_config = {
    #         event.CONF_PLATFORM: "event",
    #         event.CONF_EVENT_TYPE: WINGTO_ZIGBEE_BRIDGE_EVENT,
    #         event.CONF_EVENT_DATA: {
    #             "subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_DOORBELL,
    #             "unique_id": unique_id,
    #         },
    #     }
    # elif config[CONF_TYPE] == TRIGGER_TYPE_LOCK_RESET:
    #     event_config = {
    #         event.CONF_PLATFORM: "event",
    #         event.CONF_EVENT_TYPE: WINGTO_ZIGBEE_BRIDGE_EVENT,
    #         event.CONF_EVENT_DATA: {
    #             "subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_RESET,
    #             "unique_id": unique_id,
    #         },
    #     }
    elif config[CONF_TYPE] == TRIGGER_TYPE_LOCK_ALARM:
        event_config = {
            event.CONF_PLATFORM: "event",
            event.CONF_EVENT_TYPE: WINGTO_ZIGBEE_BRIDGE_EVENT,
            event.CONF_EVENT_DATA: {
                "subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_ALARM,
                "unique_id": unique_id,
                WZB_LOCK_ALARM_TYPE: config[WZB_LOCK_ALARM_TYPE]
            },
        }
    else:
        raise ValueError(f'the event type is unknown.')

    event_config = event.TRIGGER_SCHEMA(event_config)
    return await event.async_attach_trigger(
        hass, event_config, action, automation_info, platform_type="device"
    )


async def async_get_trigger_capabilities(hass, config):
    """List trigger capabilities."""

    if config[CONF_TYPE] == TRIGGER_TYPE_LOCK_ALARM:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required(
                        WZB_LOCK_ALARM_TYPE,
                        default=WZB_LOCK_ALARM_DOORBELL,
                        description="Select a type of alarm triggered by the lock"
                    ): vol_lock_alarm_type,
                }
            )
        }

    if hass:
        pass
