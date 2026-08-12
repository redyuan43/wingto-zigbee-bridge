from .base import WingtoDevice


class WingtoScene(WingtoDevice):
    def available(self):
        return True

    def activate(self):
        self.api.device_control(self.get_eui64(), self.get_endpoint(), "activate")
