#!/usr/bin/env bash
# Inspect the most recent speech smoke-test output files.
echo "=== /robot/speech_analysis (key fields) ==="
grep -E "transcript:|intent_name:|intent_confidence:|entities_medicines:|entities_locations:|entities_room_number:|dialogue_state:|robot_response:|engine:" /tmp/smoke_analysis_out.txt 2>/dev/null | head -60

echo ""
echo "=== /robot/say ==="
cat /tmp/smoke_say_out.txt 2>/dev/null | head -10

echo ""
echo "=== pipeline launch log (tail) ==="
tail -25 /tmp/smoke_pipeline.log 2>/dev/null

