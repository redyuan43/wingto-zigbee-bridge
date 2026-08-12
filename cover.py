from homeassistant.components.cover import (
    DOMAIN as SENSOR_DOMAIN,
    ENTITY_ID_FORMAT,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import WingtoBaseEntity
from .const import DOMAIN, WINGTO_API, WINGTO_DISCOVERY_NEW


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
        entities.append(WingtoCover(device, platform, entry_id))
    return entities


class WingtoCover(WingtoBaseEntity, CoverEntity):

    def __init__(self, wingto, platform, entry_id):
        super().__init__(wingto, platform, entry_id)
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())

    @property
    def should_poll(self) -> bool:
        return True

    @property
    def supported_features(self):
        """Flag supported features."""
        return (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP |
            CoverEntityFeature.SET_POSITION
        )

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        return self._wingto.state() == 1

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        return self._wingto.state() == 2

    @property
    def is_closed(self):
        """Return if the cover is closed or not."""
        position = self.current_cover_position
        if position is not None:
            return position == 0
        return None

    def open_cover(self, **kwargs):
        """Open the cover."""
        self._wingto.open_cover()

    def close_cover(self, **kwargs):
        """Close cover."""
        self._wingto.close_cover()

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        self._wingto.stop_cover()

    def set_cover_position(self, **kwargs):
        """Set cover position."""
        position = kwargs.get('position', 0)
        self._wingto.set_cover_position({'position': position})

    @property
    def current_cover_position(self):
        """Return current position of cover."""
        position = self._wingto.get_cover_position()
        # 确保返回值在 0-100 范围内
        if position is not None:
            return max(0, min(100, position))
        return None
