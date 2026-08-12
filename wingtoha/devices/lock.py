import asyncio
import logging

from Crypto.Cipher import AES

from .base import WingtoDevice

_LOGGER = logging.getLogger(__name__)


class WingtoLock(WingtoDevice):
    _task_init = None

    async def unlock(self, kwargs):
        try:
            key = bytes(self.attrs[257][1][0:16])
            cryptor = AES.new(key, AES.MODE_ECB)
            code = kwargs['code']
            if len(code) > 26:
                return
            msg = [len(code)]
            msg.extend([ord(code[byte]) for byte in range(len(code))])
            msg.append(4)
            msg.extend(self.attrs[257][2][-4:])
            pending_len = (16 - (len(msg) % 16)) % 16
            if pending_len > 0:
                msg.extend([pending_len for _ in range(pending_len)])
            msg_encrypt = '0x10' + cryptor.encrypt(bytes(msg)).hex()
            self._control_device("lock", {"value": msg_encrypt})
        except (KeyError, ValueError):
            if self._task_init:
                _LOGGER.info(
                    f'The initialization has been already launched, and try again after 20 seconds.')
                return
            _LOGGER.info(f'Try to initialize the lock info')
            self._task_init = self._get_aes_key_and_rand_num()
            await self._task_init
            await asyncio.sleep(10)
            self._task_init = None

    async def _get_aes_key_and_rand_num(self):
        await asyncio.sleep(10)
        self._control_device("lock_get_random_number")

        await asyncio.sleep(10)
        self._control_device("lock_get_aes_key")

    async def startup_init(self):
        await self._get_aes_key_and_rand_num()
        await asyncio.sleep(10)

        self._control_device("lock_read_state")
        await asyncio.sleep(10)

        self._control_device("local_read_device_battery")
        await asyncio.sleep(10)

        self._control_device("local_read_lock_timeout")

    async def refresh_state(self):
        """刷新设备状态"""
        self._control_device("lock_read_state")
        await asyncio.sleep(2)
        self._control_device("local_read_device_battery")
        await asyncio.sleep(2)
        self._control_device("local_read_lock_timeout")

    def get_timeout_of_auto_lock(self):
        if type(self._attrs) == dict and self._attrs.get(257, {}).get(61441, None) is not None:
            return self._attrs[257][61441]

    def get_lock_last_result(self):
        if type(self._attrs) == dict and self._attrs.get(257, {}).get(10, None) is not None:
            if self._attrs[257][10] == 0:
                return '成功'
            elif self._attrs[257][10] == 1:
                return '操作者密码错误'
            elif self._attrs[257][10] == 0x7E:
                return '没有 AES Key'
            elif self._attrs[257][10] == 0x80:
                return '数据包结构错误'
            elif self._attrs[257][10] == 0x87:
                return '密码不符合规则：密码含无效字符，或密码长度过长'
            elif self._attrs[257][10] == 0x89:
                return '密码表已满'
            elif self._attrs[257][10] == 0x8A:
                return '设置的密码已存在'
            elif self._attrs[257][10] == 0x92:
                return '用户类型不匹配'
            elif self._attrs[257][10] == 0x93:
                return '拒绝密码，操作者权限不够'
            elif self._attrs[257][10] == 0xC2:
                return '随机数校验错误'

    def get_lock_state(self):
        if type(self._attrs) == dict and self._attrs.get(257, {}).get(0, None) is not None:
            if self._attrs[257][0] == 0:
                return '假锁'
            elif self._attrs[257][0] == 1:
                return '关锁'
            elif self._attrs[257][0] == 2:
                return '开锁'
            elif self._attrs[257][0] == 256:
                return '布防'
            elif self._attrs[257][0] == 257:
                return '撤防'
            elif self._attrs[257][0] == 258:
                return '正在开锁'
            elif self._attrs[257][0] == 259:
                return '死闩损坏'

    def get_lock_changed_by(self):
        if type(self._attrs) == dict and self._attrs.get(257, {}).get(11, None) is not None:
            if self._attrs[257][11] == 0:
                return '密码键盘'
            elif self._attrs[257][11] == 1:
                return 'Zigbee 网络'
            elif self._attrs[257][11] == 2:
                return '钥匙'
            elif self._attrs[257][11] == 3:
                return '刷卡'
            elif self._attrs[257][11] == 0xFF:
                return '其他（超时、关锁按键等）'
            elif self._attrs[257][11] == 0xF0:
                return '指纹'

    async def lock_set_auto_lock_time(self, val):
        para = int.to_bytes(val, length=2, byteorder='little')
        self._control_device("lock_set_auto_lock_time", {"value": para.hex()})
        await asyncio.sleep(10)
        self._control_device("local_read_lock_timeout")
