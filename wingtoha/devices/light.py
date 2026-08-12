from .base import WingtoDevice

# the default range used to return brightness
from ..const import COL_TYPE_XY, COL_TYPE_HS

BRIGHTNESS_STD_RANGE = (1, 255)

# the default range used to return color temperature (in kelvin)
COLTEMP_KELV_RANGE = (2700, 6500)


class WingtoLight(WingtoDevice):

    def __init__(self, data, api):
        super().__init__(data, api)
        self.brightness_white_range = BRIGHTNESS_STD_RANGE
        self.brightness_color_range = BRIGHTNESS_STD_RANGE
        self._support_color = data[2][1][data[1]]['attrs'].get('color', False)
        self._support_color_tmp = data[2][1][data[1]]['attrs'].get('color_tmp', False)
        self._support_color_type = data[2][1][data[1]]['attrs'].get('color_type', COL_TYPE_XY)

    def _get_light_xy_color(self):
        try:
            return self._attrs[0x0300][3] / 65536, self._attrs[0x0300][4] / 65536
        except KeyError:
            return None, None

    def _get_light_hs_color(self):
        try:
            return self._attrs[0x0300][0] * 360 / 254, self._attrs[0x0300][1] * 100 / 254
        except KeyError:
            return None, None

    def brightness(self):
        """Return the brightness based on the light status scaled to standard range"""
        try:
            return round(self._attrs[8][0])
        except KeyError:
            return

    def xy_color(self):
        temp = self._get_light_xy_color()
        if temp[0] is None:
            return 0.5, 0.5
        return temp

    def hs_color(self):
        temp = self._get_light_hs_color()
        if temp[0] is None:
            return 0.5, 0.5
        return temp

    def _brightness_range(self):
        """return the configured brightness range based on the light status"""
        return self.brightness_color_range

    def support_color(self):
        """return if the light support color"""
        return self._support_color

    def support_color_temp(self):
        """return if the light support color temperature"""
        return self._support_color_tmp

    def support_color_type_hs(self):
        return self._support_color_type == COL_TYPE_HS

    @property
    def color_temp(self):
        """return current color temperature scaled with standard kelvin range"""
        try:
            return round(self._attrs[0x0300][7])
        except KeyError:
            return

    @property
    def min_color_temp(self):
        return COLTEMP_KELV_RANGE[1]

    @property
    def max_color_temp(self):
        return COLTEMP_KELV_RANGE[0]

    def turn_on(self):
        if self._control_device("turnOnOff", {"value": "1"}):
            attrs = [
                (self.get_eui64(), self.get_endpoint(), 6, 0, 1, None, None),
            ]
            self.api._add_async_to_mainthread(self.api._create_or_update_device_in_cor, attrs)
            self.update_state(True)

    def turn_off(self):
        if self._control_device("turnOnOff", {"value": "0"}):
            attrs = [
                (self.get_eui64(), self.get_endpoint(), 6, 0, 0, None, None),
            ]
            self.api._add_async_to_mainthread(self.api._create_or_update_device_in_cor, attrs)
            self.update_state(False)

    def set_brightness(self, brightness):
        """Set the brightness(0-255) of light."""
        if int(brightness) > 0:
            set_value = int(brightness)
            if set_value <= 3:
                set_value = 4
            set_value = (set_value - 3) / 252 * 255
            self._control_device("brightnessSet", {"value": round(set_value, 1)})
        else:
            self.turn_off()

    def set_color_hs(self, h, s):
        """Set the color of light."""
        hs_color = {"h": h, "s": s}
        if self._control_device("colorSetHS", {"color": hs_color}):
            self.update_state(True)

    def set_color_xy(self, x, y):
        """Set the color of light."""
        xy_color = {"x": x, "y": y}
        if self._control_device("colorSetXY", {"color": xy_color}):
            self.update_state(True)

    def set_color_temp(self, color_temp):
        """Set the color temperature of light."""
        self._control_device("colorTemperatureSet", {"value": round(color_temp)})

    def read_attr_on_off(self):
        self._control_device("local_read_device_on_off")

    def read_attr_brightness(self):
        self._control_device("local_read_light_brightness")

    def read_attr_color_tmp(self):
        self._control_device("local_read_light_color_tmp")

    def read_attr_color(self):
        self._control_device("local_read_light_color")

    async def startup_init(self):
        self.read_attr_on_off()
        self.read_attr_brightness()
        if self.support_color():
            self.read_attr_color()
        if self.support_color_temp():
            self.read_attr_color_tmp()

    async def refresh_state(self):
        """刷新设备状态"""
        self.read_attr_on_off()
        self.read_attr_brightness()
        if self.support_color():
            self.read_attr_color()
        if self.support_color_temp():
            self.read_attr_color_tmp()
