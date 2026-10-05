# A single chunk of raw PCM audio (16 kHz, mono, int16)
uint64 sequence
int32 sample_rate
uint8 channels
uint8 sample_width_bytes
float32 rms_energy
bool is_speech
builtin_interfaces/Time stamp
uint8[] data

