from .base import WingtoDevice
from ..const import GATEWAY_MODE_DEFAULT


class WingtoSwitch(WingtoDevice):

    def turn_on(self):
        if self._device_mode == GATEWAY_MODE_DEFAULT:
            self._control_device("adb_ctr_on")
            self.update_state(True)
        else:
            self._control_device("turnOnOff", {"value": "1"})
            attrs = [
                (self.get_eui64(), self.get_endpoint(), 6, 0, 1, None, None),
            ]
            self.api._add_async_to_mainthread(self.api._create_or_update_device_in_cor, attrs)

    def turn_off(self):
        if self._device_mode == GATEWAY_MODE_DEFAULT:
            self._control_device("adb_ctr_off")
            self.update_state(False)
        else:
            self._control_device("turnOnOff", {"value": "0"})
            attrs = [
                (self.get_eui64(), self.get_endpoint(), 6, 0, 0, None, None),
            ]
            self.api._add_async_to_mainthread(self.api._create_or_update_device_in_cor, attrs)

    async def startup_init(self):
        self._control_device("local_read_device_on_off")

    async def refresh_state(self):
        """刷新设备状态"""
        self._control_device("local_read_device_on_off")
