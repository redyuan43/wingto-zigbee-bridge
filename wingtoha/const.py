GATEWAY_MODE_DEFAULT = 'P1s'

WZB_LOCK_ALARM_DOORBELL = "doorbell went"  # {01 82}
WZB_LOCK_ALARM_FACTORY_RESET = "lock reset to factory defaults"  # {02 83}, 01
WZB_LOCK_ALARM_DEADBOLT_JAMMED = "deadbolt jammed"  # 00
WZB_LOCK_ALARM_POWER_CYCLED = "RF module power cycled"  # 03
WZB_LOCK_ALARM_TAMPER_CODE_LIMIT = "tamper: wrong code entry limit"  # 04
WZB_LOCK_ALARM_TAMPER_REMOVED = "tamper: front escutcheon removed from main"  # 05
WZB_LOCK_ALARM_FORCED_OPEN = "forced door open under door locked condition"  # 06
WZB_LOCK_ALARM_HELD = "be held"  # 0x80
WZB_LOCK_ALARM_NOT_FULLY_LOCKED = "not fully locked"  # 0x81
WZB_LOCK_ALARM_DOOR_OPEN = "door kept open for a too long time"  # 0x82
WZB_LOCK_ALARM_KEY_REMAINED = "forgot to pull out the key"  # 0x83

COL_TYPE_HS = 'hs'
COL_TYPE_XY = 'xy'
