"""Intégration Win32 : raccourci clavier global, premier plan, démarrage automatique.

Tout est protégé par `IS_WINDOWS` pour que l'application reste testable ailleurs.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MAPVK_VSC_TO_VK = 1
HOTKEY_ID = 0x5150  # « QP »


def resolve_vk(spec: dict) -> int:
    """Renvoie le code de touche virtuelle, à partir du scan code si besoin
    (indépendant de la disposition AZERTY/QWERTY)."""
    vk = int(spec.get("vk") or 0)
    if vk:
        return vk
    sc = int(spec.get("scancode") or 0)
    if IS_WINDOWS and sc:
        return int(user32.MapVirtualKeyW(sc, MAPVK_VSC_TO_VK))
    return 0


def _event_type(et) -> bytes:
    if isinstance(et, bytes):
        return et
    if isinstance(et, str):
        return et.encode()
    try:
        return bytes(et.data())
    except AttributeError:
        return bytes(et)


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API Qt)
        if _event_type(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    """Raccourci global système via RegisterHotKey."""

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._registered = False
        self._filter = None
        if IS_WINDOWS:
            self._filter = _NativeFilter(self.activated.emit)
            QCoreApplication.instance().installNativeEventFilter(self._filter)

    def register(self, spec: dict) -> tuple[bool, str]:
        self.unregister()
        if not IS_WINDOWS:
            return False, "Raccourci global disponible uniquement sous Windows."
        vk = resolve_vk(spec)
        if not vk:
            return False, "Touche du raccourci invalide."
        mods = MOD_NOREPEAT
        mods |= MOD_CONTROL if spec.get("ctrl") else 0
        mods |= MOD_ALT if spec.get("alt") else 0
        mods |= MOD_SHIFT if spec.get("shift") else 0
        mods |= MOD_WIN if spec.get("win") else 0
        if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
            err = ctypes.get_last_error()
            return False, (
                f"Le raccourci {spec.get('label', '?')} est déjà utilisé par une autre "
                f"application (erreur Win32 {err})."
            )
        self._registered = True
        return True, ""

    def unregister(self) -> None:
        if IS_WINDOWS and self._registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        self._registered = False


def force_foreground(hwnd: int) -> None:
    """Passe la fenêtre au premier plan malgré les restrictions de Windows."""
    if not IS_WINDOWS:
        return
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur_tid = kernel32.GetCurrentThreadId()
    attached = False
    if fg and fg_tid != cur_tid:
        attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(fg_tid, cur_tid, False)


HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10


def set_topmost(hwnd: int, on: bool, activate: bool = False) -> None:
    """Active/désactive « toujours au premier plan » (SetWindowPos)."""
    if not IS_WINDOWS or not hwnd:
        return
    flags = SWP_NOSIZE | SWP_NOMOVE | (0 if activate else SWP_NOACTIVATE)
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST),
                        0, 0, 0, 0, flags)


def set_app_user_model_id(app_id: str) -> None:
    if IS_WINDOWS:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except (AttributeError, OSError):
            pass


# --- Démarrage avec Windows (HKCU\...\Run, pas de droits admin requis) -------
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "QuakePad"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "run_quakepad.py"
    return f'"{exe}" "{script}" --hidden'


def set_start_with_windows(enabled: bool) -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# --- Chiffrement des secrets (DPAPI : lié au compte Windows de l'utilisateur) ---------
_DPAPI_PREFIX = "dpapi:"


def protect(value: str) -> str:
    if not value or not IS_WINDOWS:
        return value
    import base64

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    raw = value.encode("utf-8")
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        return value
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return _DPAPI_PREFIX + base64.b64encode(data).decode("ascii")


def unprotect(value: str) -> str:
    if not value or not value.startswith(_DPAPI_PREFIX):
        return value or ""
    if not IS_WINDOWS:
        return ""
    import base64

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    raw = base64.b64decode(value[len(_DPAPI_PREFIX):])
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        return ""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(blob_out.pbData)
