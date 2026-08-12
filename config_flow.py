"""Config flow for Wingto."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PLATFORM,
)
from homeassistant.core import callback
from .const import (
    DOMAIN,
    WINGTO_API,
    CONF_BROKER_PORT,
    CONF_GATEWAY_MODEL,
    CONF_AUTO_CONFIG,
    CONF_IP_RANGE,
)
from .wingtoha.gateway import GatewayInfoGetter

_LOGGER = logging.getLogger(__name__)

CONF_LIST_DEVICES = "list_devices"

ERROR_DEV_MULTI_TYPE = "dev_multi_type"
ERROR_DEV_NOT_CONFIG = "dev_not_config"
ERROR_DEV_NOT_FOUND = "dev_not_found"

RESULT_AUTH_FAILED = "invalid_auth"
RESULT_CONN_ERROR = "cannot_connect"
RESULT_SINGLE_INSTANCE = "single_instance_allowed"
RESULT_SUCCESS = "success"

RESULT_LOG_MESSAGE = {
    RESULT_AUTH_FAILED: "Invalid credential",
    RESULT_CONN_ERROR: "Connection error",
}

CONFIG_OPTIONS = "config_options"


def _get_user_schema(model="G2", ip="192.168.0.113", port=1883, schema=None):
    common_schema = {
        vol.Required(CONF_GATEWAY_MODEL, default=model): vol.In(('G2', 'P1s', 'P3', 'P6s', 'P6box')),
        vol.Required(CONF_IP_ADDRESS, default=ip): str,
        vol.Required(CONF_BROKER_PORT, default=port): int,
    }
    if schema:
        return vol.Schema({**schema, **common_schema})
    else:
        return vol.Schema(common_schema)


def _get_config_entry_title(model, ip, port):
    return f"{model} ({ip}:{str(port)})"


class WingtoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    AsyncLock = asyncio.Lock()

    def __init__(self) -> None:
        """Initialize flow."""
        self._gateway_model = None
        self._ip_address = None
        self._broker_port = None
        self._platform = 'wingto'

        self._autoconfigure_show_form = None

    async def async_step_user(self, user_input=None):
        if user_input is None:
            my_ip = await asyncio.get_running_loop().run_in_executor(
                None, FlowHelper.get_host_ip)

            if not (ip_prefix := my_ip[0:my_ip.rfind(r'.') + 1]):
                ip_prefix = "192.168.0."
            self._autoconfigure_show_form = self.async_show_form(
                step_id="user", data_schema=vol.Schema(
                    {
                        vol.Required(CONF_IP_RANGE,
                                     default=f"{ip_prefix}1 ~ {ip_prefix}254"
                                     ): str,
                        vol.Required(CONF_AUTO_CONFIG,
                                     default=1
                                     ): cv.boolean
                    }
                )
            )
            return self._autoconfigure_show_form

        if user_input.get(CONF_AUTO_CONFIG, False) is False:
            return await self.async_step_manualconfigure()

        ip_range = user_input.get(CONF_IP_RANGE, None)

        ip_set = set()
        try:
            for v in ip_range.split(r','):
                idx = v.find(r'~')
                if idx == -1:
                    if (v := v.strip()) == '':
                        continue
                    ip_set.add(ipaddress.ip_address(v))
                    continue
                head = ipaddress.ip_address(v[0:idx].strip())
                tail = ipaddress.ip_address(v[idx + 1:].strip())
                while head <= tail:
                    ip_set.add(head)
                    head = head + 1
        except ValueError:
            if self._autoconfigure_show_form:
                return self._autoconfigure_show_form
            else:
                return self.async_abort("something error")

        ip_set = {str(v) for v in ip_set}

        # 将大量 IP 地址通过线程池先经过一定规则的过滤，然后再精细判断类型
        # 默认的线程池没有这么大容量
        executor = ThreadPoolExecutor(128)
        ip_set, _ = await FlowHelper.async_group_ips(executor, ip_set, 1883, 1)  # 1883 端口有服务 (MQTT)
        ip_adb, ip_g2 = await FlowHelper.async_group_ips(executor, ip_set, 5555, 1)
        ip_g2, _ = await FlowHelper.async_group_ips(executor, ip_g2, 22, 1)
        # ip_set = {*ip_ssh, *ip_adb}  # 22 端口有服务 (SSH@G2)，或者 5555 端口有服务 (ADB@Px)
        # ip_set, _ = await FlowHelper.async_group_ips(executor, ip_set, 3306, 1)  # 3306 端口有服务 (MySQL)
        # 回收线程池资源
        executor.shutdown()

        tasks, port = list(), 1883
        for ip in ip_g2:
            tasks.append(self.async_helper_autoconfigure(
                ip, port, GatewayInfoGetter(ip, port, False).get_device_eui64_and_type()
            ))
        for ip in ip_adb:
            # port = 1883 if ip != '192.168.0.99' else 62883  # 测试使用
            tasks.append(self.async_helper_autoconfigure(
                ip, port, GatewayInfoGetter(ip, port, True).get_device_eui64_and_type()
            ))
        await asyncio.gather(*tasks)

        return await self.async_step_finish()

    async def async_helper_autoconfigure(self, ip, port, coro_get_gw_info):

        eui64, model = await coro_get_gw_info
        if not (ip and port):
            return
        if not (eui64 and model):
            return
        # if model not in ('G2', 'P1s', 'P3'):
        #     model = 'G2'
        eui64 = eui64.upper()

        async with WingtoConfigFlow.AsyncLock:
            for entry in self.hass.config_entries.async_entries():
                if entry.unique_id == eui64:
                    # 按需更新
                    await self.async_helper_autoconfigure_update(model, ip, port, entry)
                    return

            # 没有找到该设备，新添加设备
            entry_data = {
                CONF_GATEWAY_MODEL: model,
                CONF_IP_ADDRESS: ip,
                CONF_BROKER_PORT: port,
                CONF_PLATFORM: self._platform,
            }
            
            # 使用 ConfigEntries.async_add 方法添加条目
            from homeassistant.config_entries import ConfigEntry
            await self.hass.config_entries.async_add(ConfigEntry(
                version=1,
                minor_version=1,
                domain=DOMAIN,
                title=_get_config_entry_title(model, ip, port),
                data=entry_data,
                options={},
                source="automatic",
                unique_id=eui64,
                discovery_keys=set(),
                subentries_data={}
            ))

    async def async_helper_autoconfigure_update(self, model, ip_address, broker_port,
                                                entry: config_entries.ConfigEntry):
        old = [entry.data.get(CONF_GATEWAY_MODEL, None),
               entry.data.get(CONF_IP_ADDRESS, None),
               entry.data.get(CONF_BROKER_PORT, None)
               ]
        if old == [model, ip_address, broker_port]:
            return

        if _get_config_entry_title(*old) == entry.title:
            title = _get_config_entry_title(model, ip_address, broker_port)
        else:
            title = entry.title

        self.hass.config_entries.async_update_entry(
            entry,
            title=title,
            data={
                CONF_GATEWAY_MODEL: model,
                CONF_IP_ADDRESS: ip_address,
                CONF_BROKER_PORT: broker_port,
                CONF_PLATFORM: self._platform,
            },
        )
        domain_data = self.hass.data[DOMAIN][entry.entry_id]
        if old[1:] != [ip_address, broker_port]:
            await domain_data[WINGTO_API].change_ip_port(ip_address, broker_port)
        if old[0] != model:
            await domain_data[WINGTO_API].change_model(model)

    async def async_step_manualconfigure(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}
        if user_input is not None:
            for entry in self._async_current_entries():
                if entry.data.get(CONF_IP_ADDRESS, "0.0.0.0") == user_input.get(CONF_IP_ADDRESS, "") \
                        and entry.data.get(CONF_BROKER_PORT, 1883) == user_input.get(CONF_BROKER_PORT, 0):
                    return self.async_abort(reason=RESULT_SINGLE_INSTANCE)

            # self._platform = 'wingto'
            self._gateway_model = user_input[CONF_GATEWAY_MODEL]
            self._ip_address = _v if FlowHelper.check_ip((_v := user_input[CONF_IP_ADDRESS])) else None
            self._broker_port = _v if FlowHelper.check_port((_v := user_input[CONF_BROKER_PORT])) else None

            if not (self._ip_address and self._broker_port):
                return self.async_show_form(
                    step_id="manualconfigure",
                    data_schema=_get_user_schema(
                        self._gateway_model, self._ip_address, self._broker_port
                    )
                )

            eui64, _ = await GatewayInfoGetter(self._ip_address, self._broker_port, False
                                               ).get_device_eui64_and_type()
            result = RESULT_SUCCESS if eui64 else RESULT_CONN_ERROR

            if result == RESULT_SUCCESS:
                async with WingtoConfigFlow.AsyncLock:
                    for entry in self.hass.config_entries.async_entries():
                        if entry.unique_id == eui64:
                            # 按需更新
                            await self.async_helper_autoconfigure_update(
                                self._gateway_model, self._ip_address, self._broker_port,
                                entry
                            )
                            return await self.async_step_finish()

                    await self.async_set_unique_id(eui64)
                    return self.async_create_entry(
                        title=_get_config_entry_title(self._gateway_model, self._ip_address, self._broker_port),
                        data={
                            CONF_GATEWAY_MODEL: self._gateway_model,
                            CONF_IP_ADDRESS: self._ip_address,
                            CONF_BROKER_PORT: self._broker_port,
                            CONF_PLATFORM: self._platform,
                        },
                    )
            if result != RESULT_AUTH_FAILED:
                return self.async_abort(reason=result)
            errors["base"] = result

        return self.async_show_form(
            step_id="manualconfigure",
            data_schema=_get_user_schema(),
            errors=errors
        )

    async def async_step_finish(self, user_input=None):
        """
        finish the auto configuration step
        """
        # return self.async_show_form(
        #     step_id="finish",
        #     data_schema=vol.Schema({
        #     })
        # )

        if user_input:
            pass
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema({
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Wingto."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._conf_devs_id = None
        self._conf_devs_option: dict[str, Any] = {}
        self._form_error = None
        # self._progress_action = None

    def _get_form_error(self):
        """Set the error to be shown in the options form."""
        errors = {}
        if self._form_error:
            errors["base"] = self._form_error
            self._form_error = None
        return errors

    async def _async_do_task(self, task):

        if task:
            await task
        self.hass.async_create_task(
            self.hass.config_entries.options.async_configure(flow_id=self.flow_id)
        )

    async def async_step_init(self, user_input=None):
        """Handle options flow."""

        if self.config_entry.state is not config_entries.ConfigEntryState.LOADED:
            _LOGGER.error("Wingto Zigbee Bridge integration not yet loaded")
            return self.async_abort(reason=RESULT_CONN_ERROR)

        def _opt_0():
            option = r'--- SELECT & CLICK "SUBMIT" ---'
            return option, lambda: True

        def _opt_1():
            option = "discovery new devices (with a broadcast)"

            def _f():
                domain_data[WINGTO_API].broadcast_to_read_all()
                return True

            return option, _f

        # def _opt_2():
        #     option = "refresh cache and re-discovery devices (with a broadcast)"
        #
        #     def _f():
        #         domain_data[WINGTO_API].refresh_cache()
        #         domain_data[WINGTO_API].broadcast_to_read_all()
        #         return True
        #
        #     return option, _f

        def _opt_3():
            option = "refresh cache and discovery a device"
            return option, lambda: False

        def _opt_4():
            option = "change model, IP or port"
            return option, self.async_step_ip_port

        config_options = {
            opt[0]: opt[1] for opt_generator in (
                _opt_0, _opt_1,
                # _opt_2,
                _opt_3, _opt_4)
            if type(opt := opt_generator()) is tuple}

        if user_input is not None:
            domain_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
            if (opt := config_options.get(user_input.get(CONFIG_OPTIONS), None)) and (f := opt()):
                if asyncio.iscoroutine(f):
                    return await f

                # self._progress_action = self.hass.async_create_task(
                #     self._async_do_task(
                #         asyncio.sleep(0)
                #     )
                # )
                return await self.async_step_finish()
                # return self.async_show_progress(
                #     step_id="init",
                #     progress_action="init"
                # )
            return self.async_abort(reason="not_supported")

        # if self._progress_action:
        #     return self.async_show_progress_done(
        #         next_step_id="finish"
        #     )

        data_schema = vol.Schema({})
        data_schema = data_schema.extend(
            {
                vol.Optional(
                    CONFIG_OPTIONS, default=list(config_options.keys())[0],
                ): vol.In(config_options.keys()),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=self._get_form_error(),
        )

    async def async_step_device(self, user_input=None):
        """Handle options flow for device."""
        if user_input is None:
            data_schema = vol.Schema({})
            data_schema = data_schema.extend(
                {
                    vol.Optional(
                        "min_temp", default=179,
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=65535)),
                }
            )
            return self.async_show_form(
                step_id="device",
                data_schema=data_schema
            )
        return await self.async_step_init()

    async def async_step_ip_port(self, user_input=None):
        """Handle options flow for device."""

        entry = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        old = [entry.data[k] for k in (CONF_GATEWAY_MODEL, CONF_IP_ADDRESS, CONF_BROKER_PORT)]

        if user_input is None:
            return self.async_show_form(
                step_id="ip_port",
                data_schema=_get_user_schema(*old)
            )

        model = user_input[CONF_GATEWAY_MODEL]
        ip_address = _v if FlowHelper.check_ip((_v := user_input[CONF_IP_ADDRESS])) else None
        broker_port = _v if FlowHelper.check_port((_v := user_input[CONF_BROKER_PORT])) else None

        if not (ip_address and broker_port):
            return self.async_show_form(
                step_id="ip_port",
                data_schema=_get_user_schema(
                    model, ip_address, broker_port
                ))

        if old != [model, ip_address, broker_port]:

            if _get_config_entry_title(*old) == entry.title:
                title = _get_config_entry_title(model, ip_address, broker_port)
            else:
                title = entry.title

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=title,
                data={
                    CONF_GATEWAY_MODEL: model,
                    CONF_IP_ADDRESS: ip_address,
                    CONF_BROKER_PORT: broker_port,
                    CONF_PLATFORM: entry.data[CONF_PLATFORM],
                },
            )
            if old[1:] != [ip_address, broker_port]:
                domain_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
                await domain_data[WINGTO_API].change_ip_port(ip_address, broker_port)
            if old[0] != model:
                domain_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
                await domain_data[WINGTO_API].change_model(model)
        else:
            return self.async_abort(reason="no_change")

        return await self.async_step_finish()

    async def async_step_finish(self, user_input=None):
        if user_input:
            pass
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema({
            })
        )


class FlowHelper:

    @staticmethod
    def check_port(port: int):
        if port < 1 or port > 65535:
            return False
        return True

    @staticmethod
    def check_ip(ip: str):
        try:
            socket.inet_pton(socket.AF_INET, ip)
        except socket.error:
            try:
                socket.inet_pton(socket.AF_INET6, ip)
            except socket.error:
                return False
        return True

    @staticmethod
    def get_host_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('223.6.6.6', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip

    @staticmethod
    def check_tcp_port(ip="127.0.0.1", port=5555, times=1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        for _ in range(times):
            if 0 != sock.connect_ex((ip, port)):
                continue
            sock.close()
            return True
        return False

    @staticmethod
    async def async_group_ips(exe, ips, port, times=1):
        tasks = dict()
        for ip in ips:
            tasks[ip] = asyncio.get_running_loop().run_in_executor(
                exe, FlowHelper.check_tcp_port, ip, port, times)

        ip_valid, ip_invalid = set(), set()
        for ip, t in tasks.items():
            if await t:
                ip_valid.add(ip)
            else:
                ip_invalid.add(ip)
        return ip_valid, ip_invalid

# class DevGetGwInfo:
#     def __init__(self, ip, broker_port=1883):
#         self.ip = ip
#         self.broker_port = broker_port
#
#     async def async_get_gw_info(self):
#         if self.ip:
#             pass
#
#         await asyncio.sleep(1)
#         eui64 = self.ip
#         if self.ip == '192.168.0.99':
#             return [eui64, 'P1s']
#         if self.ip == '192.168.0.108':
#             return [None, None]
#         return [eui64, 'G2']
