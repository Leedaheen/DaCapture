"""화면 이미지 획득 (mss / GDI BitBlt)."""
import mss
import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


def new_mss():
    cls = getattr(mss, "MSS", None) or mss.mss
    return cls()


def _to_qimage(shot):
    img = QImage(shot.raw, shot.width, shot.height, shot.width * 4, QImage.Format.Format_RGB32)
    return img.copy()


def monitors():
    """모니터별 사각형(물리 픽셀) 목록."""
    with new_mss() as sct:
        return [QRect(m["left"], m["top"], m["width"], m["height"]) for m in sct.monitors[1:]]


def virtual_rect():
    with new_mss() as sct:
        m = sct.monitors[0]
        return QRect(m["left"], m["top"], m["width"], m["height"])


def grab_rect(rect: QRect) -> QImage:
    with new_mss() as sct:
        shot = sct.grab({"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()})
        return _to_qimage(shot)


def grab_virtual():
    """전체 가상 데스크톱 이미지와 그 사각형."""
    with new_mss() as sct:
        m = sct.monitors[0]
        shot = sct.grab(m)
        return _to_qimage(shot), QRect(m["left"], m["top"], m["width"], m["height"])


def grab_np(rect: QRect, sct=None) -> np.ndarray:
    """(H, W, 4) uint8 BGRA 배열."""
    own = sct is None
    if own:
        sct = new_mss()
    try:
        shot = sct.grab({"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()})
        return np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4).copy()
    finally:
        if own:
            sct.close()


def np_to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGB32).copy()
