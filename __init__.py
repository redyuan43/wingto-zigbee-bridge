import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_IP_ADDRESS,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from .const import (
    CONF_DISCOVERY_INTERVAL,
    CONF_QUERY_DEVICE,
    CONF_QUERY_INTERVAL,
    DOMAIN,
    SIGNAL_DELETE_ENTITY,
    SIGNAL_UPDATE_ENTITY,
    WINGTO_API,
    WINGTO_DISCOVERY_NEW,
    WINGTO_PLATFORMS,
    CONF_BROKER_PORT,
    WINGTO_ZIGBEE_BRIDGE_EVENT,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_RECALL_SCENE,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_SENSOR_ALARM,
    WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_ALARM,
    WZB_LOCK_ALARM_TYPE, CONF_GATEWAY_MODEL,
)
from .wingtoha.gateway import WingtoApi

_LOGGER = logging.getLogger(__name__)

ENTRY_IS_SETUP = "wingto_entry_is_setup"

SERVICE_FORCE_UPDATE = "force_update"
SERVICE_PULL_DEVICES = "pull_devices"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up wingto platform."""

    async def async_poll_devices_update():
        """Check if accesstoken is expired and pull device list from server."""
        async with domain_data['add_entity_lock']:
            # Add new discover device.
            device_list = wingto.get_all_devices()
            await async_load_devices(device_list)
            # Delete not exist device.
            newlist_ids = []
            for device in device_list:
                newlist_ids.append(device.object_id())
            for dev_id in list(domain_data["entities"]):
                if dev_id not in newlist_ids:
                    async_dispatcher_send(hass, SIGNAL_DELETE_ENTITY, dev_id)
                    domain_data["entities"].pop(dev_id)

    event_trigger_types_dic = {
        'recall_scene_trigger': lambda unique_id: hass.add_job(
            hass.bus.async_fire,
            WINGTO_ZIGBEE_BRIDGE_EVENT,
            {"subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_RECALL_SCENE,
             "unique_id": unique_id,
             "std_scene_id": 0}),
        'lock_trigger': lambda unique_id, trigger_type: hass.add_job(
            hass.bus.async_fire,
            WINGTO_ZIGBEE_BRIDGE_EVENT,
            {"subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_LOCK_ALARM,
             "unique_id": unique_id,
             WZB_LOCK_ALARM_TYPE: trigger_type}),
        'sensor_alarm_trigger': lambda unique_id: hass.add_job(
            hass.bus.async_fire,
            WINGTO_ZIGBEE_BRIDGE_EVENT,
            {"subtype": WINGTO_ZIGBEE_BRIDGE_EVENT_SUBTYPE_SENSOR_ALARM,
             "unique_id": unique_id})
    }

    wingto = WingtoApi(
        ip=entry.data.get(CONF_IP_ADDRESS),
        port=entry.data.get(CONF_BROKER_PORT),
        update_entities_list=lambda: hass.add_job(async_poll_devices_update),
        add_async_to_mainthread=hass.add_job,
        event_trigger_types=event_trigger_types_dic,
        gateway_type=entry.data.get(CONF_GATEWAY_MODEL),
        gateway_eui64=entry.unique_id,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    domain_data = hass.data[DOMAIN][entry.entry_id] = {
        WINGTO_API: wingto,
        ENTRY_IS_SETUP: set(),
        "entities": {},
        "pending": {},
        "add_entity_lock": asyncio.Lock(),
    }

    async def _ensure_vrv2_climate_setup():
        """Ensure the VRV2-specific climate platform is loaded."""
        config_entries_key = "climate.wingto"
        if config_entries_key not in domain_data[ENTRY_IS_SETUP]:
            _LOGGER.info("VRV2: forcing climate platform setup")
            await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
            domain_data[ENTRY_IS_SETUP].add(config_entries_key)
        else:
            _LOGGER.debug("VRV2: climate platform already initialized")

    async def async_load_devices(device_list):
        """Load new devices by device_list."""
        device_type_list = {}
        for device in device_list:
            if device.object_id() not in domain_data["entities"]:
                ha_type = device.object_type()
                if ha_type not in device_type_list:
                    device_type_list[ha_type] = []
                device_type_list[ha_type].append(device.object_id())
                domain_data["entities"][device.object_id()] = None

        for ha_type, dev_ids in device_type_list.items():
            config_entries_key = f"{ha_type}.wingto"
            if config_entries_key not in domain_data[ENTRY_IS_SETUP]:
                domain_data["pending"][ha_type] = dev_ids
                await hass.config_entries.async_forward_entry_setups(entry, [ha_type])
                domain_data[ENTRY_IS_SETUP].add(config_entries_key)
            else:
                async_dispatcher_send(hass, WINGTO_DISCOVERY_NEW.format(ha_type), dev_ids)

    hass.services.async_register(
        DOMAIN, SERVICE_PULL_DEVICES, async_poll_devices_update
    )

    async def async_force_update(call):
        """Force all devices to pull data."""
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

    hass.services.async_register(DOMAIN, SERVICE_FORCE_UPDATE, async_force_update)

    async def async_refresh_states(call):
        """刷新所有设备状态"""
        await domain_data[WINGTO_API].refresh_all_device_states()

    hass.services.async_register(DOMAIN, "refresh_states", async_refresh_states)

    async def async_discover_gateway(call):
        """自动发现G2网关IP地址"""
        from .wingtoha.network_discovery import network_discovery

        known_ip = call.data.get("known_ip")
        _LOGGER.info("Starting G2 gateway discovery...")

        result = await network_discovery.find_g2_gateway(known_ip)
        if result:
            ip, auth_info = result
            _LOGGER.info("G2 gateway found: %s (auth: %s)", ip, auth_info)
            hass.components.persistent_notification.create(
                f"找到G2网关: {ip}\n认证方式: {auth_info}\n\n请在集成配置中使用此IP地址。",
                title="G2网关发现结果",
                notification_id="g2_gateway_discovery",
            )
        else:
            _LOGGER.warning("No G2 gateway found")
            hass.components.persistent_notification.create(
                "未找到G2网关，请检查：\n1. 网关是否开机\n2. 网络连接是否正常\n3. 是否在同一网段",
                title="G2网关发现失败",
                notification_id="g2_gateway_discovery",
            )

    hass.services.async_register(DOMAIN, "discover_gateway", async_discover_gateway)

    async def async_create_vrv2_devices(call):
        """手动创建VRV2空调设备"""
        device_macs = call.data.get("device_macs", [])
        if device_macs:
            await domain_data[WINGTO_API].create_vrv2_devices(device_macs)
            _LOGGER.info("VRV2: created devices via service: %s", device_macs)
        else:
            _LOGGER.warning("VRV2: no device MACs provided for creation request")

    hass.services.async_register(DOMAIN, "create_vrv2_devices", async_create_vrv2_devices)

    async def _add_entities_after_reboot():
        """"
        If this function is called just when the very first time after
        the integration added, then the list original_names will get an empty one
        """

        registry = entity_registry.async_get(hass)
        original_names = [
            v.original_name
            for v in entity_registry.async_entries_for_config_entry(
                registry, entry.entry_id
            )
            if v.original_name
        ]

        # 等待MQTT连接建立
        await domain_data[WINGTO_API].wait_for_mqtt_ready()

        # 重新创建设备（如有需要）
        if original_names:
            await domain_data[WINGTO_API].create_device_by_entity(original_names)
        else:
            _LOGGER.debug("No existing entities found for recreation after reboot")

        # 延迟一段时间后强制刷新所有设备状态
        await asyncio.sleep(5)
        await domain_data[WINGTO_API].refresh_all_device_states()

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED,
        lambda *_: hass.add_job(_add_entities_after_reboot)
    )

    # VRV2 专用气候平台需要手动触发加载，保证空调实体可用
    await _ensure_vrv2_climate_setup()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unloading the Wingto platforms."""
    domain_data = hass.data[DOMAIN][entry.entry_id]
    platforms = [platform.split(".", 1)[0] for platform in domain_data[ENTRY_IS_SETUP]]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        await domain_data[WINGTO_API].remove_api()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
            hass.services.async_remove(DOMAIN, SERVICE_PULL_DEVICES)
            hass.services.async_remove(DOMAIN, "refresh_states")
            hass.data.pop(DOMAIN)

    return unload_ok


async def cleanup_device_registry(hass: HomeAssistant, device_id):
    """Remove device registry entry if there are no remaining entities."""

    device_reg = device_registry.async_get(hass)
    entity_reg = entity_registry.async_get(hass)
    if device_id and not entity_registry.async_entries_for_device(
            entity_reg, device_id, include_disabled_entities=True
    ):
        device_reg.async_remove_device(device_id)


class WingtoBaseEntity(Entity):
    """Wingto base device."""

    _dev_can_query_count = 0

    def __init__(self, wingto, platform, entry_id, device_id=None):
        self._wingto = wingto
        self._wingto_platform = platform
        self._wingto.update_entity_state = lambda: self.hass and self.hass.add_job(
            self.async_schedule_update_ha_state, True)
        self._entry_id = entry_id
        self._device_id = device_id

    @property
    def device_obj(self):
        return self._wingto

    @property
    def eui64(self):
        return self._wingto.get_eui64()

    @property
    def endpoint(self):
        return self._wingto.get_endpoint()

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        self.hass.data[DOMAIN][self._entry_id]["entities"][self.object_id] = self.entity_id
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_DELETE_ENTITY, self._delete_callback
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE_ENTITY, self._update_callback
            )
        )

    async def async_will_remove_from_hass(self):
        """Call when entity is removed from hass."""
        pass

    @property
    def object_id(self):
        # 于 entity，这是 entity_id，支持通过 UI 修改
        return self._wingto.object_id()

    @property
    def unique_id(self):
        """Return a unique ID."""
        # 不支持通过 UI 修改
        return self._wingto.object_id()

    @property
    def name(self):
        return self._wingto.name()

    @property
    def available(self):
        """Return if the device is available."""
        return self._wingto.available()

    @property
    def device_info(self):
        """Return a device description for device registry."""
        _device_info = {
            # 如果今后有将 entities 合并为 device 的需求
            # 这里要注意，不能修改 unique_id
            # 因为内在逻辑已经限定，unique_id 一定是作为一个 endpoint 的区分来使用的
            "identifiers": {(DOMAIN, f"{self._device_id if self._device_id else self.unique_id}")},
            "manufacturer": WINGTO_PLATFORMS.get(
                self._wingto_platform, self._wingto_platform
            ),
            "name": self.name,
            "model": self._wingto.object_type(),
        }
        return _device_info

    async def _delete_callback(self, dev_id):
        """Remove this entity."""
        if dev_id == self.object_id:
            entity_reg = entity_registry.async_get(self.hass)
            if entity_reg.async_is_registered(self.entity_id):
                entity_entry = entity_reg.async_get(self.entity_id)
                entity_reg.async_remove(self.entity_id)
                await cleanup_device_registry(self.hass, entity_entry.device_id)
            else:
                await self.async_remove(force_remove=True)

    @callback
    def _update_callback(self):
        """Call update method."""
        self.async_schedule_update_ha_state(True)
