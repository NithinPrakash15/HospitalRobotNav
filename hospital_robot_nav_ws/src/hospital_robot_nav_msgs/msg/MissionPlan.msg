# Full mission plan (ordered TaskSteps)
string plan_id
string mission_type
string description
TaskStep[] steps
uint8 priority
float32 eta_total_sec
string raw_command
# progress: 0.0–1.0 fraction of completed steps
float32 progress
builtin_interfaces/Time created_at

