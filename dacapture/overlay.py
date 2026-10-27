"""캡처 영역 선택 오버레이 (정지 화면 위에서 영역/창/단위영역/지정사이즈/스크롤 대상 선택)."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QWidget

from . import winapi
from .config import MODE_NAMES

RED = QColor("#E8192C")
NAVY = QColor("#1B365D")
DIM = QColor(0, 0, 0, 115)
MAG_CELLS = 15
MAG_ZOOM = 8

HELP = {
    "region": "드래그: 영역 지정   |   클릭: 창 캡처   |   방향키: 1px 이동   |   ESC/우클릭: 취소",
    "window": "캡처할 창을 클릭하세요   |   ESC/우클릭: 취소",
    "element": "캡처할 영역을 클릭하세요   |   휠 위/아래: 상위/하위 영역   |   ESC/우클릭: 취소",
    "scroll": "스크롤할 영역을 클릭하세요   |   휠 위/아래: 상위/하위 영역   |   ESC/우클릭: 취소",
    "fixed": "클릭: 캡처   |   방향키: 1px 이동   |   ESC/우클릭: 취소",
}


def _qrect(t):
    return QRect(QPoint(t[0], t[1]), QPoint(t[2] - 1, t[3] - 1))


class CaptureOverlay(QWidget):
    """finished(dict | None): {"mode", "rect"(전역), "image"} 또는 scroll 은 {"mode", "rect", "point"}."""
    finished = Signal(object)

    def __init__(self, mode, cfg, shot, vrect, windows, uia):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.mode = mode
        self.cfg = cfg
        self.shot = shot
        self.vrect = vrect
        self.origin = vrect.topLeft()
        self.windows = windows
        self.uia = uia
        self.magnifier = cfg.get("general/magnifier")
        self.fixed_size = QSize(max(1, cfg.get("capture/fixed_w")), max(1, cfg.get("capture/fixed_h")))

        self.bright = QPixmap.fromImage(shot)
        dark = QPixmap(self.bright)
        p = QPainter(dark)
        p.fillRect(dark.rect(), DIM)
        p.end()
        self.dark = dark

        self.mouse = QCursor.pos() - self.origin
        self.press = None
        self.sel = None
        self.path = []          # 단위영역 경로 [(QRect 로컬, scrollable)]
        self.level = 0
        self._path_key = None
        self._done = False
        self._label_font = QFont("Malgun Gothic")
        self._label_font.setPixelSize(13)

        self._elem_timer = QTimer(self, singleShot=True, interval=25)
        self._elem_timer.timeout.connect(self._update_element)

        self.setGeometry(vrect)
        self._update_hover()

    # ------------------------------------------------------------ lifecycle
    def start(self):
        self.show()
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        self.setFocus()
        if self.mode in ("element", "scroll"):
            self._update_element()

    def _finish(self, result):
        if self._done:
            return
        self._done = True
        self.hide()
        self.finished.emit(result)
        self.close()

    def _finish_rect(self, local):
        local = local.intersected(self.rect())
        if local.width() < 1 or local.height() < 1:
            return
        if self.mode == "scroll":
            pt = self.mouse if local.contains(self.mouse) else local.center()
            self._finish({"mode": "scroll", "rect": local.translated(self.origin), "point": pt + self.origin})
        else:
            self._finish({"mode": self.mode, "rect": local.translated(self.origin), "image": self.shot.copy(local)})

    def cancel(self):
        self._finish(None)

    # ------------------------------------------------------------ hover target
    def _window_at(self, local):
        g = local + self.origin
        for hwnd, r in self.windows:
            if r[0] <= g.x() < r[2] and r[1] <= g.y() < r[3]:
                return hwnd, _qrect(r).translated(-self.origin)
        return None, None

    def _update_hover(self):
        if self.mode == "window":
            _, r = self._window_at(self.mouse)
            self.sel = r.intersected(self.rect()) if r else None
        elif self.mode == "fixed":
            w, h = self.fixed_size.width(), self.fixed_size.height()
            x = min(max(self.mouse.x() - w // 2, 0), max(0, self.width() - w))
            y = min(max(self.mouse.y() - h // 2, 0), max(0, self.height() - h))
            self.sel = QRect(x, y, w, h).intersected(self.rect())
        elif self.mode in ("element", "scroll"):
            self._elem_timer.start()

    def _update_element(self):
        hwnd, wrect = self._window_at(self.mouse)
        if not hwnd:
            self.path, self.sel = [], None
            self.update()
            return
        g = self.mouse + self.origin
        rects = [(wrect, False)]
        try:
            if winapi.window_pid(hwnd) != winapi.OWN_PID and self.uia is not None:
                for r, scr in self.uia.path(hwnd, g.x(), g.y(), check_scroll=self.mode == "scroll")[1:]:
                    rects.append((_qrect(r).translated(-self.origin), scr))
            if len(rects) == 1:
                for r in winapi.child_window_path(hwnd, g.x(), g.y()):
                    rects.append((_qrect(r).translated(-self.origin), False))
        except Exception:
            pass
        clean = []
        for r, scr in rects:
            r = r.intersected(wrect).intersected(self.rect())
            if r.width() < 4 or r.height() < 4:
                continue
            if clean and clean[-1][0] == r:
                clean[-1] = (r, clean[-1][1] or scr)
                continue
            clean.append((r, scr))
        key = tuple((r.x(), r.y(), r.width(), r.height()) for r, _ in clean)
        if key != self._path_key:
            self._path_key = key
            self.path = clean
            if self.mode == "scroll":
                idx = [i for i, (r, scr) in enumerate(clean) if scr and r.height() >= 60]
                self.level = idx[-1] if idx else 0
            else:
                self.level = len(clean) - 1
        self.sel = self.path[self.level][0] if self.path else None
        self.update()

    # ------------------------------------------------------------ events
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            if self.mode == "region" and self.press is not None:
                self.press = None
                self.sel = None
                self.update()
            else:
                self.cancel()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.mouse = e.position().toPoint()
        if self.mode == "region":
            self.press = self.mouse
            self.sel = QRect(self.press, self.press)
            self.update()
        elif self.mode in ("element", "scroll"):
            self._elem_timer.stop()
            if self._path_key is None:
                self._update_element()
            if self.sel:
                self._finish_rect(self.sel)
        elif self.sel:
            self._finish_rect(self.sel)

    def mouseMoveEvent(self, e):
        self.mouse = e.position().toPoint()
        if self.mode == "region" and self.press is not None:
            self.sel = QRect(self.press, self.mouse).normalized()
        else:
            self._update_hover()
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.mode != "region" or self.press is None:
            return
        self.mouse = e.position().toPoint()
        r = QRect(self.press, self.mouse).normalized()
        self.press = None
        if r.width() >= 3 and r.height() >= 3:
            self._finish_rect(r)
        else:
            _, wr = self._window_at(self.mouse)
            if wr:
                self._finish_rect(wr)

    def wheelEvent(self, e):
        if self.mode in ("element", "scroll") and self.path:
            step = -1 if e.angleDelta().y() > 0 else 1
            self.level = max(0, min(len(self.path) - 1, self.level + step))
            self.sel = self.path[self.level][0]
            self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.cancel()
            return
        moves = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if k in moves:
            dx, dy = moves[k]
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                dx, dy = dx * 10, dy * 10
            QCursor.setPos(QCursor.pos() + QPoint(dx, dy))
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.sel:
            self._finish_rect(self.sel)

    # ------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.dark)
        sel = self.sel
        if sel and sel.isValid():
            p.drawPixmap(sel, self.bright, sel)
            pen = QPen(RED, 2)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel.adjusted(0, 0, -1, -1))
            self._draw_size_label(p, sel)
        elif self.mode == "region":
            pen = QPen(QColor(255, 255, 255, 170), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(0, self.mouse.y(), self.width(), self.mouse.y())
            p.drawLine(self.mouse.x(), 0, self.mouse.x(), self.height())
        self._draw_help(p)
        if self.magnifier and self.mode in ("region", "fixed"):
            self._draw_magnifier(p)
        p.end()

    def _label(self, p, text, anchor, below_ok=True):
        p.setFont(self._label_font)
        fm = QFontMetrics(self._label_font)
        w = fm.horizontalAdvance(text) + 14
        h = fm.height() + 8
        x = min(max(anchor.x(), 0), self.width() - w)
        y = anchor.y() - h - 4
        if y < 0 and below_ok:
            y = anchor.y() + 4
        box = QRect(x, y, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(27, 54, 93, 225))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_size_label(self, p, sel):
        text = f"{sel.width()} x {sel.height()}"
        if self.mode in ("element", "scroll") and len(self.path) > 1:
            text += f"   [{self.level + 1}/{len(self.path)}]"
        if self.mode == "scroll":
            text += "   스크롤 가능" if self.path and self.path[self.level][1] else ""
        self._label(p, text, sel.topLeft())

    def _draw_help(self, p):
        text = f"{MODE_NAMES.get(self.mode, '')}  -  {HELP.get(self.mode, '')}"
        screen_rect = self.rect()
        for s in self.screen().virtualSiblings() if self.screen() else []:
            g = s.geometry().translated(-self.origin)
            if g.contains(self.mouse):
                screen_rect = g
                break
        p.setFont(self._label_font)
        fm = QFontMetrics(self._label_font)
        w = fm.horizontalAdvance(text) + 28
        h = fm.height() + 14
        box = QRect(screen_rect.center().x() - w // 2, screen_rect.top() + 14, w, h)
        if self.sel and box.intersects(self.sel) and box.contains(self.mouse):
            box.moveBottom(screen_rect.bottom() - 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20, 200))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_magnifier(self, p):
        m = self.mouse
        size = MAG_CELLS * MAG_ZOOM
        info_h = 42
        x, y = m.x() + 22, m.y() + 22
        if x + size > self.width():
            x = m.x() - 22 - size
        if y + size + info_h > self.height():
            y = m.y() - 22 - size - info_h
        box = QRect(x, y, size, size)
        half = MAG_CELLS // 2
        src = QRect(m.x() - half, m.y() - half, MAG_CELLS, MAG_CELLS)
        p.fillRect(box, QColor("black"))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(box, self.bright, src)
        p.setPen(QPen(QColor(232, 25, 44, 150), MAG_ZOOM))
        c = half * MAG_ZOOM + MAG_ZOOM // 2
        p.drawLine(box.left(), box.top() + c, box.left() + half * MAG_ZOOM, box.top() + c)
        p.drawLine(box.left() + (half + 1) * MAG_ZOOM, box.top() + c, box.right() + 1, box.top() + c)
        p.drawLine(box.left() + c, box.top(), box.left() + c, box.top() + half * MAG_ZOOM)
        p.drawLine(box.left() + c, box.top() + (half + 1) * MAG_ZOOM, box.left() + c, box.bottom() + 1)
        p.setPen(QPen(QColor("white"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(box.left() + half * MAG_ZOOM, box.top() + half * MAG_ZOOM, MAG_ZOOM - 1, MAG_ZOOM - 1)
        p.setPen(QPen(NAVY, 2))
        p.drawRect(box.adjusted(-1, -1, 0, 0))

        info = QRect(x, y + size + 2, size, info_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(27, 54, 93, 235))
        p.drawRect(info)
        col = self.shot.pixelColor(m) if self.shot.rect().contains(m) else QColor("black")
        g = m + self.origin
        f = QFont(self._label_font)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(info.adjusted(6, 3, -4, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   f"X {g.x()}  Y {g.y()}\nRGB {col.red()},{col.green()},{col.blue()}")
        p.fillRect(QRect(info.right() - 16, info.top() + 6, 11, 11), col)
