"""전역 단축키 (RegisterHotKey + Qt 네이티브 이벤트 필터)."""
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


class HotkeyManager(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self._sink = QWidget()
        self._hwnd = int(self._sink.winId())
        self._ids = {}
        QCoreApplication.instance().installNativeEventFilter(self)

    def unregister_all(self):
        for hid in list(self._ids):
            winapi.user32.UnregisterHotKey(self._hwnd, hid)
        self._ids.clear()

    def register_all(self, mapping):
        """mapping: {mode: 'Ctrl+Shift+C'} -> 등록 실패한 [(mode, seq)]"""
        self.unregister_all()
        failed = []
        for i, (mode, seq) in enumerate(mapping.items(), start=1):
            if not seq:
                continue
            mv = seq_to_win(seq)
            if not mv or not winapi.user32.RegisterHotKey(self._hwnd, i, mv[0] | winapi.MOD_NOREPEAT, mv[1]):
                failed.append((mode, seq))
                continue
            self._ids[i] = mode
        return failed

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wt.MSG.from_address(int(message))
            if msg.message == winapi.WM_HOTKEY and (msg.hWnd or 0) == self._hwnd:
                mode = self._ids.get(int(msg.wParam))
                if mode:
                    QTimer.singleShot(0, lambda m=mode: self.callback(m))
                return True, 0
        return False, 0
