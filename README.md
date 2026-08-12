# Wingto Zigbee Bridge

Home Assistant custom integration for local WingTo G2 Zigbee gateways.

This repository contains the verified local-control fix for the HH01_64 VRV
air-conditioning controller used by this installation.

## What Is Included

- Local MQTT communication with the WingTo G2 gateway.
- VRV room control for living room, multi-function room, children's room, and
  master bedroom.
- Controller ACK verification: Home Assistant only reports a command as
  successful after the Zigbee controller replies.
- MQTT reconnect handling after Home Assistant, G2, or network restarts.
- State synchronization from controller reports, including room power and
  target temperature changes made through the vendor app or physical panel.

## Installation

1. Copy this repository directory to:

   ```text
   /config/custom_components/wingto_zigbee_bridge
   ```

2. Restart Home Assistant.
3. Configure the WingTo G2 integration with the gateway IP and MQTT port.

Do not commit Home Assistant credentials, G2 root passwords, tokens, or SSH
keys to this repository.

## VRV Configuration

The deployment-specific settings are in `vrv2_config.py`.

| Setting | Purpose |
| --- | --- |
| `VRV2_GATEWAY_CONFIG["ip"]` | G2 gateway LAN IP |
| `VRV2_GATEWAY_CONFIG["eui64"]` | G2 Zigbee EUI64 |
| `VRV2_DEVICE_CONFIG["device_mac"]` | VRV controller Zigbee EUI64 |
| `VRV2_DEVICE_CONFIG["dest_addr"]` | Current VRV Zigbee short address |

The controller currently uses the manufacturer cluster `0xFF00`, manufacturer
code `0x117B`, and G2 MQTT topic:

```text
gw/<G2_EUI64>/commadzgm
```

The topic spelling is intentionally `commadzgm`; it is the G2 firmware's
native command topic.

## After A Controller Rejoins

Zigbee short addresses can change after a controller is removed and rejoined.
When commands time out with `No Zigbee ACK from the VRV controller`, retrieve
the current address from the G2:

```sh
sqlite3 /etc/rici-zigbee.db \
  "select nodeid from devicenode where upper(mac)='VRV_CONTROLLER_EUI64';"
```

Update `VRV2_DEVICE_CONFIG["dest_addr"]` with that decimal `nodeid`, then
restart Home Assistant.

## Verification Checklist

1. Use Home Assistant to turn a room on or off.
2. Confirm the climate entity has no `last_command_error`.
3. Change a room's power or target temperature in the vendor app.
4. Confirm Home Assistant updates after the controller's next Zigbee report.
5. Check all four rooms after a G2 or Home Assistant restart.

## Room Mapping

| VRV Channel | Display Name | Existing Entity ID |
| --- | --- | --- |
| 1 | 客厅 | `climate.vrv2_zhu_wo` |
| 2 | 多功能房 | `climate.vrv2_duo_gong_neng_fang` |
| 3 | 儿童房 | `climate.vrv2_er_tong_fang` |
| 4 | 主卧 | `climate.vrv2_ke_ting` |

The display names are correct. Two entity IDs are historical and should not be
renamed without checking existing automations.

## Backups

Before changing the deployed integration, create a compressed backup outside
`custom_components`, for example:

```sh
tar -C /config/custom_components -czf \
  /config/backup/wingto-zigbee-bridge-backup.tgz \
  wingto_zigbee_bridge
```

