"""Platform to locally control Wingto climate devices."""
import asyncio
import logging
import json
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)

from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)

from .const import DOMAIN, WINGTO_API
from .vrv2_config import (
    VRV2_GATEWAY_CONFIG,
    VRV2_DEVICE_CONFIG,
    VRV2_ROOM_CONFIG,
    VRV2_ENTITY_CONFIG,
    VRV2_SUPPORTED_MODES,
    VRV2_COMMAND_CONFIG,
    get_room_name,
    get_mqtt_topic,
    build_power_command,
    build_temperature_command,
    build_fan_command,
    build_mqtt_message,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up wingto climate devices - 完全简化版本，直接创建VRV2实体"""
    # Prefer the configured G2 entry so DHCP/IP changes do not strand VRV2 commands.
    gateway_ip = config_entry.data.get("ip_address", "")
    gateway_model = str(config_entry.data.get("gateway_model", "")).upper()
    if gateway_model != "G2" and gateway_ip != VRV2_GATEWAY_CONFIG["ip"]:
        _LOGGER.debug("VRV2: Skipping VRV2 setup for gateway %s (model=%s)", gateway_ip, gateway_model)
        return
    if gateway_ip:
        VRV2_GATEWAY_CONFIG["ip"] = gateway_ip
    if config_entry.unique_id:
        VRV2_GATEWAY_CONFIG["eui64"] = str(config_entry.unique_id).upper()

    _LOGGER.info("VRV2: Starting climate platform setup for VRV2 gateway %s...", gateway_ip)

    # 直接创建VRV2实体，不依赖任何设备发现
    vrv2_entities = []

    try:
        for control_sn in VRV2_ROOM_CONFIG.keys():
            room_name = get_room_name(control_sn)
            entity = VRV2ClimateEntity(control_sn, room_name, config_entry.entry_id, hass)
            vrv2_entities.append(entity)
            _LOGGER.info("VRV2: Created entity for %s (Room %d)", room_name, control_sn)

        if vrv2_entities:
            async_add_entities(vrv2_entities, update_before_add=False)
            _LOGGER.info("VRV2: Successfully added %d entities", len(vrv2_entities))

        else:
            _LOGGER.error("VRV2: No entities created!")

    except Exception as e:
        _LOGGER.error("VRV2: Entity creation failed: %s", e)
        import traceback
        _LOGGER.error("VRV2: %s", traceback.format_exc())


class VRV2ClimateEntity(ClimateEntity):
    """VRV2空调实体 - 独立实现，不依赖wingto设备对象"""

    def __init__(self, control_sn, room_name, entry_id, hass):
        """初始化VRV2实体"""
        self._control_sn = control_sn
        self._room_name = room_name
        self._entry_id = entry_id
        self.hass = hass

        # 设备配置
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = VRV2_SUPPORTED_MODES["hvac_modes"]
        self._attr_fan_modes = VRV2_SUPPORTED_MODES["fan_modes"]
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE
        )
        if hasattr(ClimateEntityFeature, "TURN_ON"):
            features |= ClimateEntityFeature.TURN_ON
        if hasattr(ClimateEntityFeature, "TURN_OFF"):
            features |= ClimateEntityFeature.TURN_OFF
        self._attr_supported_features = features
        self._attr_min_temp = VRV2_COMMAND_CONFIG["temperature"]["min_temp"]
        self._attr_max_temp = VRV2_COMMAND_CONFIG["temperature"]["max_temp"]

        # 状态变量
        self._is_on = False
        self._target_temp = 25
        self._current_temp = None
        self._hvac_mode = HVACMode.OFF
        self._fan_mode = "auto"
        self._last_command = None
        self._last_command_error = None
        self._command_lock = asyncio.Lock()
        self._mqtt_listener_remove = None

        _LOGGER.debug("VRV2: Initialized %s (control_sn=%d)", room_name, control_sn)

    @property
    def unique_id(self):
        """Return unique ID."""
        return VRV2_ENTITY_CONFIG["unique_id_template"].format(control_sn=self._control_sn)

    @property
    def name(self):
        """Return name."""
        return VRV2_ENTITY_CONFIG["name_template"].format(room_name=self._room_name)

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, f"vrv2_{self._control_sn}")},
            "name": VRV2_ENTITY_CONFIG["device_name_template"].format(room_name=self._room_name),
            "manufacturer": VRV2_ENTITY_CONFIG["manufacturer"],
            "model": VRV2_ENTITY_CONFIG["model"],
        }

    @property
    def should_poll(self):
        """Return if entity should be polled."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        gateway = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(WINGTO_API)
        return bool(gateway and gateway.mqtt.connected)

    @property
    def extra_state_attributes(self):
        """Expose command diagnostics without pretending to parse device state."""
        return {
            "last_command": self._last_command,
            "last_command_error": self._last_command_error,
        }

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_temp

    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._target_temp

    @property
    def hvac_mode(self):
        """Return hvac mode."""
        return self._hvac_mode

    @property
    def fan_mode(self):
        """Return fan mode."""
        return self._fan_mode

    async def async_added_to_hass(self):
        """Subscribe to the controller's periodic status reports."""
        await super().async_added_to_hass()
        gateway = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(WINGTO_API)
        if gateway is not None:
            self._mqtt_listener_remove = gateway.mqtt.add_message_listener(
                self._handle_mqtt_state
            )

    async def async_will_remove_from_hass(self):
        """Remove the raw MQTT listener when this entity unloads."""
        if self._mqtt_listener_remove is not None:
            self._mqtt_listener_remove()
            self._mqtt_listener_remove = None
        await super().async_will_remove_from_hass()

    def _handle_mqtt_state(self, topic, payload, _qos):
        """Decode the HH01_64 status reports from the G2 MQTT thread."""
        if not topic.endswith("/wingto_zclresponse"):
            return
        try:
            message = json.loads(payload)
            endpoint = message.get("deviceEndpoint", {})
            if (
                endpoint.get("eui64", "").upper() != VRV2_DEVICE_CONFIG["device_mac"].upper()
                or message.get("clusterId") != "0xFF00"
                or message.get("commandId") != "0x0A"
            ):
                return
            power_mask, temperature = self._parse_status_report(message["payload"])
        except (KeyError, ValueError, json.JSONDecodeError):
            return

        if power_mask is not None or temperature is not None:
            self.hass.loop.call_soon_threadsafe(
                self._apply_status_report, power_mask, temperature
            )

    def _parse_status_report(self, payload):
        """Extract the room power bitmap and target temperatures from ZCL reports."""
        frame = bytes.fromhex(payload)
        if len(frame) < 5 or frame[4] != 0x0A:
            return None, None

        power_mask = None
        temperature = None
        position = 5
        while position + 3 <= len(frame):
            attribute_id = int.from_bytes(frame[position:position + 2], "little")
            data_type = frame[position + 2]
            position += 3

            if data_type == 0x27:
                if position + 8 > len(frame):
                    break
                value = int.from_bytes(frame[position:position + 8], "little")
                position += 8
                if attribute_id == 0x0011:
                    power_mask = value
            elif data_type == 0x42:
                if position >= len(frame):
                    break
                length = frame[position]
                position += 1
                if position + length > len(frame):
                    break
                value = frame[position:position + length].decode("ascii")
                position += length
                if attribute_id in (0x0016, 0x0018):
                    offset = (self._control_sn - 1) * 2
                    if len(value) >= offset + 2:
                        candidate = int(value[offset:offset + 2], 16)
                        if self._attr_min_temp <= candidate <= self._attr_max_temp:
                            temperature = candidate
            else:
                break

        return power_mask, temperature

    def _apply_status_report(self, power_mask, temperature):
        """Apply a parsed controller report on Home Assistant's event loop."""
        changed = False
        if power_mask is not None:
            is_on = bool(power_mask & (1 << (self._control_sn - 1)))
            if is_on != self._is_on:
                self._is_on = is_on
                self._hvac_mode = HVACMode.COOL if is_on else HVACMode.OFF
                changed = True

        if temperature is not None and temperature != self._target_temp:
            self._target_temp = temperature
            changed = True

        if changed:
            self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set temperature."""
        if ATTR_TEMPERATURE in kwargs:
            temp = int(kwargs[ATTR_TEMPERATURE])
            min_temp = VRV2_COMMAND_CONFIG["temperature"]["min_temp"]
            max_temp = VRV2_COMMAND_CONFIG["temperature"]["max_temp"]
            if min_temp <= temp <= max_temp:
                if await self._send_temperature_command(temp):
                    self._target_temp = temp
                    self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            if await self._send_power_command(False):
                self._hvac_mode = HVACMode.OFF
                self._is_on = False
                self.async_write_ha_state()
        else:
            if await self._send_power_command(True):
                self._hvac_mode = hvac_mode
                self._is_on = True
                self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        if await self._send_fan_command(fan_mode):
            self._fan_mode = fan_mode
            self.async_write_ha_state()

    async def async_turn_on(self):
        """Turn on."""
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self):
        """Turn off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _send_power_command(self, turn_on):
        """发送电源控制命令"""
        action = "turn_on" if turn_on else "turn_off"
        return await self._send_mqtt_command(
            build_power_command(self._control_sn, turn_on), action
        )

    async def _send_temperature_command(self, temperature):
        """发送温度控制命令"""
        return await self._send_mqtt_command(
            build_temperature_command(self._control_sn, temperature),
            f"set_temp_{temperature}",
        )

    async def _send_fan_command(self, fan_mode):
        """发送风量控制命令"""
        return await self._send_mqtt_command(
            build_fan_command(self._control_sn, fan_mode),
            f"set_fan_{fan_mode}",
        )

    async def _send_mqtt_command(self, zclbuf, action):
        """Send a VRV command and require the controller's Zigbee ACK."""
        message = build_mqtt_message(self._control_sn, zclbuf)
        topic = get_mqtt_topic()
        message_json = json.dumps(message)

        gateway = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get(WINGTO_API)
        if gateway is None:
            self._last_command_error = "G2 gateway integration is unavailable"
            _LOGGER.error("VRV2 %s: %s failed: %s", self._room_name, action, self._last_command_error)
            return False

        ack_event = asyncio.Event()

        def _handle_ack(ack_topic, payload, _qos):
            if not ack_topic.endswith("/apsresponse"):
                return
            try:
                response = json.loads(payload)
            except json.JSONDecodeError:
                return
            if (
                response.get("statusType") == "apsAck"
                and response.get("status") == "0x00"
                and response.get("eui64", "").upper() == VRV2_DEVICE_CONFIG["device_mac"].upper()
                and response.get("msg", "").upper().endswith(zclbuf.upper())
            ):
                self.hass.loop.call_soon_threadsafe(ack_event.set)

        async with self._command_lock:
            remove_listener = gateway.mqtt.add_message_listener(_handle_ack)
            try:
                if not await gateway.mqtt.async_publish_confirm(topic, message_json):
                    self._last_command_error = "MQTT broker did not accept the command"
                    _LOGGER.error(
                        "VRV2 %s: %s failed: %s",
                        self._room_name,
                        action,
                        self._last_command_error,
                    )
                    return False

                try:
                    await asyncio.wait_for(ack_event.wait(), timeout=6)
                except asyncio.TimeoutError:
                    self._last_command_error = "No Zigbee ACK from the VRV controller"
                    _LOGGER.error(
                        "VRV2 %s: %s failed: %s",
                        self._room_name,
                        action,
                        self._last_command_error,
                    )
                    return False
            finally:
                remove_listener()

        self._last_command = action
        self._last_command_error = None
        _LOGGER.info("VRV2 %s: %s confirmed by controller", self._room_name, action)
        return True
