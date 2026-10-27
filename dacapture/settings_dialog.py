"""환경 설정 대화상자."""
import os

from PySide6.QtCore import QKeyCombination, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from . import icons
from .config import DEFAULT_HOTKEYS, MODE_NAMES, MODES, SAVE_FORMATS
from .hotkeys import seq_to_win

_MOD_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr}
_MOD_MASK = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier |
             Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
PRINT_PRESETS = ["Print", "Ctrl+Print", "Shift+Print", "Ctrl+Shift+Print"]


def display_seq(seq):
    """'Ctrl+Print' -> 'Ctrl+Print Screen'"""
    if not seq:
        return ""
    return seq.replace("Print", "Print Screen") if seq.endswith("Print") else seq


class HotkeyEdit(QLineEdit):
    """단축키 입력란. Print Screen 처럼 Windows 가 key-up 만 보내는 키도 받는다."""

    def __init__(self, seq=""):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("여기를 클릭하고 키를 누르세요")
        self._seq = ""
        self.set_seq(seq)

    def seq(self):
        return self._seq

    def set_seq(self, seq):
        self._seq = seq or ""
        self.setText(display_seq(self._seq))

    def clear(self):
        self.set_seq("")

    @staticmethod
    def _mods_text(mods):
        names = ((Qt.KeyboardModifier.ControlModifier, "Ctrl"), (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                 (Qt.KeyboardModifier.AltModifier, "Alt"), (Qt.KeyboardModifier.MetaModifier, "Meta"))
        return "+".join(n for f, n in names if mods & f)

    def _commit(self, key, mods):
        comb = QKeyCombination(Qt.KeyboardModifier(mods & _MOD_MASK), Qt.Key(key))
        self.set_seq(QKeySequence(comb).toString(QKeySequence.SequenceFormat.PortableText))

    def keyPressEvent(self, e):
        key = e.key()
        mods = e.modifiers()
        if key in _MOD_KEYS:
            t = self._mods_text(mods)
            self.setText(t + "+" if t else "")
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Escape) and not (mods & _MOD_MASK):
            self.clear()
            return
        vk = e.nativeVirtualKey()
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # Shift+숫자 등 기호로 바뀐 키를 원래 키로
            key = vk
        if key in (0, Qt.Key.Key_unknown):
            return
        self._commit(key, mods)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Print:  # Windows 는 Print Screen 의 key-down 을 보내지 않음
            self._commit(Qt.Key.Key_Print, e.modifiers())
            return
        if e.key() in _MOD_KEYS and self.text().endswith("+"):
            self.set_seq(self._seq)
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self.set_seq(self._seq)
        super().focusOutEvent(e)


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("환경 설정 - 다캡처")
        self.setWindowIcon(icons.icon("settings"))
        self.setMinimumWidth(500)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "일반")
        tabs.addTab(self._hotkey_tab(), "단축키")
        tabs.addTab(self._save_tab(), "저장")
        tabs.addTab(self._capture_tab(), "캡처")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("확인")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # ------------------------------------------------------------ tabs
    def _check(self, key, text):
        cb = QCheckBox(text)
        cb.setChecked(self.cfg.get(key))
        cb.setProperty("cfg_key", key)
        self._checks.append(cb)
        return cb

    def _general_tab(self):
        self._checks = []
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>캡처 후 동작</b>"))
        lay.addWidget(self._check("general/open_editor", "편집기에서 열기"))
        lay.addWidget(self._check("general/copy_clipboard", "클립보드에 자동 복사"))
        lay.addWidget(QLabel("<b>프로그램</b>"))
        lay.addWidget(self._check("general/hide_main", "캡처할 때 메인 창 숨기기"))
        lay.addWidget(self._check("general/magnifier", "영역 지정 시 돋보기 표시"))
        lay.addWidget(self._check("general/autostart", "Windows 시작 시 자동 실행"))
        lay.addWidget(self._check("general/start_tray", "시작할 때 트레이로 최소화"))
        lay.addStretch()
        return w

    def _hotkey_tab(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.addWidget(QLabel("입력란을 클릭한 뒤 원하는 키 조합을 누르세요. (Backspace: 지우기)\n"
                              "Print Screen 키는 오른쪽 [PrtSc] 버튼으로도 지정할 수 있습니다."), 0, 0, 1, 4)
        self._key_edits = {}
        for row, mode in enumerate(MODES, start=1):
            grid.addWidget(QLabel(MODE_NAMES[mode]), row, 0)
            ed = HotkeyEdit(self.cfg.hotkey(mode))
            grid.addWidget(ed, row, 1)
            prt = QToolButton()
            prt.setText("PrtSc")
            prt.setObjectName("prtButton")
            prt.setToolTip("Print Screen 키 지정")
            prt.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(prt)
            for s in PRINT_PRESETS:
                menu.addAction(display_seq(s), lambda e=ed, s=s: self._set_print(e, s))
            prt.setMenu(menu)
            grid.addWidget(prt, row, 2)
            clear = QPushButton("지우기")
            clear.clicked.connect(ed.clear)
            grid.addWidget(clear, row, 3)
            self._key_edits[mode] = ed
        reset = QPushButton("기본값으로")
        reset.clicked.connect(self._reset_hotkeys)
        grid.addWidget(reset, len(MODES) + 1, 3)
        note = QLabel("Print Screen 키를 눌렀을 때 Windows 캡처 도구가 대신 열리면, Windows 설정에서 "
                      "'Print Screen 키를 사용하여 화면 캡처 열기'를 끄세요.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        grid.addWidget(note, len(MODES) + 2, 0, 1, 4)
        open_win = QPushButton("Windows 키보드 설정 열기")
        open_win.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:easeofaccess-keyboard")))
        grid.addWidget(open_win, len(MODES) + 3, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(len(MODES) + 4, 1)
        return w

    def _set_print(self, ed, seq):
        # 같은 키가 다른 기능에 있으면 그쪽을 비워 중복을 막는다
        for other in self._key_edits.values():
            if other is not ed and other.seq() == seq:
                other.clear()
        ed.set_seq(seq)

    def _save_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(self._check("save/auto", "캡처할 때마다 자동 저장"))
        row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.cfg.get("save/dir"))
        browse = QPushButton("찾아보기...")
        browse.clicked.connect(self._browse)
        row.addWidget(self.dir_edit)
        row.addWidget(browse)
        form.addRow("저장 폴더", row)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems([f.upper() for f in SAVE_FORMATS])
        cur = self.cfg.get("save/format")
        self.fmt_combo.setCurrentIndex(SAVE_FORMATS.index(cur) if cur in SAVE_FORMATS else 0)
        form.addRow("기본 형식", self.fmt_combo)
        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        self.quality.setValue(self.cfg.get("save/jpg_quality"))
        form.addRow("JPG 품질", self.quality)
        self.prefix = QLineEdit(self.cfg.get("save/prefix"))
        form.addRow("파일 이름 앞부분", self.prefix)
        form.addRow("", QLabel("예: 캡처_2026-10-27_143005.png"))
        return w

    def _capture_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        size_row = QHBoxLayout()
        self.fw = QSpinBox()
        self.fw.setRange(10, 10000)
        self.fw.setValue(self.cfg.get("capture/fixed_w"))
        self.fh = QSpinBox()
        self.fh.setRange(10, 10000)
        self.fh.setValue(self.cfg.get("capture/fixed_h"))
        size_row.addWidget(self.fw)
        size_row.addWidget(QLabel("x"))
        size_row.addWidget(self.fh)
        size_row.addStretch()
        form.addRow("지정 사이즈 (px)", size_row)
        form.addRow(self._check("capture/full_all", "전체 화면 캡처 시 모든 모니터 포함"))
        self.scroll_max = QSpinBox()
        self.scroll_max.setRange(1000, 100000)
        self.scroll_max.setSingleStep(1000)
        self.scroll_max.setValue(self.cfg.get("capture/scroll_max"))
        form.addRow("스크롤 캡처 최대 높이 (px)", self.scroll_max)
        self.scroll_delay = QSpinBox()
        self.scroll_delay.setRange(50, 3000)
        self.scroll_delay.setSingleStep(50)
        self.scroll_delay.setValue(self.cfg.get("capture/scroll_delay"))
        form.addRow("스크롤 대기 시간 (ms)", self.scroll_delay)
        form.addRow("", QLabel("웹 페이지가 늦게 그려지면 대기 시간을 늘리세요."))
        return w

    # ------------------------------------------------------------ actions
    def _reset_hotkeys(self):
        for mode, ed in self._key_edits.items():
            ed.set_seq(DEFAULT_HOTKEYS[mode])

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.dir_edit.text())
        if d:
            self.dir_edit.setText(os.path.normpath(d))

    def _accept(self):
        seqs = {}
        for mode, ed in self._key_edits.items():
            s = ed.seq()
            if s and not seq_to_win(s):
                QMessageBox.warning(self, "단축키", f"[{MODE_NAMES[mode]}] '{display_seq(s)}' 는 사용할 수 없는 키입니다.")
                return
            if s == "Alt+Print":
                QMessageBox.warning(self, "단축키", "Alt+Print Screen 은 Windows 가 사용하는 키라 지정할 수 없습니다.")
                return
            seqs[mode] = s
        used = [s for s in seqs.values() if s]
        if len(used) != len(set(used)):
            QMessageBox.warning(self, "단축키", "같은 단축키가 여러 기능에 지정되어 있습니다.")
            return
        for cb in self._checks:
            self.cfg.set(cb.property("cfg_key"), cb.isChecked())
        for mode, s in seqs.items():
            self.cfg.set_hotkey(mode, s)
        self.cfg.set("save/dir", self.dir_edit.text().strip())
        self.cfg.set("save/format", SAVE_FORMATS[self.fmt_combo.currentIndex()])
        self.cfg.set("save/jpg_quality", self.quality.value())
        self.cfg.set("save/prefix", self.prefix.text().strip())
        self.cfg.set("capture/fixed_w", self.fw.value())
        self.cfg.set("capture/fixed_h", self.fh.value())
        self.cfg.set("capture/scroll_max", self.scroll_max.value())
        self.cfg.set("capture/scroll_delay", self.scroll_delay.value())
        self.cfg.sync()
        self.accept()
