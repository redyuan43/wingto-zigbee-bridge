from .base import WingtoDevice


class WingtoSiren(WingtoDevice):

    def turn_on(self, kwargs):
        if len(kwargs) > 0:
            level = round(kwargs.get('volume_level', 0) * 4)
            warning_mode = kwargs.get('tone', 1)
            strobe = 1
            para1 = (warning_mode << 4) + (strobe << 2) + level
        else:
            para1 = 21
        para2 = kwargs.get('duration', 60)

        para1 = int.to_bytes(para1, length=1, byteorder='little')
        para2 = int.to_bytes(para2, length=2, byteorder='little')
        self._control_device("sirenOn", {'para1': para1.hex(), 'para2': para2.hex()})
        self.update_state(True)

    def turn_off(self):
        self._control_device("sirenOff", {"value": "0"})
        self.update_state(False)
