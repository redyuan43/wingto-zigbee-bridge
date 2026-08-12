"""
VRV2空调系统配置文件
用于管理所有硬编码的参数和设置
"""

# VRV2网关配置
VRV2_GATEWAY_CONFIG = {
    "ip": "192.168.100.193",
    "eui64": "5C0272FFFED495F6",
    "mqtt_port": 1883,
    "connection_timeout": 60,
    "publish_timeout": 0.1  # MQTT发布后等待时间(秒)
}

# VRV2设备配置
VRV2_DEVICE_CONFIG = {
    "device_mac": "04CD15FFFE074ED6",  # VRV2 Zigbee device EUI64
    "dest_addr": 14375,         # Current VRV2 Zigbee short address (0x3827)
    "src_endpoint": 1,          # 源端点
    "dest_endpoint": 1,         # 目标端点
    "cluster_id": 65280,        # 集群ID (0xFF00)
    "zcl_fc": 17,              # ZCL框架控制
    "zcl_mfg_id": 4475,        # 制造商ID (0x117B)
    "zcl_cmd": 16,             # ZCL命令
    "zcl_buf_len": 14          # ZCL缓冲区长度
}

# VRV2房间配置
VRV2_ROOM_CONFIG = {
    1: {
        "name": "客厅",
        "room_code": "01",
        "sn_offset": 0  # SN = 201 + offset * 10
    },
    2: {
        "name": "多功能房",
        "room_code": "02",
        "sn_offset": 1
    },
    3: {
        "name": "儿童房",
        "room_code": "03",
        "sn_offset": 2
    },
    4: {
        "name": "主卧",
        "room_code": "04",
        "sn_offset": 3
    }
}

# VRV2控制命令配置
VRV2_COMMAND_CONFIG = {
    # 电源控制命令
    "power": {
        "on": "020001000000",
        "off": "020000000000"
    },

    # 温度控制命令
    "temperature": {
        "command_prefix": "040000",
        "command_suffix": "0000",
        "min_temp": 16,
        "max_temp": 30
    },

    # 风量控制命令
    "fan": {
        "command_prefix": "08000000",
        "fan_codes": {
            "low": "1000",      # 小风
            "medium": "3000",   # 中风
            "high": "5000",     # 大风
            "auto": "1000"      # 自动(默认小风)
        }
    }
}

# VRV2 MQTT主题配置
VRV2_MQTT_CONFIG = {
    "topic_template": "gw/{eui64}/commadzgm",
    "base_sn": 201  # 基础SN，每个房间递增10
}

# Home Assistant实体配置
VRV2_ENTITY_CONFIG = {
    "unique_id_template": "vrv2_climate_{control_sn}",
    "name_template": "VRV2 {room_name}",
    "device_name_template": "VRV2 {room_name}",
    "manufacturer": "WingTo",
    "model": "VRV2",
    "via_device": "vrv2_system"
}

# 支持的HVAC模式和风扇模式
VRV2_SUPPORTED_MODES = {
    "hvac_modes": ["off", "auto", "cool", "heat"],
    "fan_modes": ["auto", "low", "medium", "high"]
}

def get_room_config(control_sn):
    """根据control_sn获取房间配置"""
    return VRV2_ROOM_CONFIG.get(control_sn)

def get_room_code(control_sn):
    """获取房间控制码"""
    room_config = get_room_config(control_sn)
    return room_config["room_code"] if room_config else "04"

def get_room_name(control_sn):
    """获取房间名称"""
    room_config = get_room_config(control_sn)
    return room_config["name"] if room_config else f"房间{control_sn}"

def get_sn_for_room(control_sn):
    """获取房间的SN号"""
    room_config = get_room_config(control_sn)
    if room_config:
        return VRV2_MQTT_CONFIG["base_sn"] + room_config["sn_offset"] * 10
    return VRV2_MQTT_CONFIG["base_sn"]

def build_power_command(control_sn, turn_on=True):
    """构建电源控制命令"""
    room_code = get_room_code(control_sn)
    command = VRV2_COMMAND_CONFIG["power"]["on" if turn_on else "off"]
    return f"{room_code}{command}"

def build_temperature_command(control_sn, temperature):
    """构建温度控制命令"""
    room_code = get_room_code(control_sn)
    hex_temp = f"{temperature:02x}"
    prefix = VRV2_COMMAND_CONFIG["temperature"]["command_prefix"]
    suffix = VRV2_COMMAND_CONFIG["temperature"]["command_suffix"]
    return f"{room_code}{prefix}{hex_temp}{suffix}"

def build_fan_command(control_sn, fan_mode):
    """构建风量控制命令"""
    room_code = get_room_code(control_sn)
    prefix = VRV2_COMMAND_CONFIG["fan"]["command_prefix"]
    fan_code = VRV2_COMMAND_CONFIG["fan"]["fan_codes"].get(fan_mode, "1000")
    return f"{room_code}{prefix}{fan_code}"

def get_mqtt_topic():
    """获取MQTT主题"""
    template = VRV2_MQTT_CONFIG["topic_template"]
    return template.format(eui64=VRV2_GATEWAY_CONFIG["eui64"])

def build_mqtt_message(control_sn, zclbuf):
    """构建完整的MQTT消息"""
    return {
        "cmdtype": "zcl",
        "addrmode": 1,
        "destaddr": VRV2_DEVICE_CONFIG["dest_addr"],
        "srcendpoint": VRV2_DEVICE_CONFIG["src_endpoint"],
        "destendpoint": VRV2_DEVICE_CONFIG["dest_endpoint"],
        "clusterid": VRV2_DEVICE_CONFIG["cluster_id"],
        "zclfc": VRV2_DEVICE_CONFIG["zcl_fc"],
        "sn": get_sn_for_room(control_sn),
        "zclmfgid": VRV2_DEVICE_CONFIG["zcl_mfg_id"],
        "zclcmd": VRV2_DEVICE_CONFIG["zcl_cmd"],
        "zclbuflen": VRV2_DEVICE_CONFIG["zcl_buf_len"],
        "zclbuf": zclbuf
    }
