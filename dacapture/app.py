"""애플리케이션 진입점: 메인 창, 트레이, 캡처 흐름 제어."""
import os
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")   # Qt 좌표 = 물리 픽셀

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QImage, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

from . import APP_TITLE, __version__, grabber, icons, winapi
from .config import MODE_NAMES, MODES, Config
from .editor import EditorWindow
from .hotkeys import HotkeyManager
from .overlay import CaptureOverlay
from .scroll import ScrollCapture
from .settings_dialog import SettingsDialog

SERVER_NAME = "DaCapture-single-instance"

STYLE = """
QMainWindow, QDialog { background: #F4F6FA; }
QToolBar { background: #FFFFFF; border: none; border-bottom: 1px solid #DCE1EA; spacing: 2px; padding: 3px; }
QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 3px; color: #3D3D3D; }
QToolButton:hover { background: #E6ECF5; border-color: #C5D0E2; }
QToolButton:checked { background: #D3DEEF; border: 1px solid #1B365D; }
QToolButton:pressed { background: #C5D0E2; }
QStatusBar { background: #FFFFFF; color: #3D3D3D; border-top: 1px solid #DCE1EA; }
QToolButton#modeButton { background: #FFFFFF; border: 1px solid #DCE1EA; border-radius: 6px;
    padding: 6px 2px; font-size: 12px; color: #1B365D; }
QToolButton#modeButton:hover { background: #E6ECF5; border-color: #1B365D; }
QToolButton#smallButton { color: #3D3D3D; }
QLabel#title { color: #1B365D; font-size: 15px; font-weight: bold; }
QLabel#hint { color: #6B7280; font-size: 11px; }
QPushButton { background: #1B365D; color: white; border: none; border-radius: 4px; padding: 5px 14px; }
QPushButton:hover { background: #24477A; }
QTabWidget::pane { border: 1px solid #DCE1EA; background: white; }
"""


class MainWindow(QMainWindow):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle(f"{APP_TITLE} {__version__}")
        self.setWindowIcon(icons.icon("app"))
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        title = QLabel(f"{APP_TITLE}  DaCapture")
        title.setObjectName("title")
        lay.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.mode_buttons = {}
        for i, mode in enumerate(MODES):
            b = QToolButton()
            b.setObjectName("modeButton")
            b.setIcon(icons.icon(mode))
            b.setIconSize(icons.pixmap(mode, 34).size())
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedSize(92, 78)
            b.clicked.connect(lambda _=False, m=mode: ctrl.capture(m))
            grid.addWidget(b, i // 3, i % 3)
            self.mode_buttons[mode] = b
        lay.addLayout(grid)

        bottom = QGridLayout()
        for col, (name, text, slot) in enumerate((
                ("open", "이미지 열기", lambda: ctrl.open_image_dialog(self)),
                ("clipboard", "클립보드 편집", ctrl.edit_clipboard),
                ("folder", "저장 폴더", ctrl.open_save_dir),
                ("settings", "설정", ctrl.show_settings))):
            b = QToolButton()
            b.setObjectName("smallButton")
            b.setIcon(icons.icon(name))
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.clicked.connect(slot)
            bottom.addWidget(b, 0, col)
        lay.addLayout(bottom)

        hint = QLabel("창을 닫아도 트레이에서 계속 실행됩니다.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

        self.setCentralWidget(central)
        self.refresh_labels()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def refresh_labels(self):
        for mode, b in self.mode_buttons.items():
            seq = self.ctrl.cfg.hotkey(mode)
            native = QKeySequence(seq, QKeySequence.SequenceFormat.PortableText).toString(
                QKeySequence.SequenceFormat.NativeText) if seq else ""
            b.setText(MODE_NAMES[mode])
            b.setToolTip(f"{MODE_NAMES[mode]}" + (f"  ({native})" if native else ""))

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.ctrl.notify_tray_once()


class Controller(QObject):
    def __init__(self, app, cfg):
        super().__init__()
        self.app = app
        self.cfg = cfg
        self.busy = False
        self.restore_main = False
        self.editors = []
        self.overlay = None
        self.scroller = None
        self.uia = winapi.UIAutomation()

        self.main = MainWindow(self)
        self.tray = QSystemTrayIcon(icons.icon("app"), self)
        self.tray.setToolTip(f"{APP_TITLE} - 화면 캡처")
        self.tray_menu = QMenu()
        self._build_tray_menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.hotkeys = HotkeyManager(self.capture)
        self.apply_hotkeys(initial=True)
        try:
            winapi.set_autostart(self.cfg.get("general/autostart"))
        except OSError:
            pass

    # ------------------------------------------------------------ menus
    def build_capture_menu(self, parent=None):
        menu = QMenu(parent)
        for mode in MODES:
            a = menu.addAction(icons.icon(mode), MODE_NAMES[mode])
            seq = self.cfg.hotkey(mode)
            if seq:
                a.setShortcut(QKeySequence(seq, QKeySequence.SequenceFormat.PortableText))
                a.setShortcutVisibleInContextMenu(True)
                a.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            a.triggered.connect(lambda _=False, m=mode: self.capture(m))
        return menu

    def _build_tray_menu(self):
        m = self.tray_menu
        m.clear()
        for a in self.build_capture_menu(m).actions():
            a.setParent(m)
            m.addAction(a)
        m.addSeparator()
        m.addAction(icons.icon("open"), "이미지 열기...", lambda: self.open_image_dialog(None))
        m.addAction(icons.icon("clipboard"), "클립보드 이미지 편집", self.edit_clipboard)
        m.addAction(icons.icon("folder"), "저장 폴더 열기", self.open_save_dir)
        m.addSeparator()
        m.addAction(icons.icon("app"), "메인 창 보기", self.show_main)
        m.addAction(icons.icon("settings"), "환경 설정...", self.show_settings)
        m.addAction("정보", self.about)
        m.addSeparator()
        m.addAction("종료", self.quit)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_main()

    def notify_tray_once(self):
        if not self.cfg.get("general/tray_notice_shown"):
            self.cfg.set("general/tray_notice_shown", True)
            self.tray.showMessage(APP_TITLE, "트레이에서 계속 실행 중입니다. 단축키로 바로 캡처할 수 있습니다.",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    def apply_hotkeys(self, initial=False):
        failed = self.hotkeys.register_all(self.cfg.hotkeys())
        self.main.refresh_labels()
        self._build_tray_menu()
        if failed:
            names = ", ".join(f"{MODE_NAMES[m]}({s})" for m, s in failed)
            self.tray.showMessage(APP_TITLE, f"단축키를 등록하지 못했습니다 (다른 프로그램이 사용 중): {names}",
                                  QSystemTrayIcon.MessageIcon.Warning, 6000)

    # ------------------------------------------------------------ windows
    def show_main(self):
        self.main.show()
        self.main.setWindowState(self.main.windowState() & ~Qt.WindowState.WindowMinimized)
        self.main.raise_()
        self.main.activateWindow()

    def show_settings(self):
        dlg = SettingsDialog(self.cfg, self.main if self.main.isVisible() else None)
        if dlg.exec():
            self.apply_hotkeys()
            try:
                winapi.set_autostart(self.cfg.get("general/autostart"))
            except OSError as ex:
                QMessageBox.warning(None, APP_TITLE, f"자동 실행 설정 실패: {ex}")

    def about(self):
        QMessageBox.about(None, f"{APP_TITLE} 정보",
                          f"<b>{APP_TITLE} (DaCapture) {__version__}</b><br><br>"
                          "Windows 화면 캡처 도구<br>"
                          "직접 지정 / 창 / 단위 영역 / 전체 화면 / 스크롤 / 지정 사이즈 캡처")

    def open_save_dir(self):
        d = self.cfg.get("save/dir")
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def open_editor(self, image, title=None, path=None):
        ed = EditorWindow(self, image, title, path)
        ed.closed.connect(lambda w: self.editors.remove(w) if w in self.editors else None)
        self.editors.append(ed)
        ed.show()
        ed.raise_()
        ed.activateWindow()
        winapi.force_foreground(int(ed.winId()))
        return ed

    def open_image_dialog(self, parent):
        path, _ = QFileDialog.getOpenFileName(parent, "이미지 열기", self.cfg.get("save/dir"),
                                              "이미지 (*.png *.jpg *.jpeg *.bmp *.gif);;모든 파일 (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(None, APP_TITLE, f"이미지를 열 수 없습니다.\n{path}")
            return
        self.open_editor(img, os.path.basename(path), path)

    def edit_clipboard(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            self.tray.showMessage(APP_TITLE, "클립보드에 이미지가 없습니다.", QSystemTrayIcon.MessageIcon.Information,
                                  3000)
            return
        self.open_editor(img, "클립보드 이미지")

    # ------------------------------------------------------------ capture flow
    def capture(self, mode):
        if self.busy or mode not in MODES:
            return
        self.busy = True
        delay = 0
        self.restore_main = False
        if self.main.isVisible() and self.cfg.get("general/hide_main"):
            self.restore_main = not self.main.isMinimized()
            self.main.hide()
            delay = 220
        QTimer.singleShot(delay or 10, lambda: self._do_capture(mode))

    def _do_capture(self, mode):
        try:
            if mode == "full":
                if self.cfg.get("capture/full_all"):
                    img, _ = grabber.grab_virtual()
                else:
                    pos = QCursor.pos()
                    rect = next((m for m in grabber.monitors() if m.contains(pos)), None) or grabber.virtual_rect()
                    img = grabber.grab_rect(rect)
                self._finish(img, mode)
                return
            windows = winapi.list_windows()
            shot, vrect = grabber.grab_virtual()
            self.overlay = CaptureOverlay(mode, self.cfg, shot, vrect, windows, self.uia)
            self.overlay.finished.connect(self._overlay_done)
            self.overlay.start()
        except Exception as ex:
            self._end()
            QMessageBox.critical(None, APP_TITLE, f"캡처 중 오류가 발생했습니다.\n{ex}")

    def _overlay_done(self, result):
        self.overlay = None
        if result is None:
            self._end()
            return
        if result["mode"] == "scroll":
            self.scroller = ScrollCapture(result["rect"], result["point"], self.cfg)
            self.scroller.finished.connect(lambda img: self._finish(img, "scroll"))
            QTimer.singleShot(120, self.scroller.start)
            return
        self._finish(result["image"], result["mode"])

    def _finish(self, img, mode):
        self.scroller = None
        self._end()
        if img is None or img.isNull():
            return
        saved = None
        if self.cfg.get("general/copy_clipboard"):
            QApplication.clipboard().setImage(img)
        if self.cfg.get("save/auto"):
            saved = self.cfg.make_filename()
            os.makedirs(os.path.dirname(saved), exist_ok=True)
            fmt = self.cfg.get("save/format").upper()
            out = img.convertToFormat(QImage.Format.Format_RGB32) if fmt != "PNG" else img
            if not out.save(saved, fmt, self.cfg.get("save/jpg_quality") if fmt == "JPG" else -1):
                saved = None
        if self.cfg.get("general/open_editor"):
            self.open_editor(img, f"{MODE_NAMES[mode]} 캡처", saved)
        else:
            msg = f"{img.width()} x {img.height()} 캡처 완료"
            if saved:
                msg += f"\n{saved}"
            elif self.cfg.get("general/copy_clipboard"):
                msg += " (클립보드에 복사됨)"
            self.tray.showMessage(APP_TITLE, msg, QSystemTrayIcon.MessageIcon.Information, 2500)

    def _end(self):
        self.busy = False
        if self.restore_main:
            self.restore_main = False
            self.main.show()

    def quit(self):
        for ed in list(self.editors):
            ed.close()
            if ed.isVisible():
                return
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.app.quit()


def _forward_to_running(args):
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(("\n".join(args) or "show").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("DaCapture")
    app.setOrganizationName("DaCapture")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icons.icon("app"))
    font = QFont("Malgun Gothic")
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(STYLE)

    args = [a for a in sys.argv[1:]]
    if _forward_to_running(args or ["show"]):
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    cfg = Config()
    ctrl = Controller(app, cfg)

    def handle_args(argv):
        files = [a for a in argv if not a.startswith("--") and os.path.isfile(a)]
        for f in files:
            ctrl.open_path(f)
        for a in argv:
            if a.startswith("--capture="):
                ctrl.capture(a.split("=", 1)[1])
        if not files and not any(a.startswith("--capture=") for a in argv) and "--tray" not in argv:
            ctrl.show_main()

    def on_conn():
        sock = server.nextPendingConnection()

        def read():
            data = bytes(sock.readAll()).decode("utf-8", "ignore")
            handle_args([] if data == "show" else data.split("\n"))
        sock.readyRead.connect(read)

    server.newConnection.connect(on_conn)

    if "--tray" in args or cfg.get("general/start_tray"):
        handle_args([a for a in args if a != "--tray"] + ["--tray"])
    else:
        handle_args(args)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
