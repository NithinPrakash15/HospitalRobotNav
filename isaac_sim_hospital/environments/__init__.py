"""Hospital environment package for Isaac Sim."""

try:
    from .hospital_env import HospitalEnvironment
except ImportError:
    try:
        from environments.hospital_env import HospitalEnvironment
    except ImportError:
        HospitalEnvironment = None

try:
    from .bilingual_voice import BilingualVoiceEngine, ClinicalAnnouncement, CLINICAL_VOICE_DATABASE
except ImportError:
    try:
        from environments.bilingual_voice import BilingualVoiceEngine, ClinicalAnnouncement, CLINICAL_VOICE_DATABASE
    except ImportError:
        BilingualVoiceEngine = ClinicalAnnouncement = CLINICAL_VOICE_DATABASE = None

try:
    from .hospital_furniture import HospitalFurniture
except ImportError:
    try:
        from environments.hospital_furniture import HospitalFurniture
    except ImportError:
        HospitalFurniture = None

try:
    from .arogya_control_window import ArogyaControlWindow
except ImportError:
    try:
        from environments.arogya_control_window import ArogyaControlWindow
    except ImportError:
        ArogyaControlWindow = None

__all__ = [
    "HospitalEnvironment",
    "HospitalFurniture",
    "ArogyaControlWindow",
    "BilingualVoiceEngine",
    "ClinicalAnnouncement",
    "CLINICAL_VOICE_DATABASE",
]

