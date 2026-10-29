"""전역 단축키 (RegisterHotKey + Qt 네이티브 이벤트 필터).

Print Screen 은 Windows 가 RegisterHotKey 보다 먼저 처리해 WM_HOTKEY 가 오지 않으므로
저수준 키보드 훅(WH_KEYBOARD_LL)으로 가로챈다.
"""
import ctypes
import threading
from ctypes import wintypes as wt

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from . import winapi

_SPECIAL = {
    Qt.Key.Key_Print: 0x2C, Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Home: 0x24,
    Qt.Key.Key_End: 0x23, Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22, Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_Space: 0x20, Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26, Qt.Key.Key_Right: 0x27,
    Qt.Key.Key_Down: 0x28, Qt.Key.Key_ScrollLock: 0x91, Qt.Key.Key_Minus: 0xBD, Qt.Key.Key_Equal: 0xBB,
    Qt.Key.Key_Comma: 0xBC, Qt.Key.Key_Period: 0xBE, Qt.Key.Key_Slash: 0xBF, Qt.Key.Key_Semicolon: 0xBA,
    Qt.Key.Key_BracketLeft: 0xDB, Qt.Key.Key_BracketRight: 0xDD, Qt.Key.Key_Backslash: 0xDC,
    Qt.Key.Key_Apostrophe: 0xDE, Qt.Key.Key_QuoteLeft: 0xC0,
}


def seq_to_win(seq):
    """'Ctrl+Shift+C' -> (modifiers, vk) | None"""
    if not seq:
        return None
    ks = QKeySequence(seq, QKeySequence.SequenceFormat.PortableText)
    if ks.isEmpty():
        return None
    comb = ks[0]
    key = comb.key()
    k = key.value if hasattr(key, "value") else int(key)
    mods = comb.keyboardModifiers()
    if 0x41 <= k <= 0x5A or 0x30 <= k <= 0x39:
        vk = k
    elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F24.value:
        vk = 0x70 + (k - Qt.Key.Key_F1.value)
    else:
        vk = _SPECIAL.get(key)
        if vk is None:
            return None
    m = 0
    if mods & Qt.KeyboardModifier.ControlModifier:
        m |= winapi.MOD_CONTROL
    if mods & Qt.KeyboardModifier.ShiftModifier:
        m |= winapi.MOD_SHIFT
    if mods & Qt.KeyboardModifier.AltModifier:
        m |= winapi.MOD_ALT
    if mods & Qt.KeyboardModifier.MetaModifier:
        m |= winapi.MOD_WIN
    return m, vk


VK_SNAPSHOT = 0x2C
_ESC_ID = 0x7F00  # 캡처 화면용 ESC 단축키 id (모드 id 와 겹치지 않게)
_WH_KEYBOARD_LL = 13
_WM_KEYDOWN, _WM_KEYUP, _WM_SYSKEYDOWN, _WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


_LRESULT = ctypes.c_ssize_t
_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wt.HINSTANCE, wt.DWORD]
_u32.SetWindowsHookExW.restype = wt.HHOOK
_u32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
_u32.CallNextHookEx.restype = _LRESULT
_u32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
_u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_u32.GetAsyncKeyState.restype = ctypes.c_short
_u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
_u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
_k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_k32.GetModuleHandleW.restype = wt.HMODULE
_WM_QUIT = 0x0012


def _current_mods():
    down = lambda vk: _u32.GetAsyncKeyState(vk) & 0x8000
    m = 0
    if down(0x11):
        m |= winapi.MOD_CONTROL
    if down(0x10):
        m |= winapi.MOD_SHIFT
    if down(0x12):
        m |= winapi.MOD_ALT
    if down(0x5B) or down(0x5C):
        m |= winapi.MOD_WIN
    return m


class _PrintHook:
    """별도 스레드에서 도는 저수준 키보드 훅. 메인 스레드가 캡처 준비로 바빠도 지연되지 않는다.
    일치하는 Print Screen 조합을 누르면 sink 창으로 WM_HOTKEY(id) 를 보낸다."""

    def __init__(self, hwnd, combos):
        self.hwnd = hwnd
        self.combos = dict(combos)  # {modifiers: hotkey id}
        self.down = False
        self.tid = 0
        self.ok = False
        self._proc = _HOOKPROC(self._ll_proc)  # GC 방지용 참조 유지
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="PrintHook", daemon=True)
        self._thread.start()
        self._ready.wait(2)

    def _run(self):
        self.tid = _k32.GetCurrentThreadId()
        hook = _u32.SetWindowsHookExW(_WH_KEYBOARD_LL, self._proc, _k32.GetModuleHandleW(None), 0)
        self.ok = bool(hook)
        self._ready.set()
        if not hook:
            return
        msg = wt.MSG()
        while _u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        _u32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self.tid:
            _u32.PostThreadMessageW(self.tid, _WM_QUIT, 0, 0)
            self._thread.join(1)

    def _ll_proc(self, code, wparam, lparam):
        try:
            if code == 0:
                kb = _KBDLLHOOKSTRUCT.from_address(lparam)
                if kb.vkCode == VK_SNAPSHOT:
                    if wparam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
                        hid = self.combos.get(_current_mods())
                        if hid:
                            if not self.down:  # 키 반복 무시
                                self.down = True
                                _u32.PostMessageW(self.hwnd, winapi.WM_HOTKEY, hid, 0)
                            return 1  # Windows 기본 동작(클립보드 복사, 캡처 도구) 차단
                    elif wparam in (_WM_KEYUP, _WM_SYSKEYUP) and self.down:
                        self.down = False
                        return 1
        except Exception:
            pass
        return _u32.CallNextHookEx(None, code, wparam, lparam)


class HotkeyManager(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self._sink = QWidget()
        self._hwnd = int(self._sink.winId())
        self._ids = {}
        self._registered = []   # RegisterHotKey 로 등록한 id
        self._prt_hook = None
        self._esc_cb = None
        QCoreApplication.instance().installNativeEventFilter(self)

    def set_escape(self, callback):
        """캡처 화면이 떠 있는 동안 ESC 를 전역 단축키로 잡는다 (포커스가 없어도 취소되도록). None 이면 해제."""
        if self._esc_cb is not None:
            winapi.user32.UnregisterHotKey(self._hwnd, _ESC_ID)
            self._esc_cb = None
        if callback is not None and winapi.user32.RegisterHotKey(self._hwnd, _ESC_ID, 0, 0x1B):
            self._esc_cb = callback

    def unregister_all(self):
        for hid in self._registered:
            winapi.user32.UnregisterHotKey(self._hwnd, hid)
        self._registered.clear()
        self._ids.clear()
        if self._prt_hook:
            self._prt_hook.stop()
            self._prt_hook = None

    def register_all(self, mapping):
        """mapping: {mode: 'Ctrl+Shift+C'} -> 등록 실패한 [(mode, seq)]"""
        self.unregister_all()
        failed = []
        prt = {}  # {modifiers: (id, mode, seq)}
        for i, (mode, seq) in enumerate(mapping.items(), start=1):
            if not seq:
                continue
            mv = seq_to_win(seq)
            if mv and mv[1] == VK_SNAPSHOT:
                prt[mv[0]] = (i, mode, seq)
                continue
            if not mv or not winapi.user32.RegisterHotKey(self._hwnd, i, mv[0] | winapi.MOD_NOREPEAT, mv[1]):
                failed.append((mode, seq))
                continue
            self._registered.append(i)
            self._ids[i] = mode
        if prt:
            hook = _PrintHook(self._hwnd, {m: v[0] for m, v in prt.items()})
            if hook.ok:
                self._prt_hook = hook
                self._ids.update({i: mode for i, mode, _ in prt.values()})
            else:
                failed.extend((mode, seq) for _, mode, seq in prt.values())
        return failed

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wt.MSG.from_address(int(message))
            if msg.message == winapi.WM_HOTKEY and (msg.hWnd or 0) == self._hwnd:
                if int(msg.wParam) == _ESC_ID:
                    cb = self._esc_cb
                    if cb is not None:
                        QTimer.singleShot(0, cb)
                    return True, 0
                mode = self._ids.get(int(msg.wParam))
                if mode:
                    QTimer.singleShot(0, lambda m=mode: self.callback(m))
                return True, 0
        return False, 0
