from homeassistant.components.siren import (
    DOMAIN as SENSOR_DOMAIN,
    SirenEntity,
)
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import WingtoBaseEntity
from .const import (
    DOMAIN,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW,
)
from homeassistant.components.siren.const import (
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_DURATION, SUPPORT_TONES, SUPPORT_VOLUME_SET)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"


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
    wingto = hass.data[DOMAIN][entry_id][WINGTO_API]
    entities = []
    for dev_id in dev_ids:
        device = wingto.get_device_by_id(dev_id)
        if device is None:
            continue
        entities.append(WingtoSirenEntity(device, platform, entry_id))
    return entities


class WingtoSirenEntity(WingtoBaseEntity, SirenEntity):

    def __init__(self, wingto, platform, entry_id):
        super().__init__(wingto, platform, entry_id)
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())
        self._attr_supported_features = \
            SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_DURATION | SUPPORT_TONES | SUPPORT_VOLUME_SET

    @property
    def is_on(self) -> bool:
        """Return true if siren is on."""
        return self._wingto.state()

    def turn_on(self, **kwargs) -> None:
        """Turn the siren on."""
        self._wingto.turn_on(kwargs)

    def turn_off(self, **kwargs) -> None:
        """Turn the siren off."""
        self._wingto.turn_off()

    @property
    def available_tones(self):
        return [1, 2, 3, 4, 5, 6]
