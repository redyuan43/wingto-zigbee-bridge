from datetime import datetime


class WingtoDevice:

    def __init__(self, data, api):
        self.api = api
        self._obj_id = api.gen_device_id(data[0], data[1][1])
        self._obj_type = data[1][0]
        self._device_mode = data[2][0][1]
        self._obj_name = f"{data[0].lower()}[{data[1][1]}].{self._obj_type}.{self._device_mode}"
        self._eui64 = data[0]
        self._endpoint = data[1][2]
        self._attrs = data[3]
        self._online = True
        self._state = False
        self.support_event = data[2][1][data[1]].get('event', None)
        self.update_entity_state = None
        self._last_update = datetime.min

    @property
    def attrs(self):
        return self._attrs

    def get_eui64(self):
        return self._eui64

    def get_endpoint(self):
        return self._endpoint

    def name(self):
        return self._obj_name

    def state(self):
        state = self._state
        if state is None:
            return None
        elif isinstance(state, str):
            if state == "true":
                return True
            return False
        else:
            return state

    def object_id(self):
        return self._obj_id

    def object_type(self):
        return self._obj_type

    def available(self):
        return self._online

    def _control_device(self, action: object, param: object = None) -> object:
        success, response = self.api.device_control(self.get_eui64(), self.get_endpoint(), action, param)
        if not success:
            self._online = False
        else:
            self._last_update = datetime.now()
        return success

    def update_state(self, st):
        if st is not None:
            old_state = self._state
            self._state = st
            # 记录状态更新
            from datetime import datetime
            self._last_update = datetime.now()
            
            # 触发实体状态更新
            if self.update_entity_state:
                try:
                    self.update_entity_state()
                except Exception as e:
                    # 如果第一次更新失败，稍后重试
                    import logging
                    _LOGGER = logging.getLogger(__name__)
                    _LOGGER.warning("Failed to update entity state for %s, retrying: %s", 
                                  self.object_id(), e)
                    # 使用API的主线程调度器重试
                    if hasattr(self.api, '_add_async_to_mainthread'):
                        self.api._add_async_to_mainthread(self._retry_state_update)
    
    async def _retry_state_update(self):
        """重试状态更新"""
        import asyncio
        await asyncio.sleep(1)  # 等待1秒后重试
        if self.update_entity_state:
            try:
                self.update_entity_state()
            except Exception as e:
                import logging
                _LOGGER = logging.getLogger(__name__)
                _LOGGER.error("Failed to retry state update for %s: %s", self.object_id(), e) 