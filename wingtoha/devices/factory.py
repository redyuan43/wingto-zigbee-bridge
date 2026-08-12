from .light import WingtoLight
from .scene import WingtoScene
from .switch import WingtoSwitch
from .cover import WingtoCover
from .sensor import WingtoSensor
from .siren import WingtoSiren
from .lock import WingtoLock


def get_wingto_device(data, api):
    """

    @rtype: object
    """
    dev_type = data[1][0]
    if dev_type == "light":
        return WingtoLight(data, api)
    elif dev_type == "scene":
        return WingtoScene(data, api)
    elif dev_type == "switch":
        return WingtoSwitch(data, api)
    elif dev_type == "cover":
        return WingtoCover(data, api)
    elif dev_type == "siren":
        return WingtoSiren(data, api)
    elif "sensor" in dev_type:
        return WingtoSensor(data, api)
    elif dev_type == "lock":
        return WingtoLock(data, api)
