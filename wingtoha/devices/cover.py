import logging
from .base import WingtoDevice

_LOGGER = logging.getLogger(__name__)


class WingtoCover(WingtoDevice):

    def __init__(self, data, api):
        super().__init__(data, api)
        self.update_state(3)
        _LOGGER.info("Initialized cover device: %s", self.object_id())

    def open_cover(self):
        """Open the cover."""
        _LOGGER.info("Opening cover: %s", self.object_id())
        if self._control_device("window-covering-up", None):
            self.update_state(1)
            _LOGGER.info("Cover open command sent successfully: %s", self.object_id())
        else:
            _LOGGER.warning("Failed to send cover open command: %s", self.object_id())

    def close_cover(self):
        """Close cover."""
        _LOGGER.info("Closing cover: %s", self.object_id())
        if self._control_device("window-covering-down", None):
            self.update_state(2)
            _LOGGER.info("Cover close command sent successfully: %s", self.object_id())
        else:
            _LOGGER.warning("Failed to send cover close command: %s", self.object_id())

    def stop_cover(self):
        """Stop the cover."""
        _LOGGER.info("Stopping cover: %s", self.object_id())
        if self._control_device("window-covering-stop", None):
            self.update_state(3)
            _LOGGER.info("Cover stop command sent successfully: %s", self.object_id())
        else:
            _LOGGER.warning("Failed to send cover stop command: %s", self.object_id())

    def set_cover_position(self, kwargs):
        """Set cover position."""
        position = kwargs.get('position', 0)
        _LOGGER.info("Setting cover position to %d%% for device: %s", position, self.object_id())
        if self._control_device("window-covering-percent", {"position": position}):
            # 设置中间状态，等待实际位置反馈
            self.update_state(4)
            _LOGGER.info("Cover position command sent successfully: %s", self.object_id())
        else:
            _LOGGER.warning("Failed to send cover position command: %s", self.object_id())

    def get_cover_position(self):
        """Get current cover position."""
        try:
            position = self._attrs[258][8]
            _LOGGER.debug("Current cover position for %s: %d", self.object_id(), position)
            return position
        except (KeyError, TypeError) as e:
            _LOGGER.warning("Failed to get cover position for %s: %s", self.object_id(), e)
            return 0

    async def startup_init(self):
        """Initialize cover state."""
        _LOGGER.info("Initializing cover state for: %s", self.object_id())
        self._control_device("local_read_cover_pos")

    async def refresh_state(self):
        """刷新设备状态"""
        _LOGGER.info("Refreshing cover state for: %s", self.object_id())
        self._control_device("local_read_cover_pos")
