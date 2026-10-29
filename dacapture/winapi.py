"""Win32 / DWM / UI Automation 래퍼 (ctypes).

모든 좌표는 물리 픽셀(Per-Monitor DPI aware) 기준의 화면 좌표다.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
ole32 = ctypes.WinDLL("ole32")

HRESULT = ctypes.c_long
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_EX_TRANSPARENT, WS_EX_LAYERED = 0x20, 0x80000
WS_CHILD = 0x40000000
LWA_ALPHA = 0x2
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
MOUSEEVENTF_WHEEL = 0x0800
INPUT_MOUSE = 0
VK_ESCAPE = 0x1B
WDA_EXCLUDEFROMCAPTURE = 0x11


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]

    def as_tuple(self):
        return (self.left, self.top, self.right, self.bottom)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wt.LONG
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetLayeredWindowAttributes.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD),
                                              ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wt.DWORD)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
user32.SetForegroundWindow.argtypes = [wt.HWND]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
dwmapi.DwmGetWindowAttribute.restype = HRESULT
ole32.CLSIDFromString.argtypes = [wt.LPCWSTR, ctypes.POINTER(GUID)]
ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD,
                                   ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]

OWN_PID = os.getpid()


# ---------------------------------------------------------------- windows
def window_rect(hwnd):
    """그림자 등 보이지 않는 테두리를 제외한 실제 창 영역."""
    r = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r.as_tuple()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.as_tuple()


def client_rect(hwnd):
    r = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y, pt.x + r.right, pt.y + r.bottom)


def is_cloaked(hwnd):
    v = wt.DWORD(0)
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v)) == 0:
        return v.value != 0
    return False


def window_pid(hwnd):
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _is_invisible_layered(hwnd, exstyle):
    if not exstyle & WS_EX_LAYERED:
        return False
    key, alpha, flags = wt.DWORD(), ctypes.c_ubyte(), wt.DWORD()
    if user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(key), ctypes.byref(alpha), ctypes.byref(flags)):
        return bool(flags.value & LWA_ALPHA) and alpha.value == 0
    return False


def list_windows():
    """보이는 최상위 창 목록 [(hwnd, (l, t, r, b)), ...] - Z 순서(위쪽 먼저)."""
    out = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TRANSPARENT or _is_invisible_layered(hwnd, ex) or is_cloaked(hwnd):
            return True
        r = window_rect(hwnd)
        if r[2] - r[0] > 1 and r[3] - r[1] > 1:
            out.append((hwnd, r))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def child_window_path(hwnd, x, y):
    """점을 포함하는 자식 창 사각형들 (큰 것부터)."""
    rects = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            r = RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            if r.left <= x < r.right and r.top <= y < r.bottom and r.right > r.left and r.bottom > r.top:
                rects.append(r.as_tuple())
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    rects = list(dict.fromkeys(rects))
    rects.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True)
    return rects


# ---------------------------------------------------------------- UI Automation (raw COM vtable)
_PROTO_CACHE = {}


def _vcall(ptr, index, argtypes, *args):
    key = (index, tuple(argtypes))
    proto = _PROTO_CACHE.get(key)
    if proto is None:
        proto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)
        _PROTO_CACHE[key] = proto
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return proto(vtbl[index])(ptr, *args)


_RELEASE = ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)


def _release(ptr):
    if ptr:
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        _RELEASE(vtbl[2])(ptr)


def _guid(s):
    g = GUID()
    ole32.CLSIDFromString(s, ctypes.byref(g))
    return g


# IUIAutomation vtable
_IUIA_ELEMENT_FROM_HANDLE = 6
_IUIA_CONTROL_VIEW_WALKER = 14
# IUIAutomationTreeWalker vtable
_WALK_FIRST_CHILD = 4
_WALK_NEXT_SIBLING = 6
# IUIAutomationElement vtable
_EL_GET_PROPERTY = 10
_EL_IS_OFFSCREEN = 38
_EL_BOUNDING_RECT = 43
UIA_ScrollVerticallyScrollablePropertyId = 30057
VT_BOOL = 11


class UIAutomation:
    """UI Automation 으로 마우스 아래의 UI 요소 계층(사각형 경로)을 구한다."""

    def __init__(self):
        self.uia = None
        self.walker = None
        try:
            ole32.CoInitializeEx(None, 0x2)
            ptr = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(ctypes.byref(_guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")), None, 1,
                                        ctypes.byref(_guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")),
                                        ctypes.byref(ptr))
            if hr < 0 or not ptr.value:
                return
            self.uia = ptr.value
            w = ctypes.c_void_p()
            if _vcall(self.uia, _IUIA_CONTROL_VIEW_WALKER, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(w)) >= 0:
                self.walker = w.value
        except Exception:
            self.uia = None

    @property
    def ok(self):
        return bool(self.uia and self.walker)

    def _rect(self, el):
        r = RECT()
        if _vcall(el, _EL_BOUNDING_RECT, [ctypes.POINTER(RECT)], ctypes.byref(r)) < 0:
            return None
        return r.as_tuple()

    def _offscreen(self, el):
        b = wt.BOOL(0)
        if _vcall(el, _EL_IS_OFFSCREEN, [ctypes.POINTER(wt.BOOL)], ctypes.byref(b)) < 0:
            return False
        return bool(b.value)

    def _v_scrollable(self, el):
        var = (ctypes.c_ubyte * 24)()
        if _vcall(el, _EL_GET_PROPERTY, [ctypes.c_int, ctypes.c_void_p],
                  UIA_ScrollVerticallyScrollablePropertyId, ctypes.byref(var)) < 0:
            return False
        vt = var[0] | (var[1] << 8)
        return vt == VT_BOOL and (var[8] | var[9]) != 0

    def _children(self, el, limit=300):
        child = ctypes.c_void_p()
        if _vcall(self.walker, _WALK_FIRST_CHILD, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                  el, ctypes.byref(child)) < 0:
            return
        cur = child.value
        n = 0
        while cur:
            # 호출자가 yield 받은 요소를 Release 할 수 있으므로 다음 형제를 먼저 구한다
            nxt = ctypes.c_void_p()
            hr = _vcall(self.walker, _WALK_NEXT_SIBLING, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                        cur, ctypes.byref(nxt))
            nxt = nxt.value if hr >= 0 else None
            n += 1
            if n > limit:
                _release(cur)
                _release(nxt)
                return
            try:
                yield cur
            except GeneratorExit:
                _release(nxt)
                raise
            cur = nxt

    def path(self, hwnd, x, y, check_scroll=False, budget=0.25):
        """[(rect, v_scrollable), ...] 바깥 -> 안쪽 순서."""
        if not self.ok:
            return []
        el = ctypes.c_void_p()
        if _vcall(self.uia, _IUIA_ELEMENT_FROM_HANDLE, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                  hwnd, ctypes.byref(el)) < 0 or not el.value:
            return []
        deadline = time.perf_counter() + budget
        cur = el.value
        out = []
        r = self._rect(cur)
        if r:
            out.append((r, self._v_scrollable(cur) if check_scroll else False))
        try:
            for _ in range(40):
                if time.perf_counter() > deadline:
                    break
                best, best_area, best_rect = None, None, None
                for ch in self._children(cur):
                    keep = False
                    cr = self._rect(ch)
                    if cr and cr[0] <= x < cr[2] and cr[1] <= y < cr[3] and not self._offscreen(ch):
                        area = (cr[2] - cr[0]) * (cr[3] - cr[1])
                        if area > 0 and (best_area is None or area < best_area):
                            if best:
                                _release(best)
                            best, best_area, best_rect = ch, area, cr
                            keep = True
                    if not keep:
                        _release(ch)
                    if time.perf_counter() > deadline:
                        break
                if not best:
                    break
                _release(cur)
                cur = best
                out.append((best_rect, self._v_scrollable(cur) if check_scroll else False))
        finally:
            _release(cur)
        return out


# ---------------------------------------------------------------- input / misc
def cursor_pos():
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


def mouse_wheel(delta):
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def exclude_from_capture(hwnd):
    try:
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.GetForegroundWindow.restype = wt.HWND


def force_foreground(hwnd):
    """창을 앞으로 가져와 키보드 포커스를 준다.
    저수준 훅으로 받은 단축키(Print Screen)는 입력이 이 프로세스로 오지 않아 SetForegroundWindow 가
    거부되므로, 현재 전경 창의 스레드에 입력을 잠시 붙여 권한을 얻는다."""
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    cur = _k32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid and fg_tid != cur and user32.AttachThreadInput(cur, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur, fg_tid, False)


# ---------------------------------------------------------------- autostart
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(enabled, name="DaCapture"):
    import winreg
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}" --tray'
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        script = os.path.abspath(sys.argv[0])
        cmd = f'"{pyw}" "{script}" --tray'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
