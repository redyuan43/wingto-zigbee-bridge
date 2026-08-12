import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, ENTITY_ID_FORMAT
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import WingtoBaseEntity
from .const import (
    DOMAIN,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW
)


async def set_reportable_change_of_illuminance(entity, service_call):
    if hasattr(entity.device_obj, 'set_reportable_change_of_illuminance'):
        entity.device_obj.set_reportable_change_of_illuminance(service_call.data['reportable_change_of_illuminance'])


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up wingto sensors dynamically through wingto discovery."""

    platform = config_entry.data[CONF_PLATFORM]

    platform_obj = entity_platform.async_get_current_platform()
    platform_obj.async_register_entity_service(
        "set_reportable_change_of_illuminance",
        {
            vol.Required('reportable_change_of_illuminance'):
                vol.All(vol.Coerce(int), vol.Range(min=10, max=100))
        },
        set_reportable_change_of_illuminance
    )

    async def async_discover_sensor(dev_ids):
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
        entities.append(WingtoSensorEntity(device, platform, entry_id))
    return entities


class WingtoSensorEntity(WingtoBaseEntity, SensorEntity):

    def __init__(self, wingto, platform, entry_id):
        super().__init__(wingto, platform, entry_id, wingto.get_eui64())
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())
        self.count = 0

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._wingto.support_event

    @property
    def native_unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._wingto.get_unit()

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def native_value(self):
        """Return the value reported by the sensor."""
        return self._wingto.get_func()

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self._wingto.get_device_class()

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes.
        """
        attr = {}
        if hasattr(self._wingto, 'get_radar_attribution'):
            _, _, val3 = self._wingto.get_radar_attribution()
            if val3:
                attr.update({'reportable_change_of_illuminance': val3})
            return attr
