import ctypes
from ctypes import wintypes
import comtypes
from comtypes import client

try:
    # Try importing comtypes to access Windows MMDevice API
    from pycaw.pycaw import AudioUtilities
    print("pycaw found")
except Exception:
    pass

# Direct COM query for default capture device
try:
    import comtypes
    from comtypes import GUID, COMMETHOD, HRESULT, IUnknown
    
    # CLSID and IID for MMDeviceEnumerator
    CLSID_MMDeviceEnumerator = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
    IID_IMMDeviceEnumerator = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
    IID_IAudioEndpointVolume = GUID('{5BC64874-3887-414E-9D81-05600F4963A0}')
    
    class IAudioEndpointVolume(IUnknown):
        _iid_ = IID_IAudioEndpointVolume
        _methods_ = [
            COMMETHOD([], HRESULT, 'RegisterControlChangeNotify'),
            COMMETHOD([], HRESULT, 'UnregisterControlChangeNotify'),
            COMMETHOD([], HRESULT, 'GetChannelCount', (['out'], ctypes.POINTER(wintypes.UINT), 'pnChannelCount')),
            COMMETHOD([], HRESULT, 'SetMasterVolumeLevel'),
            COMMETHOD([], HRESULT, 'SetMasterVolumeLevelScalar', (['in'], ctypes.c_float, 'fLevel'), (['in'], ctypes.c_void_p, 'pguidEventContext')),
            COMMETHOD([], HRESULT, 'GetMasterVolumeLevel'),
            COMMETHOD([], HRESULT, 'GetMasterVolumeLevelScalar', (['out'], ctypes.POINTER(ctypes.c_float), 'pfLevel')),
            COMMETHOD([], HRESULT, 'SetChannelVolumeLevel'),
            COMMETHOD([], HRESULT, 'SetChannelVolumeLevelScalar'),
            COMMETHOD([], HRESULT, 'GetChannelVolumeLevel'),
            COMMETHOD([], HRESULT, 'GetChannelVolumeLevelScalar'),
            COMMETHOD([], HRESULT, 'SetMute', (['in'], wintypes.BOOL, 'bMute'), (['in'], ctypes.c_void_p, 'pguidEventContext')),
            COMMETHOD([], HRESULT, 'GetMute', (['out'], ctypes.POINTER(wintypes.BOOL), 'pbMute')),
            COMMETHOD([], HRESULT, 'GetVolumeStepInfo'),
            COMMETHOD([], HRESULT, 'VolumeStepUp'),
            COMMETHOD([], HRESULT, 'VolumeStepDown'),
            COMMETHOD([], HRESULT, 'QueryHardwareSupport'),
            COMMETHOD([], HRESULT, 'GetVolumeRange'),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'Activate', (['in'], ctypes.POINTER(GUID), 'iid'), (['in'], wintypes.DWORD, 'dwClsCtx'), (['in'], ctypes.c_void_p, 'pActivationParams'), (['out'], ctypes.POINTER(ctypes.c_void_p), 'ppInterface')),
            COMMETHOD([], HRESULT, 'OpenPropertyStore'),
            COMMETHOD([], HRESULT, 'GetId'),
            COMMETHOD([], HRESULT, 'GetState'),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = IID_IMMDeviceEnumerator
        _methods_ = [
            COMMETHOD([], HRESULT, 'EnumAudioEndpoints'),
            COMMETHOD([], HRESULT, 'GetDefaultAudioEndpoint', (['in'], wintypes.INT, 'dataFlow'), (['in'], wintypes.INT, 'role'), (['out'], ctypes.POINTER(ctypes.POINTER(IMMDevice)), 'ppEndpoint')),
            COMMETHOD([], HRESULT, 'GetDevice'),
            COMMETHOD([], HRESULT, 'RegisterEndpointNotificationCallback'),
            COMMETHOD([], HRESULT, 'UnregisterEndpointNotificationCallback'),
        ]

    comtypes.CoInitialize()
    enumerator = comtypes.client.CreateObject(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
    # dataFlow = 1 (eCapture), role = 1 (eMultimedia)
    p_device = enumerator.GetDefaultAudioEndpoint(1, 1)
    
    ptr = p_device.Activate(IID_IAudioEndpointVolume, 1, None)
    vol = ctypes.cast(ptr, ctypes.POINTER(IAudioEndpointVolume))
    
    is_muted = wintypes.BOOL()
    vol.GetMute(ctypes.byref(is_muted))
    level = ctypes.c_float()
    vol.GetMasterVolumeLevelScalar(ctypes.byref(level))
    
    print(f"Windows Default Microphone: Muted={bool(is_muted.value)}, Volume={level.value * 100:.1f}%")
except Exception as e:
    print("COM Query Error:", e)
