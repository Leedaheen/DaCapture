"""설정 저장/로드 (QSettings INI: %APPDATA%\\DaCapture\\DaCapture.ini)."""
import os
from datetime import datetime

from PySide6.QtCore import QSettings, QStandardPaths

MODES = ["region", "window", "element", "full", "scroll", "fixed"]

MODE_NAMES = {
    "region": "직접 지정",
    "window": "창 캡처",
    "element": "단위 영역",
    "full": "전체 화면",
    "scroll": "스크롤 캡처",
    "fixed": "지정 사이즈",
}

DEFAULT_HOTKEYS = {
    "region": "Ctrl+Shift+C",
    "window": "Ctrl+Shift+W",
    "element": "Ctrl+Shift+D",
    "full": "Ctrl+Shift+A",
    "scroll": "Ctrl+Shift+S",
    "fixed": "Ctrl+Shift+Z",
}

SAVE_FORMATS = ["png", "jpg", "bmp"]


def default_save_dir():
    pics = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return os.path.join(pics or os.path.expanduser("~"), "DaCapture")


DEFAULTS = {
    "general/open_editor": True,
    "general/copy_clipboard": True,
    "general/hide_main": True,
    "general/autostart": False,
    "general/start_tray": False,
    "general/magnifier": True,
    "general/tray_notice_shown": False,
    "general/check_update": True,
    "general/skip_version": "",
    "save/auto": False,
    "save/dir": "",
    "save/format": "png",
    "save/jpg_quality": 92,
    "save/prefix": "캡처",
    "capture/fixed_w": 800,
    "capture/fixed_h": 600,
    "capture/full_all": False,
    "capture/scroll_max": 20000,
    "capture/scroll_delay": 250,
    "editor/color": "#e8192c",
    "editor/width": 4,
    "editor/font_size": 20,
    "editor/fill": False,
}


class Config:
    def __init__(self):
        self.s = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                           "DaCapture", "DaCapture")

    def get(self, key):
        default = DEFAULTS[key]
        value = self.s.value(key, default)
        if isinstance(default, bool):
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("1", "true", "yes")
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        value = str(value) if value is not None else ""
        if key == "save/dir" and not value:
            return default_save_dir()
        return value

    def set(self, key, value):
        self.s.setValue(key, value)

    def hotkey(self, mode):
        return str(self.s.value(f"hotkeys/{mode}", DEFAULT_HOTKEYS[mode]) or "")

    def set_hotkey(self, mode, seq):
        self.s.setValue(f"hotkeys/{mode}", seq)

    def hotkeys(self):
        return {m: self.hotkey(m) for m in MODES}

    def sync(self):
        self.s.sync()

    def make_filename(self, ext=None):
        ext = ext or self.get("save/format")
        prefix = self.get("save/prefix").strip() or "캡처"
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        base = f"{prefix}_{stamp}"
        folder = self.get("save/dir")
        path = os.path.join(folder, f"{base}.{ext}")
        n = 2
        while os.path.exists(path):
            path = os.path.join(folder, f"{base}_{n}.{ext}")
            n += 1
        return path
