"""Support for wingto switches."""

from homeassistant.components.switch import (
    DOMAIN as SENSOR_DOMAIN,
    ENTITY_ID_FORMAT,
    SwitchEntity,
)
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import WingtoBaseEntity
from .const import (
    DOMAIN,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up wingto sensors dynamically through wingto discovery."""

    platform = config_entry.data[CONF_PLATFORM]

    async def async_discover_sensor(dev_ids):
        """Discover and add a discovered wingto sensor."""
        if not dev_ids:
            return
        entities = await hass.async_add_executor_job(
            _setup_entities,
            hass,
            config_entry.entry_id,
            dev_ids,
            platform,
        )
        async_add_entities(entities)

    config_entry.async_on_unload(async_dispatcher_connect(
        hass, WINGTO_DISCOVERY_NEW.format(SENSOR_DOMAIN), async_discover_sensor
    ))

    devices_ids = hass.data[DOMAIN][config_entry.entry_id]["pending"].pop(SENSOR_DOMAIN)
    await async_discover_sensor(devices_ids)


def _setup_entities(hass, entry_id, dev_ids, platform):
    """Set up wingto Switch device."""
    wingto = hass.data[DOMAIN][entry_id][WINGTO_API]
    entities = []
    for dev_id in dev_ids:
        device = wingto.get_device_by_id(dev_id)
        if device is None:
            continue
        entities.append(WingtoSwitchEntity(device, platform, entry_id))
    return entities


class WingtoSwitchEntity(WingtoBaseEntity, SwitchEntity):
    """Wingto Switch Entity."""

    def __init__(self, wingto, platform, entry_id):
        """Init wingto switch device."""
        super().__init__(wingto, platform, entry_id)
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._wingto.state()

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self._wingto.turn_on()

    def turn_off(self, **kwargs):
        """Turn the device off."""
        self._wingto.turn_off()
