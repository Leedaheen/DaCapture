"""캡처 이미지 편집기."""
import math
import os

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QFontMetrics, QImage, QKeySequence,
                           QPainter, QPainterPath, QPen, QPolygonF)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QFileDialog, QLabel, QMainWindow,
                               QMessageBox, QScrollArea, QSpinBox, QTextEdit, QToolBar, QToolButton,
                               QWidget)

from . import icons

TOOLS = [
    ("hand", "이동 (H)", "H"),
    ("pen", "펜 (P)", "P"),
    ("highlight", "형광펜 (G)", "G"),
    ("line", "직선 (L)", "L"),
    ("arrow", "화살표 (A)", "A"),
    ("rect", "사각형 (R)", "R"),
    ("ellipse", "원 (E)", "E"),
    ("text", "텍스트 (T)", "T"),
    ("number", "번호 (N)", "N"),
    ("mosaic", "모자이크 (M)", "M"),
    ("crop", "자르기 (C)", "C"),
]
PALETTE = ["#E8192C", "#FF8C00", "#FFD400", "#2BB24C", "#1E88E5", "#1B365D", "#8E24AA", "#000000", "#FFFFFF"]
ZOOMS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
UNDO_LIMIT = 40


def _snap(a, b):
    """Shift: 45도 단위로 고정."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    length = math.hypot(dx, dy)
    return QPointF(a.x() + length * math.cos(ang), a.y() + length * math.sin(ang))


def _square(a, b):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    s = max(abs(dx), abs(dy))
    return QPointF(a.x() + math.copysign(s, dx or 1), a.y() + math.copysign(s, dy or 1))


def draw_arrow(p, a, b, width, color):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ang = math.atan2(dy, dx)
    head = max(12.0, width * 3.5)
    head = min(head, length)
    shaft_end = QPointF(b.x() - head * 0.75 * math.cos(ang), b.y() - head * 0.75 * math.sin(ang))
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(a, shaft_end)
    left = QPointF(b.x() - head * math.cos(ang - math.pi / 7), b.y() - head * math.sin(ang - math.pi / 7))
    right = QPointF(b.x() - head * math.cos(ang + math.pi / 7), b.y() - head * math.sin(ang + math.pi / 7))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([b, left, right]))


def pixelate(img, rect, block):
    rect = rect.intersected(img.rect())
    if rect.width() < 1 or rect.height() < 1:
        return None
    sub = img.copy(rect)
    small = sub.scaled(max(1, rect.width() // block), max(1, rect.height() // block),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return small.scaled(rect.width(), rect.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation)


class Canvas(QWidget):
    changed = Signal()
    cursorMoved = Signal(int, int)

    def __init__(self, image: QImage, owner):
        super().__init__()
        self.owner = owner
        self.img = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self.zoom = 1.0
        self.tool = "hand"
        self.color = QColor("#E8192C")
        self.width_ = 4
        self.font_size = 20
        self.fill = False
        self.counter = 1
        self.undo_stack, self.redo_stack = [], []
        self.modified = False
        self.p1 = self.p2 = None
        self.points = []
        self.pan_start = None
        self.text_edit = None
        self.text_pos = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._resize()

    # ------------------------------------------------------------ state
    def _resize(self):
        self.setFixedSize(QSize(max(1, round(self.img.width() * self.zoom)),
                                max(1, round(self.img.height() * self.zoom))))
        self.update()

    def set_zoom(self, z):
        self.commit_text()
        self.zoom = max(0.05, min(16.0, z))
        self._resize()
        self.changed.emit()

    def push_undo(self):
        self.undo_stack.append((self.img.copy(), self.counter))
        del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack.clear()
        self.modified = True

    def undo(self):
        self.commit_text()
        if self.undo_stack:
            self.redo_stack.append((self.img.copy(), self.counter))
            self.img, self.counter = self.undo_stack.pop()
            self.modified = True
            self._resize()
            self.changed.emit()

    def redo(self):
        self.commit_text()
        if self.redo_stack:
            self.undo_stack.append((self.img.copy(), self.counter))
            self.img, self.counter = self.redo_stack.pop()
            self.modified = True
            self._resize()
            self.changed.emit()

    def set_tool(self, tool):
        self.commit_text()
        self.tool = tool
        self.p1 = self.p2 = None
        cursor = {"hand": Qt.CursorShape.OpenHandCursor, "text": Qt.CursorShape.IBeamCursor}
        self.setCursor(cursor.get(tool, Qt.CursorShape.CrossCursor))
        self.update()

    def final_image(self):
        self.commit_text()
        return self.img

    # ------------------------------------------------------------ coords
    def to_img(self, pos):
        return QPointF(pos.x() / self.zoom, pos.y() / self.zoom)

    def _constrained(self, a, b, mods):
        if not mods & Qt.KeyboardModifier.ShiftModifier:
            return b
        if self.tool in ("line", "arrow"):
            return _snap(a, b)
        if self.tool in ("rect", "ellipse", "mosaic", "crop"):
            return _square(a, b)
        return b

    # ------------------------------------------------------------ drawing
    def _stroke_pen(self):
        if self.tool == "highlight":
            pen = QPen(QColor(self.color.red(), self.color.green(), self.color.blue()), max(12, self.width_ * 4))
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        else:
            pen = QPen(self.color, self.width_)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _shape_rect(self):
        return QRectF(self.p1, self.p2).normalized()

    def _draw_shape(self, p, preview=False):
        t = self.tool
        if t in ("pen", "highlight") and self.points:
            if t == "highlight":
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            p.setPen(self._stroke_pen())
            p.setBrush(Qt.BrushStyle.NoBrush)
            if len(self.points) == 1:
                p.drawPoint(self.points[0])
            else:
                path = QPainterPath(self.points[0])
                for pt in self.points[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            return
        if self.p1 is None or self.p2 is None:
            return
        if t == "line":
            p.setPen(self._stroke_pen())
            p.drawLine(self.p1, self.p2)
        elif t == "arrow":
            draw_arrow(p, self.p1, self.p2, self.width_, self.color)
        elif t in ("rect", "ellipse"):
            pen = self._stroke_pen()
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(self.color if self.fill else Qt.BrushStyle.NoBrush)
            r = self._shape_rect()
            if t == "rect":
                p.drawRect(r)
            else:
                p.drawEllipse(r)
        elif t == "mosaic":
            r = self._shape_rect().toAlignedRect()
            px = pixelate(self.img, r, max(6, self.width_ * 3))
            if px is not None:
                p.drawImage(r.intersected(self.img.rect()).topLeft(), px)
            if preview:
                p.setPen(QPen(QColor("#1B365D"), 1 / self.zoom, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(r))

    def _draw_number(self, p, center, n):
        radius = max(11.0, self.width_ * 3.0 + 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(center, radius, radius)
        f = QFont("Malgun Gothic")
        f.setPixelSize(int(radius * (1.15 if n < 10 else 0.9)))
        f.setBold(True)
        p.setFont(f)
        light = self.color.lightness() > 170
        p.setPen(QColor("black") if light else QColor("white"))
        p.drawText(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
                   Qt.AlignmentFlag.AlignCenter, str(n))

    def _commit_shape(self):
        self.push_undo()
        p = QPainter(self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_shape(p)
        p.end()
        self.changed.emit()

    def _crop(self, r):
        r = r.toAlignedRect().intersected(self.img.rect())
        if r.width() < 2 or r.height() < 2:
            return
        self.push_undo()
        self.img = self.img.copy(r)
        self._resize()
        self.changed.emit()

    # ------------------------------------------------------------ text
    def _start_text(self, img_pos):
        self.commit_text()
        self.text_pos = img_pos
        ed = QTextEdit(self)
        ed.setFrameStyle(0)
        ed.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ed.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ed.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        ed.setAcceptRichText(False)
        ed.document().setDocumentMargin(0)
        f = QFont("Malgun Gothic")
        f.setPixelSize(max(6, round(self.font_size * self.zoom)))
        f.setBold(True)
        ed.setFont(f)
        ed.setStyleSheet(f"QTextEdit{{background:rgba(255,255,255,40);color:{self.color.name()};"
                         f"border:1px dashed #1B365D;}}")
        ed.move(round(img_pos.x() * self.zoom) - 1, round(img_pos.y() * self.zoom) - 1)
        ed.textChanged.connect(self._fit_text)
        self.text_edit = ed
        self._fit_text()
        ed.show()
        ed.setFocus()

    def _fit_text(self):
        ed = self.text_edit
        if not ed:
            return
        fm = QFontMetrics(ed.font())
        lines = ed.toPlainText().split("\n") or [""]
        w = max(fm.horizontalAdvance(line) for line in lines) + fm.averageCharWidth() * 2 + 4
        h = fm.lineSpacing() * len(lines) + 6
        ed.resize(max(40, w), h)

    def commit_text(self):
        ed = self.text_edit
        if not ed:
            return
        self.text_edit = None
        text = ed.toPlainText().rstrip()
        color = self.color
        ed.hide()
        ed.deleteLater()
        if not text:
            return
        self.push_undo()
        p = QPainter(self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = QFont("Malgun Gothic")
        f.setPixelSize(self.font_size)
        f.setBold(True)
        p.setFont(f)
        p.setPen(color)
        fm = QFontMetrics(f)
        y = self.text_pos.y()
        for line in text.split("\n"):
            p.drawText(QPointF(self.text_pos.x(), y + fm.ascent()), line)
            y += fm.lineSpacing()
        p.end()
        self.changed.emit()
        self.update()

    # ------------------------------------------------------------ events
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom < 1)
        p.scale(self.zoom, self.zoom)
        p.drawImage(0, 0, self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.tool == "crop" and self.p1 is not None and self.p2 is not None:
            r = self._shape_rect()
            path = QPainterPath()
            path.addRect(QRectF(self.img.rect()))
            inner = QPainterPath()
            inner.addRect(r)
            p.fillPath(path.subtracted(inner), QColor(0, 0, 0, 120))
            p.setPen(QPen(QColor("#E8192C"), 1.5 / self.zoom, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
        else:
            self._draw_shape(p, preview=True)
        p.end()

    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton
                                                          and self.tool == "hand"):
            self.pan_start = (e.globalPosition().toPoint(), self.owner.scroll.horizontalScrollBar().value(),
                              self.owner.scroll.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        ip = self.to_img(pos)
        if self.tool == "text":
            if self.text_edit:
                self.commit_text()
            else:
                self._start_text(ip)
            return
        if self.tool == "number":
            self.push_undo()
            p = QPainter(self.img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_number(p, ip, self.counter)
            p.end()
            self.counter += 1
            self.changed.emit()
            self.update()
            return
        self.p1 = self.p2 = ip
        self.points = [ip] if self.tool in ("pen", "highlight") else []
        self.update()

    def mouseMoveEvent(self, e):
        ip = self.to_img(e.position())
        self.cursorMoved.emit(int(ip.x()), int(ip.y()))
        if self.pan_start:
            start, hx, vy = self.pan_start
            d = e.globalPosition().toPoint() - start
            self.owner.scroll.horizontalScrollBar().setValue(hx - d.x())
            self.owner.scroll.verticalScrollBar().setValue(vy - d.y())
            return
        if self.p1 is None:
            return
        if self.tool in ("pen", "highlight"):
            self.points.append(ip)
        self.p2 = self._constrained(self.p1, ip, e.modifiers())
        self.update()

    def mouseReleaseEvent(self, e):
        if self.pan_start:
            self.pan_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.tool == "hand" else Qt.CursorShape.CrossCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton or self.p1 is None:
            return
        self.p2 = self._constrained(self.p1, self.to_img(e.position()), e.modifiers())
        moved = (self.p2 - self.p1).manhattanLength() >= 2
        if self.tool == "crop":
            if moved:
                self._crop(self._shape_rect())
        elif self.tool in ("pen", "highlight") or moved:
            self._commit_shape()
        self.p1 = self.p2 = None
        self.points = []
        self.update()

    def keyPressEvent(self, e):
        if e.modifiers() == Qt.KeyboardModifier.NoModifier and self.owner.tool_key(e.key()):
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.owner.zoom_step(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            e.ignore()


class EditorWindow(QMainWindow):
    closed = Signal(object)

    def __init__(self, ctrl, image: QImage, title=None, path=None):
        super().__init__()
        self.ctrl = ctrl
        self.cfg = ctrl.cfg
        self.saved_path = path
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(icons.icon("app"))
        self.base_title = title or "캡처"

        self.canvas = Canvas(image, self)
        self.canvas.color = QColor(self.cfg.get("editor/color"))
        self.canvas.width_ = self.cfg.get("editor/width")
        self.canvas.font_size = self.cfg.get("editor/font_size")
        self.canvas.fill = self.cfg.get("editor/fill")
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea{background:#5B6470;border:none}")
        self.setCentralWidget(self.scroll)

        self._build_actions()
        self._build_toolbars()
        self._build_status()
        self.canvas.changed.connect(self._refresh)
        self.canvas.cursorMoved.connect(lambda x, y: self.pos_label.setText(f"{x}, {y}"))
        self._select_tool("hand")
        self._fit_window()
        self._refresh()

    # ------------------------------------------------------------ UI
    def _act(self, text, icon_name, slot, shortcut=None, tip=None):
        a = QAction(icons.icon(icon_name) if icon_name else None, text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip(f"{tip or text}" + (f" ({QKeySequence(shortcut).toString()})" if shortcut else ""))
        a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _build_actions(self):
        self.a_save = self._act("저장", "save", self.save, "Ctrl+S")
        self.a_save_as = self._act("다른 이름으로 저장", "save_as", self.save_as, "Ctrl+Shift+S")
        self.a_copy = self._act("복사", "copy", self.copy, "Ctrl+C", "클립보드로 복사")
        self.a_print = self._act("인쇄", "print", self.print_image, "Ctrl+P")
        self.a_open = self._act("열기", "open", self.open_file, "Ctrl+O", "이미지 파일 열기")
        self.a_undo = self._act("실행 취소", "undo", self.canvas.undo, "Ctrl+Z")
        self.a_redo = self._act("다시 실행", "redo", self.canvas.redo, "Ctrl+Y")
        self.a_zin = self._act("확대", "zoom_in", lambda: self.zoom_step(1), "Ctrl+=")
        self.a_zout = self._act("축소", "zoom_out", lambda: self.zoom_step(-1), "Ctrl+-")
        self.a_actual = self._act("실제 크기", "actual", lambda: self.canvas.set_zoom(1.0), "Ctrl+0")
        self.a_fit = self._act("창에 맞춤", "fit", self.zoom_fit, "Ctrl+9")
        self._act("닫기", None, self._escape, "Escape")
        extra_zoom = QAction(self)
        extra_zoom.setShortcut(QKeySequence("Ctrl++"))
        extra_zoom.triggered.connect(lambda: self.zoom_step(1))
        self.addAction(extra_zoom)

    def _tb(self, name):
        tb = QToolBar(name, self)
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        self.addToolBar(tb)
        return tb

    def _build_toolbars(self):
        tb = self._tb("파일")
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        new_btn = QToolButton()
        new_btn.setText("새 캡처")
        new_btn.setIcon(icons.icon("region"))
        new_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        new_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        new_btn.setMenu(self.ctrl.build_capture_menu(self))
        new_btn.clicked.connect(lambda: self.ctrl.capture("region"))
        tb.addWidget(new_btn)
        tb.addSeparator()
        for a in (self.a_open, self.a_save, self.a_save_as, self.a_copy, self.a_print):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.a_undo, self.a_redo):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.a_zin, self.a_zout, self.a_actual, self.a_fit):
            tb.addAction(a)

        self.addToolBarBreak()
        tt = self._tb("그리기")
        group = QActionGroup(self)
        group.setExclusive(True)
        self.tool_actions = {}
        self.tool_keys = {}
        for key, label, sc in TOOLS:
            a = QAction(icons.icon(key), label, self)
            a.setCheckable(True)
            a.setToolTip(label)
            a.triggered.connect(lambda _=False, k=key: self._select_tool(k))
            group.addAction(a)
            tt.addAction(a)
            self.tool_actions[key] = a
            self.tool_keys[getattr(Qt.Key, f"Key_{sc}")] = key
        tt.addSeparator()

        tt.addWidget(QLabel(" 색 "))
        self.color_btn = QToolButton()
        self.color_btn.setFixedSize(26, 22)
        self.color_btn.setToolTip("색 선택")
        self.color_btn.clicked.connect(self._pick_color)
        tt.addWidget(self.color_btn)
        for c in PALETTE:
            b = QToolButton()
            b.setFixedSize(16, 16)
            b.setStyleSheet(f"QToolButton{{background:{c};border:1px solid #999;border-radius:2px}}"
                            f"QToolButton:hover{{border:1px solid #1B365D}}")
            b.clicked.connect(lambda _=False, col=c: self._set_color(QColor(col)))
            tt.addWidget(b)
        tt.addSeparator()

        tt.addWidget(QLabel(" 굵기 "))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setValue(self.canvas.width_)
        self.width_spin.valueChanged.connect(self._set_width)
        tt.addWidget(self.width_spin)
        tt.addWidget(QLabel(" 글자 "))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 200)
        self.font_spin.setValue(self.canvas.font_size)
        self.font_spin.valueChanged.connect(self._set_font)
        tt.addWidget(self.font_spin)
        self.fill_chk = QCheckBox("채우기")
        self.fill_chk.setChecked(self.canvas.fill)
        self.fill_chk.toggled.connect(self._set_fill)
        tt.addWidget(self.fill_chk)
        tt.addWidget(QLabel(" 번호 "))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(1, 999)
        self.num_spin.setToolTip("다음에 찍을 번호")
        self.num_spin.valueChanged.connect(lambda v: setattr(self.canvas, "counter", v))
        tt.addWidget(self.num_spin)
        self._update_color_btn()

    def _build_status(self):
        sb = self.statusBar()
        self.size_label = QLabel()
        self.zoom_label = QLabel()
        self.pos_label = QLabel()
        self.file_label = QLabel()
        sb.addWidget(self.size_label)
        sb.addWidget(QLabel("|"))
        sb.addWidget(self.zoom_label)
        sb.addWidget(QLabel("|"))
        sb.addWidget(self.pos_label)
        sb.addPermanentWidget(self.file_label)

    def _fit_window(self):
        scr = self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()
        img = self.canvas.img
        chrome_w, chrome_h = 40, 150
        w = min(max(img.width() + chrome_w, 760), int(scr.width() * 0.9))
        h = min(max(img.height() + chrome_h, 480), int(scr.height() * 0.9))
        self.resize(w, h)
        self.move(scr.center() - QPoint(w // 2, h // 2))

    # ------------------------------------------------------------ tool options
    def _select_tool(self, key):
        self.tool_actions[key].setChecked(True)
        self.canvas.set_tool(key)
        self.canvas.setFocus()

    def _set_color(self, c):
        self.canvas.commit_text()
        self.canvas.color = c
        self.cfg.set("editor/color", c.name())
        self._update_color_btn()

    def _pick_color(self):
        c = QColorDialog.getColor(self.canvas.color, self, "색 선택")
        if c.isValid():
            self._set_color(c)

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(f"QToolButton{{background:{self.canvas.color.name()};"
                                     f"border:2px solid #1B365D;border-radius:3px}}")

    def _set_width(self, v):
        self.canvas.width_ = v
        self.cfg.set("editor/width", v)

    def _set_font(self, v):
        self.canvas.font_size = v
        self.cfg.set("editor/font_size", v)

    def _set_fill(self, v):
        self.canvas.fill = v
        self.cfg.set("editor/fill", v)

    # ------------------------------------------------------------ zoom
    def zoom_step(self, direction):
        z = self.canvas.zoom
        if direction > 0:
            nz = next((s for s in ZOOMS if s > z + 1e-6), ZOOMS[-1])
        else:
            nz = next((s for s in reversed(ZOOMS) if s < z - 1e-6), ZOOMS[0])
        self.canvas.set_zoom(nz)

    def zoom_fit(self):
        vp = self.scroll.viewport().size()
        img = self.canvas.img
        z = min((vp.width() - 4) / img.width(), (vp.height() - 4) / img.height(), 1.0)
        self.canvas.set_zoom(z)

    # ------------------------------------------------------------ refresh
    def _refresh(self):
        img = self.canvas.img
        self.size_label.setText(f"{img.width()} x {img.height()} px")
        self.zoom_label.setText(f"{round(self.canvas.zoom * 100)}%")
        self.a_undo.setEnabled(bool(self.canvas.undo_stack))
        self.a_redo.setEnabled(bool(self.canvas.redo_stack))
        self.num_spin.blockSignals(True)
        self.num_spin.setValue(self.canvas.counter)
        self.num_spin.blockSignals(False)
        name = os.path.basename(self.saved_path) if self.saved_path else self.base_title
        mark = " *" if self.canvas.modified else ""
        self.setWindowTitle(f"{name}{mark} - 다캡처")
        self.file_label.setText(self.saved_path or "저장되지 않음")

    # ------------------------------------------------------------ file ops
    def _write(self, path):
        img = self.canvas.final_image()
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        fmt = {"jpg": "JPG", "jpeg": "JPG", "bmp": "BMP", "png": "PNG"}.get(ext, "PNG")
        out = img.convertToFormat(QImage.Format.Format_RGB32) if fmt in ("JPG", "BMP") else img
        quality = self.cfg.get("save/jpg_quality") if fmt == "JPG" else -1
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not out.save(path, fmt, quality):
            QMessageBox.warning(self, "저장 실패", f"파일을 저장할 수 없습니다.\n{path}")
            return False
        self.saved_path = path
        self.canvas.modified = False
        self._refresh()
        self.statusBar().showMessage(f"저장됨: {path}", 4000)
        return True

    def save(self):
        if self.saved_path:
            return self._write(self.saved_path)
        return self.save_as()

    def save_as(self):
        start = self.saved_path or self.cfg.make_filename()
        filters = "PNG 이미지 (*.png);;JPG 이미지 (*.jpg *.jpeg);;BMP 이미지 (*.bmp)"
        ext = os.path.splitext(start)[1].lower().lstrip(".")
        sel = {"jpg": "JPG 이미지 (*.jpg *.jpeg)", "bmp": "BMP 이미지 (*.bmp)"}.get(ext, "PNG 이미지 (*.png)")
        path, chosen = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", start, filters, sel)
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ".jpg" if chosen.startswith("JPG") else ".bmp" if chosen.startswith("BMP") else ".png"
        return self._write(path)

    def copy(self):
        if self.canvas.text_edit and self.canvas.text_edit.hasFocus():
            self.canvas.text_edit.copy()
            return
        QApplication.clipboard().setImage(self.canvas.final_image())
        self.statusBar().showMessage("클립보드에 복사했습니다.", 3000)

    def print_image(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        img = self.canvas.final_image()
        p = QPainter(printer)
        page = printer.pageLayout().paintRectPixels(printer.resolution())
        target = QSize(img.size())
        target.scale(page.size(), Qt.AspectRatioMode.KeepAspectRatio)
        if img.width() <= page.width() and img.height() <= page.height():
            dpi_scale = printer.resolution() / 96.0
            scaled = QSize(int(img.width() * dpi_scale), int(img.height() * dpi_scale))
            if scaled.width() <= page.width() and scaled.height() <= page.height():
                target = scaled
        p.drawImage(QRect(QPoint(0, 0), target), img)
        p.end()

    def open_file(self):
        self.ctrl.open_image_dialog(self)

    def _escape(self):
        if self.canvas.text_edit:
            self.canvas.commit_text()
            self.canvas.setFocus()
        else:
            self.close()

    def tool_key(self, key):
        tool = self.tool_keys.get(key)
        if tool:
            self._select_tool(tool)
            return True
        return False

    def closeEvent(self, e):
        self.canvas.commit_text()
        if self.canvas.modified:
            r = QMessageBox.question(self, "다캡처", "변경 내용을 저장할까요?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                     | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel or (r == QMessageBox.StandardButton.Save and not self.save()):
                e.ignore()
                return
        self.closed.emit(self)
        e.accept()
