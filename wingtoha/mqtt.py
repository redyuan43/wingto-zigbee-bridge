from __future__ import annotations

import asyncio
import logging
import uuid

import paho.mqtt.client as mqtt

from .models import PublishPayloadType

_LOGGER = logging.getLogger(__name__)

TOPICS = {r"gw/+/wingto_zclresponse",
          r"gw/+/apsresponse",
          r"gw/+/heartbeat",
          r"$gw/child/#",
          r"$ricisung"}
QOS = 0


class MqttError(Exception):
    """General MQTT exception occurred."""


class MQTT:
    """ MQTT client."""

    def __init__(self, ip_address, broker_port, add_job, message_callback) -> None:

        self.connected = False

        self._ip_address = ip_address
        self._broker_port = int(broker_port)
        self._add_job = add_job
        self._handle_message_callback = message_callback

        self._mqttc: mqtt.Client | None = None
        self._paho_lock = asyncio.Lock()
        self._message_listeners = set()

        self._init_client()

    def _init_client(self):
        """Initialize paho client."""

        self._mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, str(uuid.uuid1()))

        # Enable logging
        self._mqttc.enable_logger()

        self._mqttc.on_connect = self._mqtt_on_connect
        self._mqttc.on_disconnect = self._mqtt_on_disconnect
        self._mqttc.on_message = self._mqtt_on_message

    def publish(self, topic: str, payload: PublishPayloadType):
        self._add_job(self.async_publish, topic, payload, 0, False)

    def add_message_listener(self, listener):
        """Register a lightweight listener for raw MQTT messages."""
        self._message_listeners.add(listener)

        def remove_listener():
            self._message_listeners.discard(listener)

        return remove_listener

    async def async_publish(
            self, topic: str, payload: PublishPayloadType, qos: int, retain: bool
    ) -> bool:
        """Publish a MQTT message and return whether the broker accepted it."""
        return await self.async_publish_confirm(topic, payload, qos, retain)

    async def async_publish_confirm(
            self,
            topic: str,
            payload: PublishPayloadType,
            qos: int = 0,
            retain: bool = False,
            timeout: float = 5.0,
    ) -> bool:
        """Publish through the long-lived client and wait for completion."""
        if not self.connected:
            _LOGGER.error(
                "Cannot publish to %s because MQTT is disconnected from %s:%d.",
                topic,
                self._ip_address,
                self._broker_port,
            )
            return False

        async with self._paho_lock:
            try:
                msg_info = await asyncio.get_running_loop().run_in_executor(
                    None,
                    self._mqttc.publish,
                    topic,
                    payload,
                    qos,
                    retain,
                )
                _raise_on_error(msg_info.rc)
                published = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: (msg_info.wait_for_publish(timeout), msg_info.is_published())[1],
                )
            except (MqttError, RuntimeError, ValueError) as err:
                _LOGGER.error(
                    "Failed to transmit message on %s through %s:%d: %s",
                    topic,
                    self._ip_address,
                    self._broker_port,
                    err,
                )
                return False

            if not published:
                _LOGGER.error(
                    "Timed out publishing message on %s through %s:%d.",
                    topic,
                    self._ip_address,
                    self._broker_port,
                )
                return False

            _LOGGER.debug("Published message on %s (mid=%s).", topic, msg_info.mid)
            return True

    async def async_connect(self) -> None:
        """Start a reconnecting MQTT connection."""

        def connect() -> None:
            self._mqttc.reconnect_delay_set(min_delay=1, max_delay=30)
            self._mqttc.connect_async(self._ip_address, self._broker_port)
            self._mqttc.loop_start()

        await asyncio.get_running_loop().run_in_executor(None, connect)

    async def async_disconnect(self):
        """Stop the MQTT client."""

        def stop():
            """Stop the MQTT client."""
            # Do not disconnect, we want the broker to always publish will
            self._mqttc.loop_stop()

        await asyncio.get_event_loop().run_in_executor(None, stop)

    def _mqtt_on_connect(self, _mqttc, _userdata, _flags, result_code: int) -> None:
        """On connect callback.

        Resubscribe to all topics we were subscribed to and publish birth
        message.
        """

        if result_code != mqtt.CONNACK_ACCEPTED:
            _LOGGER.error(
                "Unable to connect to the MQTT broker: %s",
                mqtt.connack_string(result_code),
            )
            return

        self.connected = True
        _LOGGER.info(
            "Connected to MQTT server %s:%s (%s)",
            self._ip_address,
            self._broker_port,
            result_code,
        )

        for t in TOPICS:
            self._add_job(self._async_perform_subscription, t, QOS)

    def _mqtt_on_message(self, _mqttc, _userdata, msg) -> None:
        """Message received callback."""

        # self._add_job(self._mqtt_handle_message, msg)
        self._mqtt_handle_message(msg)

    def _mqtt_on_disconnect(self, _mqttc, _userdata, result_code: int) -> None:
        """Disconnected callback."""
        self.connected = False
        _LOGGER.warning(
            "Disconnected from MQTT server %s:%s (%s)",
            self._ip_address,
            self._broker_port,
            result_code,
        )

    async def _async_perform_subscription(self, topic: str, qos: int) -> None:
        """Perform a paho-mqtt subscription."""
        async with self._paho_lock:
            result, mid = await asyncio.get_event_loop().run_in_executor(
                None,
                self._mqttc.subscribe, topic, qos
            )
            _LOGGER.debug("Subscribing to %s, mid: %s", topic, mid)
            _raise_on_error(result)

    def _mqtt_handle_message(self, msg) -> None:
        _LOGGER.debug(
            "Received message on %s%s: %s",
            msg.topic,
            " (retained)" if msg.retain else "",
            msg.payload[0:8192],
        )
        try:
            payload = msg.payload.decode("utf-8")
            self._handle_message_callback(msg.topic, payload, QOS)
            for listener in tuple(self._message_listeners):
                try:
                    listener(msg.topic, payload, QOS)
                except Exception:
                    _LOGGER.exception("MQTT message listener failed for %s", msg.topic)
        except UnicodeDecodeError:
            _LOGGER.error(
                "Received message on %s%s: %s",
                msg.topic,
                " (retained)" if msg.retain else "",
                msg.payload[0:8192],
            )

    # async def async_subscribe(
    #         self,
    #         topic: str,
    #         qos: int,
    #         encoding: str | None = None,
    # ) -> Callable[[], None]:
    #     """Set up a subscription to a topic with the provided qos.
    #
    #     This method is a coroutine.
    #     """
    #     if not isinstance(topic, str):
    #         raise
    #
    #         # Only subscribe if currently connected.
    #     if self.connected:
    #         await self._async_perform_subscription(topic, qos)


def _raise_on_error(result_code: int | None) -> None:
    """Raise error if error result."""

    if result_code is not None and result_code != 0:
        raise MqttError()
