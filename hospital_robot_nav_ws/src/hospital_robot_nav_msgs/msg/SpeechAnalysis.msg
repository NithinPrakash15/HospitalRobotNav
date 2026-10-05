# Speech analysis result produced by the speech_analysis_node.
# Aggregates STT confidence, NLU intent, entities, and dialogue state.
string transcript
float32 stt_confidence
string intent_name
float32 intent_confidence
string[] entities_locations
string[] entities_medicines
string entities_room_number
string priority_label
string dialogue_state
string robot_response
string engine
builtin_interfaces/Time stamp

