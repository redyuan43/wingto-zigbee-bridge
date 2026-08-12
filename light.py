import asyncio
from datetime import timedelta

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    COLOR_MODE_XY,
    ATTR_HS_COLOR,
    DOMAIN as SENSOR_DOMAIN,
    ENTITY_ID_FORMAT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    LightEntity, COLOR_MODE_HS,
)
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import color as colorutil

from . import WingtoBaseEntity
from .const import (
    DOMAIN,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW,
)
import logging

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=15)


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
    """Set up Wingto Light device."""
    wingto = hass.data[DOMAIN][entry_id][WINGTO_API]
    entities = []
    for dev_id in dev_ids:
        device = wingto.get_device_by_id(dev_id)
        if device is None:
            continue
        entities.append(WingtoLight(device, platform, entry_id))
        _LOGGER.info("add_light_entitity=%s", dev_id)
    return entities


class WingtoLight(WingtoBaseEntity, LightEntity):
    """Wingto light device."""

    def __init__(self, wingto, platform, entry_id):
        """Init Wingto light device."""
        super().__init__(wingto, platform, entry_id)
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())
        self._min_kelvin = wingto.max_color_temp
        self._max_kelvin = wingto.min_color_temp

    async def async_added_to_hass(self):
        """Set config parameter when add to hass."""
        await super().async_added_to_hass()
        return

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def brightness(self):
        """Return the brightness of the light."""
        val = self._wingto.brightness()
        if val is None:
            return
        return int(val)

    @property
    def xy_color(self):
        """Return the xy_color of the light."""
        return tuple(self._wingto.xy_color())

    @property
    def hs_color(self):
        """Return the hs_color of the light."""
        return tuple(self._wingto.hs_color())

    @property
    def color_mode(self):
        if self._wingto.support_color_type_hs():
            return COLOR_MODE_HS
        else:
            return COLOR_MODE_XY

    @property
    def color_temp(self):
        """Return the color_temp of the light."""
        val = self._wingto.color_temp
        if val is None:
            return
        return int(val)

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._wingto.state()

    @property
    def min_mireds(self):
        """Return color temperature min mireds."""
        return colorutil.color_temperature_kelvin_to_mired(self._max_kelvin)

    @property
    def max_mireds(self):
        """Return color temperature max mireds."""
        return colorutil.color_temperature_kelvin_to_mired(self._min_kelvin)

    def turn_on(self, **kwargs):
        """Turn on or control the light."""
        if (
                ATTR_BRIGHTNESS not in kwargs
                and ATTR_HS_COLOR not in kwargs
                and ATTR_COLOR_TEMP not in kwargs
        ):
            self._wingto.turn_on()
        if ATTR_BRIGHTNESS in kwargs:
            self._wingto.set_brightness(kwargs[ATTR_BRIGHTNESS])
        if ATTR_HS_COLOR in kwargs:
            if self.color_mode == COLOR_MODE_XY:
                x, y = colorutil.color_hs_to_xy(*kwargs[ATTR_HS_COLOR])
                self._wingto.set_color_xy(x, y)
            else:
                h, s = kwargs[ATTR_HS_COLOR]
                self._wingto.set_color_hs(h * 254 / 360, s * 254 / 100)
        if ATTR_COLOR_TEMP in kwargs:
            self._wingto.set_color_temp(kwargs[ATTR_COLOR_TEMP])

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        self._wingto.turn_off()

    @property
    def supported_features(self):
        """Flag supported features."""
        supports = SUPPORT_BRIGHTNESS
        if self._wingto.support_color():
            supports = supports | SUPPORT_COLOR
        if self._wingto.support_color_temp():
            supports = supports | SUPPORT_COLOR_TEMP
        return supports
