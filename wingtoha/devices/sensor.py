from .base import WingtoDevice


class WingtoSensor(WingtoDevice):

    def __init__(self, data, api):
        super().__init__(data, api)
        self._device_class = data[2][1][data[1]]['cls']
        self.get_func = None
        if self._device_class == 'humidity':
            self.get_func = self.get_humidity
        elif self._device_class == 'temperature':
            self.get_func = self.get_temperature
        elif self._device_class == 'battery':
            self.get_func = self.get_battery
        elif self._device_class == 'tamper':
            self.get_func = self.get_sensor_tamper
        elif self._device_class == 'illuminance':
            self.get_func = self.get_illuminance
            self.set_reportable_change_of_illuminance = self._set_reportable_change_of_illuminance
        elif self._device_class == 'move':
            self.get_func = self.get_move
        elif self._device_class in ('moisture', 'moving', 'opening', 'smoke'):
            self.get_func = self.get_sensor_alarm1
        elif self._device_class == 'gas':
            if data[1][1] == 1:
                self.get_func = self.get_sensor_alarm1
            else:
                self.get_func = self.get_sensor_alarm2
        elif self._device_class == 'motion':
            self.get_func = self.get_motion
            self.get_attribution = self.get_radar_attribution
            self.set_range_of_sensing_occupancy = self._set_range_of_sensing_occupancy

        self._unit = data[2][1][data[1]].get('unit', None)

    def _set_reportable_change_of_illuminance(self, val):
        para = int.to_bytes(val, length=1, byteorder='little')
        self._control_device("set_reportable_change_of_illuminance", {"value": para.hex()})

    def _set_range_of_sensing_occupancy(self, val):
        para = int.to_bytes(val, length=1, byteorder='little')
        self._control_device("set_range_of_sensing_occupancy", {"value": para.hex()})

    def get_radar_attribution(self):
        val1 = val2 = val3 = None
        if type(self._attrs) == dict and self._attrs.get(1030, {}).get(0, None) is not None:
            val = (self._attrs[1030][0] >> 1) & 7
            if val == 1:
                val1 = "有人移动"
            elif val == 2:
                val1 = "微动信号"
            elif val == 3:
                val1 = "呼吸信号"
            elif val == 4:
                val1 = "故障"
            else:
                val1 = "无人移动"
        if type(self._attrs) == dict and self._attrs.get(64651, {}).get(61442, None) is not None:
            val2 = self._attrs[64651][61442]
        if type(self._attrs) == dict and self._attrs.get(64651, {}).get(61444, None) is not None:
            val3 = self._attrs[64651][61444]
        return val1, val2, val3

    def get_unit(self):
        return self._unit

    def get_device_class(self):
        return self._device_class

    def get_motion(self):
        if type(self._attrs) == dict and self._attrs.get(1030, {}).get(0, None) is not None:
            return self._attrs[1030][0] & 1

    def get_battery(self):
        if type(self._attrs) == dict and self._attrs.get(1, {}).get(33, None) is not None:
            return self._attrs[1][33] / 2

    def get_illuminance(self):
        if type(self._attrs) == dict and self._attrs.get(1024, {}).get(0, None) is not None:
            return self._attrs[1024][0]

    def get_move(self):
        if type(self._attrs) == dict and self._attrs.get(1030, {}).get(0, None) is not None:
            return self._attrs[1030][0]

    def get_temperature(self):
        if type(self._attrs) == dict and self._attrs.get(1026, {}).get(0, None) is not None:
            return self._attrs[1026][0] / 100

    def get_humidity(self):
        if type(self._attrs) == dict and self._attrs.get(1029, {}).get(0, None) is not None:
            return self._attrs[1029][0] / 100

    def get_sensor_alarm1(self):
        if type(self._attrs) == dict and self._attrs.get(1280, {}).get(0, None) is not None:
            return self.api.get_bit_val(self._attrs[1280][0], 0)

    def get_sensor_alarm2(self):
        if type(self._attrs) == dict and self._attrs.get(1280, {}).get(0, None) is not None:
            return self.api.get_bit_val(self._attrs[1280][0], 1)

    def get_sensor_tamper(self):
        if type(self._attrs) == dict and self._attrs.get(1280, {}).get(0, None) is not None:
            return self.api.get_bit_val(self._attrs[1280][0], 2)

    async def startup_init(self):
        if self._device_class == 'motion':
            self._control_device("local_read_radar_attr")
