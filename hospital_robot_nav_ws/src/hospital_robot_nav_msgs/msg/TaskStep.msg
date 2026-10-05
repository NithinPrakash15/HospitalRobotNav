# Atomic task step in a mission plan
# task_type enum:
#   0 = NAVIGATE
#   1 = COLLECT
#   2 = DELIVER
#   3 = WAIT
#   4 = INTERACT
#   5 = ESCORT
#   6 = ALERT
#   7 = RETURN_TO_DOCK
#   8 = CHARGE
uint8 task_type
string step_id
string description
string destination
GridPos destination_pos
string item
float32 duration_sec
# status enum: 0=PENDING 1=IN_PROGRESS 2=COMPLETED 3=FAILED 4=SKIPPED
uint8 status
string metadata_json

