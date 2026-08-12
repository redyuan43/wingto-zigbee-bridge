from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

import ppadb.client

from adb_shell.auth.keygen import keygen
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner


from .const import (
    WZB_LOCK_ALARM_DOORBELL,
    WZB_LOCK_ALARM_FACTORY_RESET,
    WZB_LOCK_ALARM_DEADBOLT_JAMMED,
    WZB_LOCK_ALARM_HELD,
    WZB_LOCK_ALARM_FORCED_OPEN,
    WZB_LOCK_ALARM_TAMPER_REMOVED,
    WZB_LOCK_ALARM_TAMPER_CODE_LIMIT,
    WZB_LOCK_ALARM_POWER_CYCLED,
    WZB_LOCK_ALARM_NOT_FULLY_LOCKED,
    WZB_LOCK_ALARM_DOOR_OPEN,
    WZB_LOCK_ALARM_KEY_REMAINED,
    GATEWAY_MODE_DEFAULT, COL_TYPE_HS,
)
from .devices.factory import get_wingto_device
from .mqtt import MQTT

_LOGGER = logging.getLogger(__name__)

_KEY_CLUSTERS = 'clusters'
_KEY_OBJ = 'obj'

# 格式含义：{'x-y': 'a-b'}
# a 代表device type(platform) b 代表device-class
# 其中x代表创建entity对象所需要的endpoint,可能包含虚拟的endpoint来表示其他属性。一个设备所拥有的x必须包含真实的endpoint,即y是x的子集
# 那么其值从哪个endpoint下面获取呢？这就是y所代表的含义。
# y=0代表几个endpoint共用一个属性。比如电量，1号endpoint或者2号endpoint可能都上报电量。这种共用属性的值保存在电池entity下面。
# 0<y<255 时， 其值保存在对象下的_attrs下


# 如果参数是字典，其中的type字段的值是设备类型；device_class 指定哪个endpoint下创建哪个device_class；
# 如果参数为字符串，值为设备类型
# ("HEIMAN", "HT-EF-3.0"): {
#     ("binary_sensor", 1, 256): {"cls": "sos"},
#     ("sensor",      255,   4): {"cls": "battery", "pure_event": True },
#     ("sensor",        2, 258): {"cls": "humidity"},
#     ("sensor",        1, 259): {"cls": "temperature"},
#     ("light",         3,   1): {"attrs": {"cw", "level"}},
#     ("switch",        4,   5): {},
# }
_DEVICE_TYPES = {
    # ("WingTo", "wingto:ctrl_hvac:hhc01"): 'unknown',
    # ("WingTo", "wingto:ctrl_hvac:hhc02"): 'unknown',
    # ("WingTo", "wt:ctrl_hvac::hh01:"): 'unknown',
    # ("WingTo", "wt:ctrl_hvac::hh01:01"): 'unknown',
    # ("WingTo", "wt:ctrl_hvac::hh03:"): 'unknown',
    # ("WingTo", "wt:ctrl_hvac:hvc01:"): 'unknown',
    ('AIBIC', 'K001_1'): {
        ('switch', 1, 1): {},
    },
    ('AIBIC', 'K001_2'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('AIBIC', 'K001_3'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('AIBIC', 'K003-1'): {
        ('switch', 1, 1): {},
    },
    ('AIBIC', 'K003-2'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('AIBIC', 'K003-3'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('HEIMAN', 'HT-EF-3.0'): {
        ('sensor', 1, 1): {'cls': 'temperature', 'unit': '°C'},
        ('sensor', 2, 2): {'cls': 'humidity', 'unit': '%'},
        ('sensor', 3, 1): {'cls': 'battery', 'unit': '%'},
    },
    ("HEIMAN", "PIRSensor-EF-3.0"): {
        ('binary_sensor', 1, 1): {'cls': 'moving'},
        ('binary_sensor', 2, 1): {'cls': 'tamper'},
        ('sensor', 3, 1): {'cls': 'battery', 'unit': '%'},
    },
    ("HEIMAN", "DoorSensor-EF-3.0"): {
        ('binary_sensor', 1, 1): {'cls': 'opening'},
        ('binary_sensor', 2, 1): {'cls': 'tamper'},
        ('sensor', 3, 1): {'cls': 'battery', 'unit': '%'},
    },
    ("HEIMAN", "GASSensor-EF-3.0"): {
        ('binary_sensor', 1, 1): {'cls': 'gas'},
        ('binary_sensor', 2, 1): {'cls': 'gas'},
    },
    ("HEIMAN", "SmokeSensor-EF-3.0"): {
        ('binary_sensor', 1, 1): {'cls': 'smoke'},
        ('binary_sensor', 2, 1): {'cls': 'tamper'},
        ('sensor', 3, 1): {'cls': 'battery', 'unit': '%'},
    },
    ("HEIMAN", "RadarSensor1-EF-3.0"): {
        ('sensor', 1, 1): {'cls': 'illuminance', 'unit': 'lx'},
        ('binary_sensor', 2, 1): {'cls': 'motion'},
    },
    ("HEIMAN", "WarningDevice-EF-3.0"): {
        ('siren', 1, 1): {},
    },
    ("HEIMAN", "WaterSensor-EF-3.0"): {
        ('binary_sensor', 1, 1): {'cls': 'moisture'},
        ('binary_sensor', 2, 1): {'cls': 'tamper'},
        ('sensor', 3, 1): {'cls': 'battery', 'unit': '%'},
    },
    ("HEIMAN", "SOS-EF-3.0"): {
        ('sensor', 1, 1): {'cls': 'battery', 'event': 'sensor_alarm', 'unit': '%'},
    },
    ('WINGTO', 'K001_1'): {
        ('switch', 1, 1): {},
    },
    ('WINGTO', 'K001_2'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WINGTO', 'K001_3'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WINGTO', 'K001_4'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
        ('switch', 4, 4): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:k051'): {
        ('switch', 1, 1): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:k052'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:k053'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:lk01'): {
        ('switch', 1, 1): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:lk02'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:lk03'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WingTo', 'wingto:ctrl_switch:bk01'): {
        ('switch', 1, 1): {},
    },
    ('WingTo', 'wingto:ctrl_switch:k051'): {
        ('switch', 1, 1): {},
    },
    ('WINGTO', 'wingto:ctrl_switch:k051'): {
        ('switch', 1, 1): {},
    },
    ('WingTo', 'wt:ctrl_switch::k051:00'): {
        ('switch', 1, 1): {},
    },
    ('WingTo', 'wingto:ctrl_switch:k052'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WingTo', 'wt:ctrl_switch::k052:00'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WingTo', 'wingto:ctrl_switch:k053'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WingTo', 'wt:ctrl_switch::k053:00'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WingTo', 'wingto:ctrl_switch:lk011'): {
        ('switch', 1, 1): {},
    },
    ('WingTo', 'wt:ctrl_switch::lk011:'): {
        ('switch', 1, 1): {},
    },
    ('WingTo', 'wingto:ctrl_switch:lk012'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WingTo', 'wt:ctrl_switch::lk012:'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WingTo', 'wingto:ctrl_switch:lk013'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WingTo', 'wt:ctrl_switch::lk013:'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
        ('switch', 3, 3): {},
    },
    ('WingTo', 'wingto:ctrl_switch:mc01'): {
        ('switch', 1, 1): {},
    },
    ('WINGTO', 'wt:ctrl_switch::bc01:00'): {
        ('switch', 1, 1): {},
        ('switch', 2, 2): {},
    },
    ('WingTo', 'wt:ctrl_plug::ls10:'): {
        ('switch', 1, 1): {},
    },
    ("WINGTO", "wingto:ctrl_switch:k054"): {
        ('scene', 1, 1): {},
        ('scene', 2, 2): {},
        ('scene', 3, 3): {},
        ('scene', 4, 4): {},
    },
    ("WINGTO", "wt:ctrl_switch::k054:00"): {
        ('scene', 1, 1): {},
        ('scene', 2, 2): {},
        ('scene', 3, 3): {},
        ('scene', 4, 4): {},
    },
    ("WINGTO", "K001_5"): {
        ('scene', 1, 1): {},
        ('scene', 2, 2): {},
        ('scene', 3, 3): {},
        ('scene', 4, 4): {},
        ('scene', 5, 5): {},
    },
    ('AIBIC', 'K002_4'): {
        ('scene', 1, 1): {},
        ('scene', 2, 2): {},
        ('scene', 3, 3): {},
        ('scene', 4, 4): {},
    },
    ("WINGTO", "wingto:ctrl_switch:lq015"): {
        ('scene', 1, 1): {},
        ('scene', 2, 2): {},
        ('scene', 3, 3): {},
        ('scene', 4, 4): {},
        ('scene', 5, 5): {},
    },
    ("WingTo", "wingto:ctrl_window:m:ce01"): {
        ('cover', 1, 1): {},
    },
    ("WingTo", "wt:ctrl_light:m006:cw:01"): {
        ('light', 1, 1): {'attrs': {'color_tmp': True}},
    },
    ("WingTo", "wt:ctrl-light:m006:dimm:01"): {
        ('light', 1, 1): {'attrs': {}},
    },
    ("WingTo", "wt:ctrl_light:m006:rgb:00"): {
        ('light', 1, 1): {'attrs': {'color': True}},
    },
    ("WingTo", "wt:ctrl_light:m006:rgbcw:00"): {
        ('light', 1, 1): {'attrs': {'color': True, 'color_tmp': True}},
    },
    ("WingTo", "wingto:ctrl_light:m006:cw"): {
        ('light', 1, 1): {'attrs': {'color_tmp': True}},
    },
    ("WingTo", "wingto:ctrl_light:m:rgbcw"): {
        ('light', 1, 1): {'attrs': {'color': True, 'color_tmp': True}},
    },
    ("WingTo", "wt:ctrl_light:m006:rgbcw:dp085"): {
        ('light', 1, 1): {'attrs': {'color': True, 'color_tmp': True, 'color_type': COL_TYPE_HS}},
    },
    ("WingTo", "wt:doorlock::sl01z:00"): {
        ('lock', 1, 1): {},
        ('sensor', 2, 1): {'cls': 'battery', 'unit': '%'},
    },
    ('Philips', 'LCT015'): {
        ('light', 1, 11): {'attrs': {'color': True, 'color_tmp': True}},
    },
    ('WingTo', GATEWAY_MODE_DEFAULT): {
        ('switch', 1, 1): {'ctr_type': 'adb'},
        ('switch', 2, 2): {'ctr_type': 'adb'},
    },
}


def _foo(*args, **kwargs):
    if not (args or kwargs):
        pass


def _get_device_info_by_table(attr_4, attr_5):
    if type(attr_5) != str or type(attr_5) != str:
        return None
    for key, val in _DEVICE_TYPES.items():
        if attr_4 == key[0] and attr_5 == key[1]:
            return key, val


def _gen_gateway_sign(cmd, tag, ver):
    salt = '6A23DC10FDB94227977501F62FB80BDD'
    src = cmd + tag + ver + salt
    md1 = hashlib.md5()
    md1.update(src.encode('UTF-8'))
    return md1.hexdigest()


class GatewayInfoGetter(object):
    """
    创建对象的时候需要在当前事件循环中的线程中创建，以便用其事件循环
    call_soon_threadsafe:在别的线程中被调用
    """

    Adb_lock = asyncio.Lock()

    def __init__(self, ip, port, is_adb=True):
        self._timeout = 7
        self._adb_timeout = 2
        self._adb_port = 5555
        self._p1s_name = 'P1s'
        self._p3_name = 'P3'
        self._p6s_name = 'P6s'
        self._p6box_name = 'P6box'
        self._ip = ip
        self._port = port
        self._loop = asyncio.get_event_loop()
        self._rev_done = self._loop.create_future()
        self._is_adb = is_adb
        self.mqtt = MQTT(
            self._ip,
            self._port,
            lambda target, *args: self._loop.create_task(target(*args)),
            self._message_received)

    def _set_result(self, eui64):

        if not self._rev_done.done():
            self._rev_done.set_result(eui64)

    def _message_received(self, topic, payload, qos):
        try:
            gw = re.findall('^gw/(.*)/(.*)', topic)[0]
        except IndexError:
            pass
        else:
            if len(gw[0]) > 0:
                self._loop.call_soon_threadsafe(self._set_result, gw[0])

    async def _get_eui64_by_mqtt(self):
        self._loop.create_task(self.mqtt.async_connect())
        result = None
        try:
            result = await asyncio.wait_for(self._rev_done, timeout=self._timeout)
        except asyncio.TimeoutError:

            pass
        finally:
            self._loop.create_task(self.mqtt.async_disconnect())
            return result

    async def _get_device_type_by_adb(self):
        result = None

        def _adb_cmd():
            with open(WingtoApi._ADB_KEY) as f:
                priv = f.read()
            with open(WingtoApi._ADB_KEY + '.pub') as f:
                pub = f.read()

            signer = PythonRSASigner(pub, priv)
            try:
                client = AdbDeviceTcp(self._ip, self._adb_port, default_transport_timeout_s=2.)
                client.connect(rsa_keys=[signer], auth_timeout_s=0.1)
            except OSError:
                return False
            recv = client.shell("getprop ro.product.model")
            if self._p1s_name.lower() in str(recv).lower():
                return self._p1s_name
            elif self._p3_name.lower() in str(recv).lower():
                return self._p3_name
            elif self._p6s_name.lower() in str(recv).lower():
                return self._p6s_name

            # client = ppadb.client.Client()
            # if client.remote_connect(self._ip, self._adb_port):
            #     device = client.device(f"{self._ip}:{self._adb_port}")
            #     if not device:
            #         return False
            #     try:
            #         recv = device.shell("getprop ro.product.model")
            #         if self._p1s_name.lower() in str(recv).lower():
            #             return self._p1s_name
            #         elif self._p3_name.lower() in str(recv).lower():
            #             return self._p3_name
            #     except RuntimeError:
            #         return False

        # adb 只能顺序访问
        async with GatewayInfoGetter.Adb_lock:
            try:
                result = await asyncio.wait_for(self._loop.run_in_executor(None, _adb_cmd), timeout=self._adb_timeout)
            except asyncio.TimeoutError:
                pass
        return result

    async def get_device_eui64_and_type(self):
        result = [await self._get_eui64_by_mqtt()]
        if result[0] is not None:
            if self._is_adb:
                result.append(await self._get_device_type_by_adb())
            else:
                result.append('G2')
        else:
            result.append(None)
        return result


def _convert_spec_cluster(cluster_id, attr_id):
    if cluster_id != 0xfc12:
        return None
    target_clusters = ((0xfc12, 0x0000, 0x0008, 0x0000),
                       (0xfc12, 0x0003, 0x0300, 0x0003),
                       (0xfc12, 0x0004, 0x0300, 0x0004),
                       (0xfc12, 0x0005, 0x0300, 0x0007),
                       (0xfc12, 0x0010, 0x0006, 0x0000),
                       (0xfc12, 0x0001, 0x0300, 0x0000),
                       (0xfc12, 0x0002, 0x0300, 0x0001),
                       (0xfc12, 0x0014, 0x0300, 0x0008),
                       (0xfc12, 0x0015, 0x0006, 0x4003),
                       (0xfc12, 0x0016, 0x0008, 0x0012),
                       (0xfc12, 0x0017, 0x0008, 0x0013))
    for val in target_clusters:
        if val[0] == cluster_id and val[1] == attr_id:
            return val[2:]


class WingtoApi(object):
    """Wingto API, to manage the devices list, and the MQTT connections"""

    _ADB_KEY='/tmp/adbkey'
    _= keygen(_ADB_KEY)
    _KEY_IP_ADDRESS = "_ip_address"
    _KEY_BROKER_PORT = "_broker_port"
    _ZCL_DATATYPE_W_LENGTH = {
        0x19: 2, 0x1a: 3, 0x1b: 4, 0x1d: 6, 0x1f: 8, 0x18: 1, 0x10: 1, 0x08: 1,
        0x31: 2, 0x30: 1, 0xf0: 8, 0x29: 2, 0x21: 2, 0x2a: 3, 0x22: 3, 0x2b: 4,
        0x23: 4, 0x25: 6, 0x26: 7, 0x27: 8, 0x28: 1, 0x20: 1, 0xf1: 16, 0xe2: 4,
        0x2d: 6, 0x2f: 8}

    _list_objects = []

    def __new__(cls, *args, **kw):
        for obj in cls._list_objects:
            if getattr(obj, cls._KEY_IP_ADDRESS, "none") == kw.get("ip", "null") \
                    and getattr(obj, cls._KEY_BROKER_PORT, "none") == kw.get("port", "null"):
                return obj
        obj = object.__new__(cls)
        cls._list_objects.append(obj)
        return obj

    def __init__(self,
                 *, ip="127.0.0.1", port=1883,
                 update_entities_list=None,
                 event_trigger_types=None,
                 add_async_to_mainthread,
                 gateway_type='G2',
                 gateway_eui64=None,
                 ) -> None:

        if hasattr(self, self._KEY_IP_ADDRESS):
            # the gateway with the same IP has been initialized
            if getattr(self, "_recall_scene_trigger", _foo) in (_foo, None):
                self._recall_scene_trigger = event_trigger_types['recall_scene_trigger'] or _foo
            if getattr(self, "_sensor_alarm_trigger", _foo) in (_foo, None):
                self._sensor_alarm_trigger = event_trigger_types['sensor_alarm_trigger'] or _foo
            if getattr(self, "_lock_trigger", _foo) in (_foo, None):
                self._lock_trigger = event_trigger_types['lock_trigger'] or _foo
            if getattr(self, "_update_entities_list", _foo) in (_foo, None):
                self._update_entities_list = update_entities_list or _foo
                self._broadcast_to_read_all()
            return

        # the initialization of a new WingtoApi instance
        setattr(self, self._KEY_IP_ADDRESS, ip)
        setattr(self, self._KEY_BROKER_PORT, port)

        if gateway_eui64 is None:
            self._gateway_eui64 = ''
        else:
            self._gateway_eui64 = gateway_eui64
        self._broadcast_sent_tag = False
        self._gateway_mac = ""
        self._gateway_ver = 0

        self._devices_dict = {}
        self._gateway_type = gateway_type
        self._adb_lock = asyncio.Lock()

        # _devices_dict = {
        #     "eui64_1": dict_1,
        #     ...
        #     "eui64_n": {
        #         "endpoint_1": dict_1,
        #         ...
        #         "endpoint_n": {
        #             "obj": [] list of instances of WingtoSwitch with several methods
        #             "clusters":{
        #                 "cluster_1": dict_1,
        #                 ...
        #                 "cluster_n": {
        #                     "attribute_1": val_1,
        #                     ...
        #                     "attribute_n": val_n,
        #                 }
        #             }
        #         }
        #     }
        # }
        # 如果被创建过 entity 实体，"obj" 非 None
        # 没有被创建过 entity 实体，"obj" 为 None
        #     如果没有收到过 4、5，则 "4","5" 为 None，下次收到任意帧都会触发发送 "4" "5" 的读取
        #     如果已经收到过 4、5，且当时不认识，则 "4","5" 为 ''; 否则，就一定会创建 entity 实体

        if update_entities_list is not None:
            self._update_entities_list = update_entities_list
            # self._broadcast_to_read_all()
        else:
            self._update_entities_list = _foo
        self._recall_scene_trigger = event_trigger_types['recall_scene_trigger'] or _foo
        self._sensor_alarm_trigger = event_trigger_types['sensor_alarm_trigger'] or _foo
        self._lock_trigger = event_trigger_types['lock_trigger'] or _foo
        self._add_async_to_mainthread = add_async_to_mainthread

        self.mqtt = MQTT(
            getattr(self, self._KEY_IP_ADDRESS, "0.0.0.0"),
            getattr(self, self._KEY_BROKER_PORT, 1883),
            self._add_async_to_mainthread,
            self.message_received)

        self._add_async_to_mainthread(self.mqtt.async_connect)

    async def change_model(self, new):
        old = self._gateway_type
        self._gateway_type = new
        if old == GATEWAY_MODE_DEFAULT and new != GATEWAY_MODE_DEFAULT:
            if self._gateway_eui64 in self._devices_dict:
                del self._devices_dict[self._gateway_eui64]
                self._update_entities_list()
        elif old != GATEWAY_MODE_DEFAULT and new == GATEWAY_MODE_DEFAULT:
            self._add_async_to_mainthread(self._create_gateway_spec_device)
            self._update_entities_list()

    def _broadcast_to_read_all(self):
        """attempt to broadcast, to get all of the devices in the current Zigbee network"""

        if self._broadcast_to_read_all == _foo:
            # Already sent once
            return
        if self._update_entities_list in (None, _foo):
            # Not ready, for the entities update can't be implemented
            return
        if self._gateway_eui64 == "":
            # Not ready, for the MQTT topic is not clear
            return
        # self.device_control(None, None, action="broadcastToReadAll")
        self.broadcast_to_read_all()
        # Only broadcast once
        self._broadcast_to_read_all = _foo

    @staticmethod
    def get_bit_val(val, index):
        if val & (1 << index):
            return 1
        else:
            return 0

    async def _create_gateway_spec_device(self):
        if self._gateway_type == GATEWAY_MODE_DEFAULT:
            # f"{eui64.lower()}[{endpoint}].{device_type}.{attr_5}",
            await self.create_device_by_entity([f"{self._gateway_eui64.lower()}[{1}].{'switch'}.{self._gateway_type}"])

    async def _create_or_update_device_in_cor(self, list_attr):
        # 关联全局变量，处理放到协程中处理
        state_change_tag = False
        on_off_value = None
        for args in list_attr:
            eui64, endpoint, cluster_id, attr_id, new_val, zcl_cmd, cluster_specific = args

            # 自定义的cluster转换为标准cluster
            # (由于标准的zigbee只能传输一个cluster下的属性，为了一次性传输多个不同cluster的属性用了自定义属性去表示标准的属性)
            convert_ret = _convert_spec_cluster(cluster_id, attr_id)
            if isinstance(convert_ret, tuple) and len(convert_ret) == 2:
                cluster_id, attr_id = convert_ret

            # 特殊处理lock
            if cluster_id == 0x101 and attr_id == 0 and isinstance(new_val, int):
                if 3 <= new_val <= 0xFF:
                    continue
                elif new_val == 300:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_DOORBELL)
                    continue
                elif new_val == 301:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_FACTORY_RESET)
                    continue
            if cluster_id == 0x9 and attr_id == 0 and isinstance(new_val, int):
                if new_val == 0:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_DEADBOLT_JAMMED)
                elif new_val == 3:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_POWER_CYCLED)
                elif new_val == 4:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_TAMPER_CODE_LIMIT)
                elif new_val == 5:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_TAMPER_REMOVED)
                elif new_val == 6:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_FORCED_OPEN)
                elif new_val == 0x80:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_HELD)
                elif new_val == 0x81:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_NOT_FULLY_LOCKED)
                elif new_val == 0x82:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_DOOR_OPEN)
                elif new_val == 0x83:
                    self._lock_trigger(self.gen_device_id(eui64, endpoint), WZB_LOCK_ALARM_KEY_REMAINED)
                continue
            # lock end

            old_val = self._devices_dict.get(eui64, {}).get(endpoint, {}).get(_KEY_CLUSTERS, {}).get(cluster_id,
                                                                                                     {}).get(attr_id,
                                                                                                             None)
            self._devices_dict.setdefault(eui64, {}).setdefault(endpoint, {}).setdefault(_KEY_CLUSTERS, {}).setdefault(
                cluster_id, {})[
                attr_id] = new_val

            if old_val != new_val:
                state_change_tag = True
                # get state value of on_off
                if cluster_id == 6 and attr_id == 0:
                    on_off_value = new_val

            if self._devices_dict[eui64][endpoint].get('obj', None):
                for obj in self._devices_dict[eui64][endpoint]['obj']:

                    # 1.1 update entity of endpoint. when state of device changed, notify ha update state
                    if state_change_tag and hasattr(obj, 'update_state'):
                        obj.update_state(on_off_value)

                    # 1.2 fire event for specific device (eg, SOS-EF-3.0)
                    if obj.support_event == 'sensor_alarm' and zcl_cmd == 0 and cluster_specific:
                        self._sensor_alarm_trigger(obj.object_id())
            else:
                self._create_entities_for_device_by_endpoint(eui64, endpoint)

    def _parse_topic_wingto_zclresponse_response(self, args):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        index = 6
        list_attr = []
        parse_suc_tag = True
        while index + 8 <= len(payload):
            attr_id = int(payload[index:2 + index], base=16) + (int(payload[index + 2:4 + index], base=16) << 8)
            data_type = int(payload[4 + index:6 + index], base=16)
            if 0x41 <= data_type <= 0x44:
                data_len = int(payload[index + 6:8 + index], base=16)
                if 8 + index + data_len * 2 <= len(payload):
                    attr_val = ''.join(
                        chr(int(i, 16)) for i in re.findall('..', payload[8 + index:8 + index + data_len * 2]))
                    index = index + 6 + (1 + data_len) * 2
                else:
                    parse_suc_tag = False
                    break
            else:
                start_pos = 6 + index
                try:
                    end_pos = start_pos + self._ZCL_DATATYPE_W_LENGTH[data_type] * 2
                except KeyError:
                    return
                if end_pos <= len(payload):
                    attr_val = int.from_bytes(int(payload[start_pos:end_pos], base=16).to_bytes(
                        self._ZCL_DATATYPE_W_LENGTH[data_type], 'big'), 'little')
                    index = end_pos
                else:
                    parse_suc_tag = False
                    break
            attr_tuple = (eui64, endpoint, cluster_id, attr_id, attr_val, zcl_cmd, cluster_specific)
            list_attr.append(attr_tuple)
        if parse_suc_tag:
            return list_attr

    def _parse_topic_wingto_zclresponse_readback(self, args):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, mfg_code, payload = args
        if mfg_code is not None:
            index = 10
        else:
            index = 6
        list_attr = []
        parse_suc_tag = True
        while index + 8 <= len(payload):
            attr_id = int(payload[index:2 + index], base=16) + (int(payload[index + 2:4 + index], base=16) << 8)
            status = int(payload[index + 4:6 + index], base=16)
            data_type = int(payload[6 + index:8 + index], base=16)
            if status != 0:
                index = index + 6
                if status == 0x86:
                    attr_tuple = (eui64, endpoint, cluster_id, attr_id, '', zcl_cmd, cluster_specific)
                    list_attr.append(attr_tuple)
                    continue
                else:
                    parse_suc_tag = False
                    break

            if 0x41 <= data_type <= 0x44:
                data_len = int(payload[index + 8:10 + index], base=16)
                if index + 10 + data_len * 2 <= len(payload):
                    attr_val = ''.join(
                        chr(int(i, 16)) for i in re.findall('..', payload[10 + index:10 + index + data_len * 2]))
                    index = index + 8 + (1 + data_len) * 2
                else:
                    parse_suc_tag = False
                    break
            else:
                start_pos = 8 + index
                try:
                    end_pos = start_pos + self._ZCL_DATATYPE_W_LENGTH[data_type] * 2
                except KeyError:
                    return
                if end_pos <= len(payload):
                    attr_val = int.from_bytes(int(payload[start_pos:end_pos], base=16).to_bytes(
                        self._ZCL_DATATYPE_W_LENGTH[data_type], 'big'), 'little')
                    index = end_pos
                else:
                    parse_suc_tag = False
                    break
            attr_tuple = (eui64, endpoint, cluster_id, attr_id, attr_val, zcl_cmd, cluster_specific)

            list_attr.append(attr_tuple)
        if parse_suc_tag:
            return list_attr

    @staticmethod
    def _parse_topic_wingto_specific_dev(args, val=None):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        list_attr = []
        attr_tuple = (eui64, endpoint, cluster_id, 0, val, zcl_cmd, cluster_specific)
        list_attr.append(attr_tuple)
        return list_attr

    @staticmethod
    def _parse_topic_wingto_0x101_1(args, val=None):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        list_attr = []
        attr_tuple = (eui64, endpoint, cluster_id, 10, int(payload[-2:], 16), zcl_cmd, cluster_specific)
        list_attr.append(attr_tuple)
        if int(payload[-2:], 16) == 0:
            attr_tuple = (eui64, endpoint, cluster_id, 0, 258, zcl_cmd, cluster_specific)
            list_attr.append(attr_tuple)
        list_attr.append(attr_tuple)
        return list_attr

    @staticmethod
    def _parse_topic_wingto_0x9_0(args, val=None):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        if len(payload) < 12 or cluster_specific is not True:
            return
        if payload[8:12] == '0101':
            alarm_code = int(payload[6:8], 16)
            list_attr = []
            attr_tuple = (eui64, endpoint, cluster_id, 0, alarm_code, zcl_cmd, cluster_specific)
            list_attr.append(attr_tuple)
            if alarm_code == 0:
                attr_tuple = (eui64, endpoint, 0x101, 0, 259, zcl_cmd, cluster_specific)
                list_attr.append(attr_tuple)
            return list_attr

    @staticmethod
    def _parse_topic_wingto_0x101_0x20(args, val=None):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        event_source = int(payload[6:8], 16)
        event_code = int(payload[8:10], 16)
        event_state = ''
        if event_code == 1 or event_code == 2:
            event_state = event_code
        elif event_code == 0xf:
            if payload[24:26] == '0180':
                event_state = 256
            elif payload[24:28] == '0181':
                event_state = 257
            elif payload[24:28] == '0182':
                event_state = 300
            elif payload[24:28] == '0183':
                event_state = 301
        list_attr = []
        attr_tuple = (eui64, endpoint, cluster_id, 0, event_state, zcl_cmd, cluster_specific)
        # changed_by
        attr_tuple1 = (eui64, endpoint, cluster_id, 11, event_source, zcl_cmd, cluster_specific)
        list_attr.append(attr_tuple)
        list_attr.append(attr_tuple1)
        return list_attr

    @staticmethod
    def _parse_topic_wingto_sensor(args):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload = args
        start_pos = 6
        end_pos = 10
        if len(payload) < end_pos or cluster_specific is not True:
            return
        attr_val = int.from_bytes(int(payload[start_pos:end_pos], base=16).to_bytes(2, 'big'), 'little')
        list_attr = []
        attr_tuple = (eui64, endpoint, cluster_id, 0, attr_val, zcl_cmd, cluster_specific)
        list_attr.append(attr_tuple)
        return list_attr

    @staticmethod
    def _parse_topic_wingto_custom(args):
        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, mfg_code, payload = args
        if cluster_specific and cluster_id == 257 and mfg_code == '0x117B':
            tmp = [int(i, 16) for i in re.findall('..', payload[12:])]
            return [(eui64, endpoint, cluster_id, 2, tmp, None, None)]

    def _get_device_info(self, device, in_attr_id):
        obj = self._devices_dict.get(device, None)
        if type(obj) != dict:
            return
        for endpoint, val in obj.items():
            for cluster_id, val1 in val[_KEY_CLUSTERS].items():
                if cluster_id == 0 and type(val1) == dict:
                    for attr_id, val2 in val1.items():
                        if attr_id == in_attr_id:
                            return val2

    def _create_objs_for_device(self, eui64, device_info):
        attrs_dic = device_info[1]
        for key_endpoints, val_attrs in attrs_dic.items():
            # check para
            if len(key_endpoints) != 3:
                return
            # init dict memory
            self._devices_dict.setdefault(eui64, {}).setdefault(key_endpoints[2], {}).setdefault(_KEY_OBJ, [])
            self._devices_dict.setdefault(eui64, {}).setdefault(key_endpoints[2], {}).setdefault(_KEY_CLUSTERS, {})

            # create obj and init
            obj_para = (eui64, key_endpoints, device_info, self._devices_dict[eui64][key_endpoints[2]][_KEY_CLUSTERS])
            device_obj = get_wingto_device(obj_para, self)
            self._devices_dict[eui64][key_endpoints[2]][_KEY_OBJ].append(device_obj)

            if hasattr(device_obj, 'startup_init'):
                self._add_async_to_mainthread(device_obj.startup_init)

    def _create_entities_for_device_by_endpoint(self, eui64, endpoint):
        attr_4 = self._get_device_info(eui64, 4)
        attr_5 = self._get_device_info(eui64, 5)
        # 沒有读到4，5属性, 需要继续读属性
        if attr_4 is None or attr_5 is None:
            self.device_control(eui64, endpoint, action="local_read_device_type")
            return

        device_info = _get_device_info_by_table(attr_4, attr_5)
        if device_info:
            self._create_objs_for_device(eui64, device_info)
            self._update_entities_list()

    async def create_device_by_entity(self, names):
        """"create devices by entities with 'original_name'"""

        # f"{eui64.lower()}[{endpoint}].{device_type}.{attr_5}",
        pattern = re.compile(
            r'(?P<eui64>[0-9a-fA-F]{16})\[[0-9]+]\.(?P<device_type>[^.]*)\.(?P<model_id>.*)$'
        )

        models = set()
        for name in names:
            if not (info := pattern.findall(name)):
                continue
            models.add(info[0])

        while not self._gateway_eui64:
            await asyncio.sleep(1)

        for eui64, device_type, model_id in models:
            manufacturer_name = ''
            endpoint = None
            for k, v in _DEVICE_TYPES.items():
                if model_id != k[1]:
                    continue
                for typ, _, ep in v.keys():
                    if typ != device_type:
                        continue
                    endpoint = ep
                    break
                if endpoint is None:
                    continue
                manufacturer_name = k[0]
                break
            if not manufacturer_name:
                continue

            eui64 = eui64.upper()
            attrs = [
                (eui64, endpoint, 0, 4, manufacturer_name, None, None),
                (eui64, endpoint, 0, 5, model_id, None, None),
            ]

            await self._create_or_update_device_in_cor(attrs)

    def get_device_by_id(self, dev_id):
        for _, val in self._devices_dict.items():
            for _, val1 in val.items():
                if not val1.get(_KEY_OBJ, None):
                    continue
                for obj in val1[_KEY_OBJ]:
                    if dev_id == obj.object_id():
                        return obj

    @staticmethod
    def gen_device_id(eui64, endpoint):
        return eui64 + '.' + str(endpoint)

    def get_all_devices(self):
        devices = []
        for _, val in self._devices_dict.items():
            for _, val1 in val.items():
                if val1.get(_KEY_OBJ, None) is not None:
                    devices.extend(val1[_KEY_OBJ])
        return devices

    async def wait_for_mqtt_ready(self, timeout=30):
        """等待MQTT连接建立"""
        start_time = asyncio.get_event_loop().time()
        while not self.mqtt.connected:
            if asyncio.get_event_loop().time() - start_time > timeout:
                _LOGGER.warning("MQTT connection timeout after %d seconds", timeout)
                break
            await asyncio.sleep(0.5)
        
        # 再等待一点时间确保连接稳定
        if self.mqtt.connected:
            await asyncio.sleep(2)

    async def refresh_all_device_states(self):
        """刷新所有设备的状态"""
        _LOGGER.info("Refreshing all device states...")
        
        for eui64, endpoints in self._devices_dict.items():
            for endpoint, endpoint_data in endpoints.items():
                if not endpoint_data.get(_KEY_OBJ, None):
                    continue
                
                for device_obj in endpoint_data[_KEY_OBJ]:
                    try:
                        # 根据设备类型调用相应的状态读取方法
                        if hasattr(device_obj, 'refresh_state'):
                            await device_obj.refresh_state()
                        elif hasattr(device_obj, 'startup_init'):
                            # 如果没有refresh_state方法，重新调用startup_init
                            await device_obj.startup_init()
                    except Exception as e:
                        _LOGGER.warning("Failed to refresh state for device %s: %s", 
                                      device_obj.object_id(), e)
                    
                    # 给设备一些时间处理状态读取请求
                    await asyncio.sleep(0.5)

    def handle_topic_left(self, payload):
        dic = json.loads(payload)
        if dic['eui64'] in self._devices_dict:
            del self._devices_dict[dic['eui64']]
            self._update_entities_list()

    def message_received(self, topic: str, payload: str, qos: int) -> None:
        """A new MQTT message has been received."""
        try:
            gw = re.findall('^gw/(.*)/(.*)', topic)[0]
            if self._broadcast_sent_tag is False:
                self._broadcast_sent_tag = True
                if len(self._gateway_eui64) == 0:
                    self._gateway_eui64 = gw[0]
                # attempt to broadcast, to get all of the devices in the current Zigbee network
                self._broadcast_to_read_all()
                self._add_async_to_mainthread(self._create_gateway_spec_device)
            else:
                if gw[0] == self._gateway_eui64:
                    if re.match(r'.*wingto_zclresponse$', str(topic)):
                        try:
                            dic = json.loads(payload)
                            eui64 = dic['deviceEndpoint']['eui64']
                            endpoint = dic['deviceEndpoint']['endpoint']
                            zcl_cmd = int(dic['commandId'], base=16)
                            cluster_id = int(dic['clusterId'], base=16)
                            cluster_specific = dic.get('clusterSpecific', None)
                            payload_data = dic['payload']
                            mfg_code = dic.get('mfgCode', None)

                        except (json.decoder.JSONDecodeError, KeyError):
                            _LOGGER.info(topic + ':' + payload)
                        else:
                            list_attr = None
                            para = (eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, payload_data)
                            if zcl_cmd == 10:
                                list_attr = self._parse_topic_wingto_zclresponse_response(para)
                            elif zcl_cmd == 1:
                                if not cluster_specific:
                                    para = (
                                        eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, mfg_code, payload_data)
                                    list_attr = self._parse_topic_wingto_zclresponse_readback(para)
                                elif cluster_id == 0x101:
                                    list_attr = self._parse_topic_wingto_0x101_1(para)
                            elif zcl_cmd == 5:
                                list_attr = self._parse_topic_wingto_specific_dev(para)
                            elif zcl_cmd == 0:
                                if cluster_id == 0x9:
                                    list_attr = self._parse_topic_wingto_0x9_0(para)
                                else:
                                    list_attr = self._parse_topic_wingto_sensor(para)
                            elif zcl_cmd == 0x80:
                                para = (eui64, endpoint, cluster_id, zcl_cmd, cluster_specific, mfg_code, payload_data)
                                list_attr = self._parse_topic_wingto_custom(para)
                            elif zcl_cmd == 0x20:
                                if cluster_specific and cluster_id == 0x101:
                                    list_attr = self._parse_topic_wingto_0x101_0x20(para)

                            if list_attr:
                                self._add_async_to_mainthread(self._create_or_update_device_in_cor, list_attr)
        except IndexError:
            pass
        finally:
            if re.match(r'\$ricisung$', str(topic)):
                try:
                    dic = json.loads(payload)
                    gateway_mac = dic['gwmac']
                    ver = dic['ver']
                    cmd = dic['cmd']
                    if self._gateway_mac != gateway_mac:
                        self._gateway_mac = gateway_mac
                    if self._gateway_ver != ver:
                        self._gateway_ver = ver
                    if cmd == '120011':
                        device_mac = dic['devicemac']
                        index = dic['index']
                        device_mac = device_mac.replace('-', '')
                        self._recall_scene_trigger(self.gen_device_id(device_mac, int(index)))
                    elif cmd == '150000':
                        device_mac = dic['data'][0]['devicemac']
                        index = dic['data'][0]['DeviceIndex']
                        err_code = dic['data'][0]['ErrCode']
                        device_mac = device_mac.replace('-', '')
                        attrs = [(device_mac, index, 6, 0, err_code, None, None)]
                        self._add_async_to_mainthread(self._create_or_update_device_in_cor, attrs)
                    elif cmd == '150001':
                        device_mac = dic['data'][0]['devicemac']
                        index = dic['data'][0]['DeviceIndex']
                        attr_hex = dic['data'][0]['AttrHex'] & 0xffffffff
                        attr_val = dic['data'][0]['AttrValue']
                        device_mac = device_mac.replace('-', '')
                        attrs = [(device_mac, index, attr_hex >> 16, attr_hex & 0xffff, attr_val, None, None)]
                        self._add_async_to_mainthread(self._create_or_update_device_in_cor, attrs)

                except (json.decoder.JSONDecodeError, KeyError):
                    _LOGGER.info(topic + ':' + payload)
            elif re.match(r'\$gw/child', str(topic)):
                try:
                    dic = json.loads(payload)
                    cmd = dic['cmd']
                    if cmd == '120005' and isinstance(dic['data'], list):
                        attr_cmd = dic['data'][0]['AttrCmd']
                        if attr_cmd != 67174789:
                            return
                        attr_val = dic['data'][0]['AttrValue']
                        if attr_val[0:6] != '0x117B':
                            return
                        index = dic['data'][0]['DeviceIndex']
                        device_mac = dic['devicemac']

                        def encrypt_xor(var, key):
                            ret = list()
                            for i in range(len(key)):
                                ret.append(var[i] ^ key[i])
                            return ret

                        tmp = [int(i, 16) for i in re.findall('..', attr_val[6:])]
                        attr_val = encrypt_xor(tmp, str.encode(device_mac))
                        device_mac = device_mac.replace('-', '')
                        attrs = [(device_mac, index, 257, 1, attr_val, None, None)]
                        self._add_async_to_mainthread(self._create_or_update_device_in_cor, attrs)
                except (json.decoder.JSONDecodeError, KeyError):
                    _LOGGER.info(topic + ':' + payload)

    def _device_control_send_cmd(self, *args):
        mac, endpoint, attr_cmd, attr_val = args
        tmp_mac = re.findall(".{2}", mac)
        new_mac = "-".join(tmp_mac)
        message = f'{{ "cmd": "120005", "data": [ {{ "AttrCmd": {attr_cmd}, "AttrDataType": "", ' \
                  f' "AttrValue": "{attr_val}", "DeviceIndex": {endpoint} }} ],' \
                  f' "devicemac": "{new_mac}", "gwmac": "{self._gateway_mac}", ' \
                  '"sign": "6725cf5d8430aab11ac58c20b64a0fe0", "tag": 1641885387, "ver": 10010100 }'
        self.mqtt.publish(f"$gw/child/{self._gateway_mac}", message)

    def device_control(self, mac, endpoint, action, param=None):
        if param is None:
            param = {}

        if action == 'turnOnOff':
            if int(param['value']) == 0:
                # off
                self._device_control_send_cmd(mac, endpoint, 1536, '0x')
            else:
                # on
                self._device_control_send_cmd(mac, endpoint, 1537, '0x')
        elif action == 'brightnessSet':
            self._device_control_send_cmd(mac, endpoint, 2048, '0x' +
                                          int.to_bytes(round(param['value']), length=1,
                                                       byteorder='little').hex() + '0A00')
        elif action == 'colorSetHS':
            self._device_control_send_cmd(mac, endpoint, 196614, '0x' +
                                          int.to_bytes(round(param['color']['h']), length=1,
                                                       byteorder='little').hex() +
                                          int.to_bytes(round(param['color']['s']), length=1,
                                                       byteorder='little').hex() +
                                          '0A00')
        elif action == 'colorSetXY':
            self._device_control_send_cmd(mac, endpoint, 196615, '0x' +
                                          int.to_bytes(round(param['color']['x'] * 65536), length=2,
                                                       byteorder='little').hex() +
                                          int.to_bytes(round(param['color']['y'] * 65536), length=2,
                                                       byteorder='little').hex() +
                                          '0A00')
        elif action == 'colorTemperatureSet':
            self._device_control_send_cmd(mac, endpoint, 196618, '0x' +
                                          int.to_bytes(param['value'], length=2,
                                                       byteorder='little').hex() + '0A00')
        elif action == 'window-covering-up':
            message = '{{"commands":[' \
                      '{{"command":"zcl window-covering up"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'window-covering-down':
            message = '{{"commands":[' \
                      '{{"command":"zcl window-covering down"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'window-covering-stop':
            message = '{{"commands":[' \
                      '{{"command":"zcl window-covering stop"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'window-covering-percent':
            message = '{{"commands":[' \
                      '{{"command":"zcl window-covering go-to-lift-percent {2}"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint, param['position'])
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'sirenOn':
            message = '{{"commands": [' \
                      '{{"command":"raw 0x0502 {{11 00 00 {0} {1} 32 00}}"}},' \
                      '{{"command":"plugin device-table send {{{2}}} {3}"}}' \
                      ']}}'.format(param['para1'], param['para2'], mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'sirenOff':
            message = '{"commands": [' \
                      '{"command":"raw 0x0502 {11 00 00 00 0000 32 00}"},' \
                      f'{{"command":"plugin device-table send {{{mac}}} {endpoint}"}}' \
                      ']}'
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'set_range_of_sensing_occupancy':
            message = '{{"commands": [' \
                      '{{"command":"raw 0xFC8B {{14 0B12 00 05 02F0 20 {0}}}"}},' \
                      '{{"command":"plugin device-table send {{{1}}} {2}"}}' \
                      ']}}'.format(param['value'], mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'set_reportable_change_of_illuminance':
            message = '{{"commands": [' \
                      '{{"command":"raw 0xFC8B {{14 0B12 FF 05 04F0 20 {0}}}"}},' \
                      '{{"command":"plugin device-table send {{{1}}} {2}"}}' \
                      ']}}'.format(param['value'], mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_device_type":
            message = '{"commands": [' \
                      '{"command":"raw 0 {10 00 00 0400 0500 0040}"},' \
                      f'{{"command":"plugin device-table send {{{mac}}} {endpoint}"}}' \
                      ']}'
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_device_battery":
            message = '{"commands": [' \
                      '{"command":"raw 0x0001 {10 FF 00 2100}"},' \
                      f'{{"command":"plugin device-table send {{{mac}}} {endpoint}"}}' \
                      ']}'
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_lock_timeout":
            message = '{"commands": [' \
                      '{"command":"raw 0x0101 {14 7B11 FF 00 01F0}"},' \
                      f'{{"command":"plugin device-table send {{{mac}}} {endpoint}"}}' \
                      ']}'
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_device_on_off":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 6 0"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_light_brightness":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 8 0"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_light_color_tmp":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 0x0300 7"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_light_color":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 0x0300 3"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 0x0300 4"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_cover_pos":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 258 8"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "local_read_radar_attr":
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 0x0400 0"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
            message = '{{"commands":[' \
                      '{{"command":"zcl global read 0x0406 6"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
            message = '{{"commands":[' \
                      '{{"command": "raw 0xFC8B {{14 0B12 00 00 02F0 04F0}}"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'broadcastToReadAll':
            message = '{"commands": [' \
                      '{"command":"raw 0 {10 00 00 0400 0500 0040}"},' \
                      '{"command":"send 0xFFFF 1 255"}' \
                      ']}'
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == "activate":
            tag = 1637749381
            cmd = "120011"
            sign = _gen_gateway_sign(cmd, str(tag), str(self._gateway_ver))
            tmp_mac = re.findall(".{2}", mac)
            new_mac = "-".join(tmp_mac)
            message = f'{{"cmd": "{cmd}", "tag": {tag}, "sign": "{sign}", "ver":{str(self._gateway_ver)},' \
                      f' "gwmac":"{self._gateway_mac}", "devicemac": "{new_mac}", "index":{endpoint} }} '
            self.mqtt.publish("$ricisung", message)
        elif action == 'lock':
            self._device_control_send_cmd(mac, endpoint, 65793, param['value'])
        elif action == 'lock_get_aes_key':
            message = f'{{"clusterId": "0x0101", "commandId": "0x85", "clusterSpecific": true, "mfgCode": "0x117B", ' \
                      f'"payload": "1D7B11FF85", "dstEndpoint": 1, ' \
                      f'"deviceEndpoint": {{"eui64": "{mac}", "endpoint": 1}}}}'
            self.mqtt.publish(f'gw/{self._gateway_eui64}/wingto_zclresponse', message)
        elif action == 'lock_get_random_number':
            message = '{{"commands":[' \
                      '{{"command": "raw 0x0101 {{15 7B11 FF 80}}"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'lock_set_auto_lock_time':
            message = '{{"commands":[' \
                      '{{"command": "raw 0x0101 {{15 7B11 FF 81 {2}}}"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint, param['value'])
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'lock_read_state':
            message = '{{"commands":[' \
                      '{{"command": "raw 0x0101 {{10 FF 00 0000}}"}},' \
                      '{{"command":"plugin device-table send {{{0}}} {1}"}}' \
                      ']}}'.format(mac, endpoint)
            self.mqtt.publish(f"gw/{self._gateway_eui64}/commands", message)
        elif action == 'adb_ctr_on':
            self._control_relay_at_gateway(endpoint, 'on')
        elif action == 'adb_ctr_off':
            self._control_relay_at_gateway(endpoint, 'off')
        return True, True

    def _control_relay_at_gateway(self, index, on_or_off):

        def _adb_cmd():
            with open(WingtoApi._ADB_KEY) as f:
                priv = f.read()
            with open(WingtoApi._ADB_KEY + '.pub') as f:
                pub = f.read()
            signer = PythonRSASigner(pub, priv)

            ip = getattr(self, self._KEY_IP_ADDRESS, "0.0.0.0")
            port = 5555

            try:
                device = AdbDeviceTcp(ip, port, default_transport_timeout_s=2.)
                device.connect(rsa_keys=[signer], auth_timeout_s=0.1)
            except OSError:
                _LOGGER.error(
                    f"The adb device {ip}:{port} cannot be connected."
                )
                return False

            device.shell(
                f"echo '{1 if on_or_off == 'on' else 0}' "
                f"> /proc/product/relay{index}"
            )
            return True

            #
            # client = ppadb.client.Client()
            # ip = getattr(self, self._KEY_IP_ADDRESS, "0.0.0.0")
            # port = 5555
            # if not client.remote_connect(ip, port):
            #     _LOGGER.error(
            #         f"The adb device {ip}:{port} cannot be connected."
            #     )
            #     return False
            #
            # device = client.device(f"{ip}:{port}")
            # if not device:
            #     _LOGGER.error(
            #         f"Something is error with the adb device {ip}:{port}."
            #     )
            #     return False
            #
            # device.shell(
            #     f"echo '{1 if on_or_off == 'on' else 0}' "
            #     f"> /proc/product/relay{index}"
            # )
            # return True

        async def _async_schedule():
            async with self._adb_lock:
                await asyncio.get_event_loop().run_in_executor(None, _adb_cmd)

        self._add_async_to_mainthread(_async_schedule)

    def broadcast_to_read_all(self):
        # return
        self.device_control(None, None, action="broadcastToReadAll")

    # def refresh_cache(self):
    #     for _, eui64 in self._devices_dict.items():
    #         for _, endpoint in eui64.items():
    #             # if endpoint.get("obj", None):
    #             #     continue
    #             if not (cluster := endpoint.get(0, None)):
    #                 continue
    #             cluster[4], cluster[5] = None, None

    async def change_ip_port(self, ip, port):
        if not (ip and port):
            return

        setattr(self, self._KEY_IP_ADDRESS, ip)
        setattr(self, self._KEY_BROKER_PORT, port)

        await self.mqtt.async_disconnect()
        # del self.mqtt

        self.mqtt = MQTT(ip, port,
                         self._add_async_to_mainthread,
                         self.message_received)

        self._add_async_to_mainthread(self.mqtt.async_connect)

    async def remove_api(self):
        await self.mqtt.async_disconnect()
        type(self)._list_objects.remove(self)
