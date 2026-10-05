# Agent fleet status / heartbeat
string agent_id
string agent_type
# state enum: 0=IDLE 1=BIDDING 2=ASSIGNED 3=EXECUTING 4=RETURNING
#             5=CHARGING 6=ERROR 7=OFFLINE
uint8 state
GridPos position
float32 battery_pct
string current_mission_id
string[] capabilities
builtin_interfaces/Time timestamp

