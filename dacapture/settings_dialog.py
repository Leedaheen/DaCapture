"""환경 설정 대화상자."""
import os

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import icons
from .config import DEFAULT_HOTKEYS, MODE_NAMES, MODES, SAVE_FORMATS
from .hotkeys import seq_to_win


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
        grid.addWidget(QLabel("입력란을 클릭한 뒤 원하는 키 조합을 누르세요."), 0, 0, 1, 3)
        self._key_edits = {}
        for row, mode in enumerate(MODES, start=1):
            grid.addWidget(QLabel(MODE_NAMES[mode]), row, 0)
            ed = QKeySequenceEdit(QKeySequence(self.cfg.hotkey(mode), QKeySequence.SequenceFormat.PortableText))
            try:
                ed.setMaximumSequenceLength(1)
            except AttributeError:
                pass
            grid.addWidget(ed, row, 1)
            clear = QPushButton("지우기")
            clear.clicked.connect(ed.clear)
            grid.addWidget(clear, row, 2)
            self._key_edits[mode] = ed
        reset = QPushButton("기본값으로")
        reset.clicked.connect(self._reset_hotkeys)
        grid.addWidget(reset, len(MODES) + 1, 2)
        grid.setRowStretch(len(MODES) + 2, 1)
        return w

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
            ed.setKeySequence(QKeySequence(DEFAULT_HOTKEYS[mode], QKeySequence.SequenceFormat.PortableText))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self.dir_edit.text())
        if d:
            self.dir_edit.setText(os.path.normpath(d))

    def _accept(self):
        seqs = {}
        for mode, ed in self._key_edits.items():
            s = ed.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            if s and not seq_to_win(s):
                QMessageBox.warning(self, "단축키", f"[{MODE_NAMES[mode]}] '{s}' 는 사용할 수 없는 키입니다.")
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
