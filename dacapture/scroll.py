"""스크롤 캡처: 대상 영역에 마우스 휠을 보내며 프레임을 받아 이어 붙인다."""
import time

import numpy as np
from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from . import winapi
from .grabber import grab_np, new_mss, np_to_qimage


class Stitcher:
    """연속 프레임의 세로 이동량을 찾아 하나의 긴 이미지로 합친다.

    고정 머리글/바닥글(스크롤되지 않는 영역)은 첫 이동 쌍에서 감지해 한 번만 넣는다.
    """

    MIN_OVERLAP = 12

    def __init__(self, first):
        self.h, self.w = first.shape[:2]
        self.first = first
        self.prev = first
        self.prev_hash = self._hash(first)
        self.top = None
        self.bottom = None
        self.chunks = []
        self.last = first
        self.last_d = None
        self.total = self.h

    @staticmethod
    def _hash(img):
        rows = np.ascontiguousarray(img[:, :, :3])
        return np.array([hash(rows[i].tobytes()) for i in range(rows.shape[0])], dtype=np.int64)

    @staticmethod
    def _uniform(img):
        return (img[:, :, :3] == img[:, :1, :3]).all(axis=(1, 2))

    @staticmethod
    def _signature(img):
        gray = img[:, :, :3].astype(np.float32).mean(axis=2)
        w = gray.shape[1]
        blocks = 32 if w >= 32 else w
        cut = (w // blocks) * blocks
        return gray[:, :cut].reshape(gray.shape[0], blocks, -1).mean(axis=2)

    def _find_shift(self, a_img, b_img, a_hash, b_hash):
        t, bt = self.top, self.bottom
        n = self.h - t - bt
        if n <= self.MIN_OVERLAP + 1:
            return None
        a = a_hash[t:self.h - bt]
        b = b_hash[t:self.h - bt]
        informative = ~self._uniform(b_img[t:self.h - bt])

        best_d, best_score = None, -1.0
        for d in range(1, n - self.MIN_OVERLAP):
            ov = n - d
            inf = informative[:ov]
            k = int(inf.sum())
            if k < 3:
                continue
            score = float(((a[d:] == b[:ov]) & inf).sum()) / k
            if score > best_score + 1e-9 or (abs(score - best_score) < 1e-9 and self.last_d is not None
                                             and abs(d - self.last_d) < abs(best_d - self.last_d)):
                best_d, best_score = d, score
        if best_d is not None and best_score >= 0.6:
            return best_d

        # 분수 배율 렌더링 등으로 픽셀이 정확히 일치하지 않는 경우: 근사 비교
        sa = self._signature(a_img[t:self.h - bt])
        sb = self._signature(b_img[t:self.h - bt])
        errs = []
        for d in range(1, n - self.MIN_OVERLAP):
            ov = n - d
            errs.append((float(np.abs(sa[d:] - sb[:ov]).mean()), d))
        if not errs:
            return None
        errs.sort()
        err, d = errs[0]
        median = errs[len(errs) // 2][0]
        if err < 4.0 and err < median * 0.5:
            return d
        return None

    def add(self, frame):
        """'same' | 'ok' | 'fail'"""
        if frame.shape != self.prev.shape:
            return "fail"
        if np.array_equal(frame, self.prev):
            return "same"
        fh = self._hash(frame)
        if self.top is None:
            eq = fh == self.prev_hash
            top = int(np.argmin(eq)) if not eq.all() else self.h
            bottom = int(np.argmin(eq[::-1])) if not eq.all() else self.h
            if top + bottom >= self.h - self.MIN_OVERLAP * 2:
                return "same"
            self.top, self.bottom = top, bottom
        d = self._find_shift(self.prev, frame, self.prev_hash, fh)
        if d is None:
            return "fail"
        end = self.h - self.bottom
        self.chunks.append(frame[end - d:end])
        self.total += d
        self.last_d = d
        self.prev, self.prev_hash, self.last = frame, fh, frame
        return "ok"

    def result(self):
        if not self.chunks:
            return self.first
        t, bt = self.top, self.bottom
        parts = [self.first[:self.h - bt]] + self.chunks
        if bt:
            parts.append(self.last[self.h - bt:])
        return np.concatenate(parts, axis=0)


class _Hud(QWidget):
    def __init__(self, on_stop):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("QWidget{background:#1B365D;color:white;border-radius:6px}"
                           "QPushButton{background:#E8192C;border:none;padding:5px 14px;border-radius:4px;"
                           "font-weight:bold}QPushButton:hover{background:#ff3347}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 8, 8)
        self.label = QLabel("스크롤 캡처 준비 중...")
        f = QFont("Malgun Gothic")
        f.setPixelSize(13)
        self.label.setFont(f)
        btn = QPushButton("중지 (ESC)")
        btn.setFont(f)
        btn.clicked.connect(on_stop)
        lay.addWidget(self.label)
        lay.addWidget(btn)


class ScrollCapture(QObject):
    finished = Signal(object)   # QImage | None

    def __init__(self, rect: QRect, point, cfg):
        super().__init__()
        self.rect = rect
        self.point = point
        self.max_h = max(1000, cfg.get("capture/scroll_max"))
        self.delay = max(50, cfg.get("capture/scroll_delay"))
        self.sct = new_mss()
        self.stitcher = None
        self.same_count = 0
        self.fail_count = 0
        self.stopped = False
        self.last_poll = None
        self.t0 = 0.0
        self.notches = 1 if rect.height() < 360 else 2
        self.hud = _Hud(self.stop)

    def start(self):
        self.hud.adjustSize()
        winapi.exclude_from_capture(int(self.hud.winId()))
        scr = QApplication.screenAt(self.rect.center()) or QApplication.primaryScreen()
        g = scr.geometry()
        x = g.center().x() - self.hud.width() // 2
        y = g.top() + 12
        hud_rect = QRect(x, y, self.hud.width(), self.hud.height())
        if hud_rect.intersects(self.rect):
            y = g.bottom() - self.hud.height() - 48
        self.hud.move(x, y)
        self.hud.show()
        winapi.set_cursor_pos(self.point.x(), self.point.y())
        QTimer.singleShot(150, self._first)

    def stop(self):
        self.stopped = True

    def _grab(self):
        return grab_np(self.rect, self.sct)

    def _first(self):
        self.stitcher = Stitcher(self._grab())
        self._scroll()

    def _scroll(self):
        if self.stopped or winapi.key_down(winapi.VK_ESCAPE):
            return self._finish()
        winapi.set_cursor_pos(self.point.x(), self.point.y())
        for _ in range(self.notches):
            winapi.mouse_wheel(-120)
        self.last_poll = None
        self.t0 = time.perf_counter()
        QTimer.singleShot(self.delay // 2, self._poll)

    def _poll(self):
        if self.stopped or winapi.key_down(winapi.VK_ESCAPE):
            return self._finish()
        frame = self._grab()
        elapsed = (time.perf_counter() - self.t0) * 1000
        stable = self.last_poll is not None and np.array_equal(frame, self.last_poll)
        if not stable and elapsed < self.delay + 900:
            self.last_poll = frame
            QTimer.singleShot(50, self._poll)
            return
        if elapsed < self.delay:
            QTimer.singleShot(int(self.delay - elapsed), self._poll)
            return
        status = self.stitcher.add(frame)
        if status == "same":
            self.same_count += 1
            if self.same_count >= 2:
                return self._finish()
        elif status == "fail":
            self.fail_count += 1
            if self.fail_count >= 2:
                return self._finish()
        else:
            self.same_count = self.fail_count = 0
        self.hud.label.setText(f"스크롤 캡처 중...  {self.rect.width()} x {self.stitcher.total} px")
        if self.stitcher.total >= self.max_h:
            return self._finish()
        self._scroll()

    def _finish(self):
        if self.hud is None:
            return
        self.hud.close()
        self.hud = None
        img = None
        if self.stitcher is not None:
            img = np_to_qimage(self.stitcher.result())
        self.sct.close()
        self.finished.emit(img)
