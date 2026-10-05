# Structured mission request from NLU / command resolver
# mission_type enum:
#   0=MEDICINE_DELIVERY 1=GUIDE_PATIENT 2=CALL_NURSE 3=EMERGENCY_RESPONSE
#   4=DELIVER_REPORT 5=TRANSPORT_SAMPLE 6=FETCH_WHEELCHAIR
#   7=ESCORT_VISITOR 8=NAVIGATE 9=RETURN_TO_DOCK
uint8 mission_type
string mission_type_name
string pickup_location
string delivery_location
string item
uint8 quantity
uint8 priority
string priority_label
string patient_name
string raw_text
string intent_name
float32 intent_confidence
string[] locations
string[] medicines
string room_number
GridPos resolved_pickup
GridPos resolved_delivery
bool is_valid
string validation_error
builtin_interfaces/Time stamp

