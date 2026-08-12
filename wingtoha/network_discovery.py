"""
G2网关网络发现工具
"""
import socket
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

_LOGGER = logging.getLogger(__name__)


class NetworkDiscovery:
    """网络发现类"""
    
    def __init__(self):
        self.timeout = 1
        self.common_networks = [
            "192.168.100",
            "192.168.1", 
            "192.168.0",
            "10.0.0",
            "172.16.0"
        ]
    
    def scan_port(self, ip: str, port: int, timeout: float = None) -> bool:
        """扫描单个IP的指定端口"""
        if timeout is None:
            timeout = self.timeout
            
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception as e:
            _LOGGER.debug("Port scan failed for %s:%d - %s", ip, port, e)
            return False

    async def async_scan_network_for_mqtt(self, network: str = None) -> List[str]:
        """异步扫描网络中的MQTT服务（1883端口）"""
        _LOGGER.info("Scanning network for MQTT services...")
        mqtt_hosts = []
        
        networks_to_scan = [network] if network else self.common_networks
        
        def scan_ip_range(network_prefix):
            hosts = []
            for i in range(1, 255):
                ip = f"{network_prefix}.{i}"
                if self.scan_port(ip, 1883, 0.3):
                    _LOGGER.info("Found MQTT service: %s:1883", ip)
                    hosts.append(ip)
            return hosts
        
        # 使用线程池进行并行扫描
        with ThreadPoolExecutor(max_workers=10) as executor:
            tasks = []
            for network_prefix in networks_to_scan:
                _LOGGER.debug("Scanning %s.0/24 network...", network_prefix)
                task = asyncio.get_event_loop().run_in_executor(
                    executor, scan_ip_range, network_prefix
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            for hosts in results:
                mqtt_hosts.extend(hosts)
        
        return mqtt_hosts

    async def test_mqtt_connection(self, ip: str, port: int = 1883) -> Tuple[bool, Optional[str]]:
        """测试MQTT连接"""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _LOGGER.warning("paho-mqtt not available for connection testing")
            return False, "paho-mqtt not installed"
        
        # 尝试常见认证组合
        auth_combinations = [
            ("admin", "admin"),
            ("root", "root"),
            ("wingto", "wingto"),
            (None, None)  # 无认证
        ]
        
        for username, password in auth_combinations:
            try:
                # 创建客户端
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, f"discovery_{ip}")
                client.connected = False
                client.connection_error = None
                
                def on_connect(client, userdata, flags, rc):
                    if rc == 0:
                        client.connected = True
                        _LOGGER.debug("MQTT connection successful: %s:1883", ip)
                    else:
                        client.connection_error = f"Connection failed with code {rc}"
                
                def on_disconnect(client, userdata, rc):
                    client.connected = False
                
                client.on_connect = on_connect
                client.on_disconnect = on_disconnect
                
                # 设置认证
                if username and password:
                    client.username_pw_set(username, password)
                    _LOGGER.debug("Trying MQTT auth: %s/***", username)
                else:
                    _LOGGER.debug("Trying MQTT without auth")
                
                # 连接测试
                def test_connection():
                    try:
                        client.connect(ip, port, 5)
                        client.loop_start()
                        
                        # 等待连接结果
                        import time
                        for _ in range(20):  # 等待2秒
                            if client.connected or client.connection_error:
                                break
                            time.sleep(0.1)
                        
                        client.loop_stop()
                        client.disconnect()
                        
                        return client.connected
                    except Exception as e:
                        _LOGGER.debug("MQTT connection test failed: %s", e)
                        return False
                
                # 在线程池中执行连接测试
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, test_connection)
                
                if success:
                    auth_info = f"{username}/{password}" if username else "no-auth"
                    _LOGGER.info("Successfully connected to MQTT: %s:1883 (%s)", ip, auth_info)
                    return True, auth_info
                    
            except Exception as e:
                _LOGGER.debug("MQTT connection attempt failed: %s", e)
                continue
        
        return False, "All authentication methods failed"

    async def find_g2_gateway(self, known_ip: str = None) -> Optional[Tuple[str, str]]:
        """查找G2网关"""
        _LOGGER.info("Starting G2 gateway discovery...")
        
        # 1. 首先测试已知IP
        test_ips = []
        if known_ip:
            test_ips.append(known_ip)
        test_ips.extend([
            "192.168.100.241", 
            "192.168.1.241", 
            "192.168.0.241"
        ])
        
        _LOGGER.info("Testing known IP addresses...")
        for ip in test_ips:
            _LOGGER.debug("Testing %s...", ip)
            if self.scan_port(ip, 1883):
                _LOGGER.debug("MQTT port open on %s", ip)
                success, auth_info = await self.test_mqtt_connection(ip)
                if success:
                    _LOGGER.info("Found G2 gateway: %s (auth: %s)", ip, auth_info)
                    return ip, auth_info
            else:
                _LOGGER.debug("No MQTT service on %s", ip)
        
        # 2. 如果已知IP无效，扫描网络
        _LOGGER.info("Known IPs failed, scanning network...")
        
        # 优先扫描192.168.100网段
        mqtt_hosts = await self.async_scan_network_for_mqtt("192.168.100")
        
        # 如果192.168.100网段没找到，扫描其他网段
        if not mqtt_hosts:
            mqtt_hosts = await self.async_scan_network_for_mqtt()
        
        if not mqtt_hosts:
            _LOGGER.warning("No MQTT services found on network")
            return None
        
        _LOGGER.info("Testing discovered MQTT services...")
        for ip in mqtt_hosts:
            success, auth_info = await self.test_mqtt_connection(ip)
            if success:
                _LOGGER.info("Found G2 gateway: %s (auth: %s)", ip, auth_info)
                return ip, auth_info
        
        _LOGGER.warning("No accessible G2 gateway found")
        return None

    def get_local_network_info(self) -> List[str]:
        """获取本地网络信息"""
        networks = []
        try:
            # 获取本地IP地址
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # 提取网络前缀
            ip_parts = local_ip.split('.')
            if len(ip_parts) >= 3:
                network_prefix = '.'.join(ip_parts[:3])
                networks.append(network_prefix)
                _LOGGER.debug("Local network detected: %s.0/24", network_prefix)
        except Exception as e:
            _LOGGER.debug("Failed to detect local network: %s", e)
        
        return networks


# 全局实例
network_discovery = NetworkDiscovery() 