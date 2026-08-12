"""Support for wingto lock."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.lock import (
    DOMAIN as SENSOR_DOMAIN,
    ENTITY_ID_FORMAT,
    LockEntity,
)
from homeassistant.const import CONF_PLATFORM
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import WingtoBaseEntity
from .const import (
    DOMAIN,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW,
)


async def lock_set_auto_lock_time(entity, service_call):
    if hasattr(entity.device_obj, 'lock_set_auto_lock_time'):
        await entity.device_obj.lock_set_auto_lock_time(service_call.data['timeout'])


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up wingto sensors dynamically through wingto discovery."""

    platform = config_entry.data[CONF_PLATFORM]

    platform_obj = entity_platform.async_get_current_platform()
    platform_obj.async_register_entity_service(
        "set_timeout_to_lock_automatically",
        {
            vol.Required('timeout'):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=255))
        },
        lock_set_auto_lock_time
    )

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
    """Set up wingto lock device."""
    wingto = hass.data[DOMAIN][entry_id][WINGTO_API]
    entities = []
    for dev_id in dev_ids:
        device = wingto.get_device_by_id(dev_id)
        if device is None:
            continue
        entities.append(WingtoLockEntity(device, platform, entry_id))
    return entities


class WingtoLockEntity(WingtoBaseEntity, LockEntity):
    """Wingto lock Entity."""

    def __init__(self, wingto, platform, entry_id):
        """Init wingto switch device."""
        super().__init__(wingto, platform, entry_id, wingto.get_eui64())
        self.entity_id = ENTITY_ID_FORMAT.format(wingto.object_id())

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes.
        """
        attr = {}
        val = self._wingto.get_timeout_of_auto_lock()
        if val is not None:
            attr.update({'timeout_to_lock': val})
        val = self._wingto.get_lock_last_result()
        if val is not None:
            attr.update({'result_of_last_operation': val})
        val = self._wingto.get_lock_state()
        if val is not None:
            attr.update({'status': val})
        return attr

    @property
    def changed_by(self):
        """Last change triggered by."""
        return self._wingto.get_lock_changed_by()

    @property
    def code_format(self):
        # re.compile(r'[0-9]{4,8}$')
        return "^\\d{8}$"

    @property
    def is_locked(self):
        """Return true if the lock is locked."""
        if self._wingto.get_lock_state() in ('关锁',):
            return True
        return False

    @property
    def is_locking(self):
        """Return true if the lock is locking."""
        if self._wingto.get_lock_state() in ('正在开锁',):
            return True
        return False

    @property
    def is_unlocking(self):
        """Return true if the lock is unlocking."""
        return False

    @property
    def is_jammed(self):
        """Return true if the lock is jammed (incomplete locking)."""
        if self._wingto.get_lock_state() in ('死闩损坏',):
            return True
        return False

    async def async_lock(self, **kwargs):
        """Lock the lock."""
        return

    async def async_unlock(self, **kwargs):
        """unLock the lock."""
        self.hass.add_job(self._wingto.unlock, kwargs)
        # await self._wingto.unlock(kwargs)
