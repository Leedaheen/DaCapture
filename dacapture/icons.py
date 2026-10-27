"""코드로 그리는 벡터 아이콘 (외부 리소스 없음)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)

NAVY = QColor("#1B365D")
RED = QColor("#E8192C")
GRAY = QColor("#3D3D3D")
WHITE = QColor("#FFFFFF")

_cache = {}


def _pen(color=NAVY, w=2.2, style=Qt.PenStyle.SolidLine):
    p = QPen(color, w, style)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _arrow_head(p, tip, angle, size, color):
    a1 = angle + math.pi - math.pi / 7
    a2 = angle + math.pi + math.pi / 7
    poly = QPolygonF([tip,
                      QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
                      QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2))])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(poly)


# ---- 각 아이콘은 32x32 좌표계에 그린다 ----
def _app(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(NAVY)
    p.drawRoundedRect(QRectF(1, 1, 30, 30), 7, 7)
    p.setPen(_pen(WHITE, 2.6))
    for x, y, dx, dy in ((7, 7, 1, 1), (25, 7, -1, 1), (7, 25, 1, -1), (25, 25, -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + 6 * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + 6 * dy))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(RED)
    p.drawEllipse(QPointF(16, 16), 4.5, 4.5)


def _region(p):
    p.setPen(_pen(NAVY, 2, Qt.PenStyle.DashLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 6, 20, 16))
    p.setPen(_pen(RED, 2.2))
    p.drawLine(QPointF(24, 18), QPointF(24, 30))
    p.drawLine(QPointF(18, 24), QPointF(30, 24))


def _window(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(3, 5, 26, 22), 2, 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(NAVY)
    p.drawRect(QRectF(3, 5, 26, 6))
    p.setBrush(RED)
    p.drawEllipse(QPointF(25, 8), 1.6, 1.6)


def _element(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3, 4, 26, 24), 2, 2)
    p.drawLine(QPointF(3, 10), QPointF(29, 10))
    p.setPen(_pen(RED, 2.2))
    p.setBrush(QColor(232, 25, 44, 50))
    p.drawRect(QRectF(8, 14, 16, 9))


def _full(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(3, 4, 26, 18), 2, 2)
    p.drawLine(QPointF(16, 22), QPointF(16, 27))
    p.drawLine(QPointF(10, 28), QPointF(22, 28))
    p.setPen(_pen(RED, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(7, 8, 18, 10))


def _scroll(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(5, 2, 16, 28), 2, 2)
    for y in (8, 13, 18, 23):
        p.drawLine(QPointF(9, y), QPointF(17, y))
    p.setPen(_pen(RED, 2.4))
    p.drawLine(QPointF(26, 8), QPointF(26, 24))
    _arrow_head(p, QPointF(26, 29), math.pi / 2, 7, RED)


def _fixed(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4, 4, 24, 18))
    p.setPen(_pen(RED, 1.8))
    p.drawLine(QPointF(7, 27), QPointF(25, 27))
    _arrow_head(p, QPointF(4, 27), math.pi, 5, RED)
    _arrow_head(p, QPointF(28, 27), 0, 5, RED)


def _pen_tool(p):
    path = QPainterPath()
    path.moveTo(6, 26)
    path.lineTo(9, 19)
    path.lineTo(23, 5)
    path.lineTo(27, 9)
    path.lineTo(13, 23)
    path.closeSubpath()
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawPath(path)
    p.drawLine(QPointF(20, 8), QPointF(24, 12))


def _highlight(p):
    p.setPen(_pen(QColor(255, 210, 0), 7))
    p.drawLine(QPointF(5, 24), QPointF(27, 24))
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRect(QRectF(13, 4, 8, 12))
    p.drawLine(QPointF(15, 16), QPointF(15, 20))
    p.drawLine(QPointF(19, 16), QPointF(19, 20))


def _line(p):
    p.setPen(_pen(NAVY, 2.6))
    p.drawLine(QPointF(5, 27), QPointF(27, 5))


def _arrow(p):
    p.setPen(_pen(NAVY, 2.6))
    p.drawLine(QPointF(5, 27), QPointF(22, 10))
    _arrow_head(p, QPointF(27, 5), -math.pi / 4, 11, NAVY)


def _rect(p):
    p.setPen(_pen(NAVY, 2.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(5, 7, 22, 18))


def _ellipse(p):
    p.setPen(_pen(NAVY, 2.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(4, 7, 24, 18))


def _text(p):
    f = QFont("Malgun Gothic")
    f.setPixelSize(24)
    f.setBold(True)
    p.setFont(f)
    p.setPen(NAVY)
    p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "T")


def _number(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(RED)
    p.drawEllipse(QPointF(16, 16), 12, 12)
    f = QFont("Malgun Gothic")
    f.setPixelSize(15)
    f.setBold(True)
    p.setFont(f)
    p.setPen(WHITE)
    p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "1")


def _mosaic(p):
    shades = [QColor("#1B365D"), QColor("#6F86A8"), QColor("#B8C4D6"), QColor("#3D3D3D")]
    for i in range(4):
        for j in range(4):
            p.fillRect(QRectF(4 + i * 6, 4 + j * 6, 6, 6), shades[(i * 3 + j) % 4])


def _crop(p):
    p.setPen(_pen(NAVY, 2.6))
    p.drawLine(QPointF(9, 3), QPointF(9, 23))
    p.drawLine(QPointF(9, 23), QPointF(29, 23))
    p.drawLine(QPointF(3, 9), QPointF(23, 9))
    p.drawLine(QPointF(23, 9), QPointF(23, 29))


def _hand(p):
    p.setPen(_pen(NAVY, 2.2))
    p.drawLine(QPointF(16, 4), QPointF(16, 28))
    p.drawLine(QPointF(4, 16), QPointF(28, 16))
    for ang, tip in ((-math.pi / 2, (16, 3)), (math.pi / 2, (16, 29)), (math.pi, (3, 16)), (0, (29, 16))):
        _arrow_head(p, QPointF(*tip), ang, 7, NAVY)


def _curve_arrow(p, mirror):
    p.save()
    if mirror:
        p.translate(32, 0)
        p.scale(-1, 1)
    path = QPainterPath()
    path.moveTo(9, 13)
    path.cubicTo(17, 5, 29, 9, 26, 20)
    path.cubicTo(24, 26, 18, 27, 13, 26)
    p.setPen(_pen(NAVY, 2.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    _arrow_head(p, QPointF(5, 16), math.pi * 0.83, 10, NAVY)
    p.restore()


def _undo(p):
    _curve_arrow(p, False)


def _redo(p):
    _curve_arrow(p, True)


def _save(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(4, 4, 24, 24), 2, 2)
    p.setBrush(NAVY)
    p.drawRect(QRectF(9, 4, 13, 8))
    p.setBrush(WHITE)
    p.drawRect(QRectF(8, 17, 16, 11))


def _save_as(p):
    _save(p)
    p.setPen(_pen(RED, 2.2))
    p.drawLine(QPointF(22, 30), QPointF(30, 22))


def _copy(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(4, 4, 16, 19), 2, 2)
    p.drawRoundedRect(QRectF(12, 10, 16, 19), 2, 2)


def _print(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRect(QRectF(9, 3, 14, 9))
    p.drawRoundedRect(QRectF(3, 11, 26, 12), 2, 2)
    p.drawRect(QRectF(9, 19, 14, 10))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(RED)
    p.drawEllipse(QPointF(24, 15), 1.5, 1.5)


def _zoom(p, plus):
    p.setPen(_pen(NAVY, 2.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(13, 13), 9, 9)
    p.drawLine(QPointF(20, 20), QPointF(28, 28))
    p.drawLine(QPointF(9, 13), QPointF(17, 13))
    if plus:
        p.drawLine(QPointF(13, 9), QPointF(13, 17))


def _zoom_in(p):
    _zoom(p, True)


def _zoom_out(p):
    _zoom(p, False)


def _fit(p):
    p.setPen(_pen(NAVY, 2.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(5, 5, 22, 22))
    p.setPen(_pen(RED, 2.2))
    p.drawRect(QRectF(11, 11, 10, 10))


def _actual(p):
    f = QFont("Malgun Gothic")
    f.setPixelSize(13)
    f.setBold(True)
    p.setFont(f)
    p.setPen(NAVY)
    p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "1:1")


def _open(p):
    path = QPainterPath()
    path.moveTo(3, 8)
    path.lineTo(12, 8)
    path.lineTo(15, 11)
    path.lineTo(29, 11)
    path.lineTo(29, 26)
    path.lineTo(3, 26)
    path.closeSubpath()
    p.setPen(_pen(NAVY, 2))
    p.setBrush(QColor("#E9EEF5"))
    p.drawPath(path)


def _settings(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(NAVY)
    path = QPainterPath()
    for i in range(8):
        a = i * math.pi / 4
        c = QPointF(16 + 11 * math.cos(a), 16 + 11 * math.sin(a))
        path.addEllipse(c, 3.2, 3.2)
    path.addEllipse(QPointF(16, 16), 10, 10)
    p.drawPath(path.simplified())
    p.setBrush(WHITE)
    p.drawEllipse(QPointF(16, 16), 4.5, 4.5)


def _clipboard(p):
    p.setPen(_pen(NAVY, 2))
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(6, 5, 20, 24), 2, 2)
    p.setBrush(NAVY)
    p.drawRoundedRect(QRectF(11, 2, 10, 6), 2, 2)
    p.setPen(_pen(RED, 1.8))
    for y in (14, 19, 24):
        p.drawLine(QPointF(10, y), QPointF(22, y))


def _folder_open(p):
    _open(p)
    p.setPen(_pen(RED, 2.2))
    p.drawLine(QPointF(16, 23), QPointF(16, 14))
    _arrow_head(p, QPointF(16, 13), -math.pi / 2, 6, RED)


_DRAW = dict(
    app=_app, region=_region, window=_window, element=_element, full=_full, scroll=_scroll, fixed=_fixed,
    pen=_pen_tool, highlight=_highlight, line=_line, arrow=_arrow, rect=_rect, ellipse=_ellipse, text=_text,
    number=_number, mosaic=_mosaic, crop=_crop, hand=_hand, undo=_undo, redo=_redo, save=_save,
    save_as=_save_as, copy=_copy, print=_print, zoom_in=_zoom_in, zoom_out=_zoom_out, fit=_fit,
    actual=_actual, open=_open, settings=_settings, clipboard=_clipboard, folder=_folder_open)


def pixmap(name, size=32):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(size / 32.0, size / 32.0)
    _DRAW[name](p)
    p.end()
    return pm


def icon(name):
    if name not in _cache:
        ic = QIcon()
        for s in (16, 20, 24, 32, 48, 64, 128, 256):
            ic.addPixmap(pixmap(name, s))
        _cache[name] = ic
    return _cache[name]
