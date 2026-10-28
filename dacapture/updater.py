"""GitHub Releases 기반 업데이트 확인 / 다운로드 / exe 교체."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout)

from . import APP_TITLE, __version__, icons

REPO = "Leedaheen/DaCapture"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "DaCapture.exe"
_UA = {"User-Agent": f"DaCapture/{__version__}", "Accept": "application/vnd.github+json"}


def parse_version(tag):
    """'v1.0.2' -> (1, 0, 2)"""
    parts = []
    for p in str(tag).lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def is_newer(tag, current=__version__):
    return parse_version(tag) > parse_version(current)


def fetch_latest(timeout=10):
    """최신 릴리스 정보 {'version', 'notes', 'url', 'size', 'page'} | 실패 시 예외"""
    req = urllib.request.Request(API_LATEST, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.load(r)
    asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET_NAME), None)
    return {
        "version": rel.get("tag_name", "").lstrip("vV"),
        "notes": rel.get("body") or "",
        "url": asset["browser_download_url"] if asset else None,
        "size": asset["size"] if asset else 0,
        "page": rel.get("html_url", f"https://github.com/{REPO}/releases"),
    }


def can_self_update():
    return getattr(sys, "frozen", False) and sys.executable.lower().endswith(".exe")


class UpdateChecker(QObject):
    """백그라운드 스레드에서 최신 버전 확인. result(info|None, error_text)"""
    result = Signal(object, str)

    def check(self):
        def run():
            try:
                self.result.emit(fetch_latest(), "")
            except Exception as ex:  # 네트워크 오류 등
                self.result.emit(None, str(ex))
        threading.Thread(target=run, name="UpdateCheck", daemon=True).start()


class _Downloader(QObject):
    progress = Signal(int, int)
    done = Signal(str, str)  # (path, error)

    def start(self, url, size, dest):
        def run():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _UA["User-Agent"]})
                got = 0
                with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                    total = int(r.headers.get("Content-Length") or size or 0)
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        self.progress.emit(got, total)
                if size and got != size:
                    raise IOError(f"다운로드 크기가 맞지 않습니다 ({got} / {size} bytes)")
                self.done.emit(dest, "")
            except Exception as ex:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                self.done.emit("", str(ex))
        threading.Thread(target=run, name="UpdateDownload", daemon=True).start()


def launch_replacer(new_exe, target_exe, pids):
    """현재 프로세스가 끝나면 target 을 new 로 바꾸고 다시 실행하는 PowerShell 스크립트를 띄운다."""
    q = lambda s: "'" + s.replace("'", "''") + "'"
    ids = ",".join(str(p) for p in pids if p)
    script = f"""$ErrorActionPreference = 'SilentlyContinue'
Wait-Process -Id {ids} -Timeout 30
$src = {q(new_exe)}
$dst = {q(target_exe)}
$ok = $false
for ($i = 0; $i -lt 40; $i++) {{
    try {{ Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop; $ok = $true; break }}
    catch {{ Start-Sleep -Milliseconds 500 }}
}}
if ($ok) {{ Remove-Item -LiteralPath $src -Force }}
Start-Process -FilePath $dst -ArgumentList '--updated'
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force
"""
    ps1 = os.path.join(tempfile.gettempdir(), "DaCapture_update.ps1")
    with open(ps1, "w", encoding="utf-8-sig") as f:
        f.write(script)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", ps1], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class UpdateDialog(QDialog):
    """새 버전 안내 팝업. 업데이트 / 나중에 / 이 버전 건너뛰기"""

    def __init__(self, info, cfg, quit_app, parent=None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint)
        self.info = info
        self.cfg = cfg
        self.quit_app = quit_app
        self.setWindowTitle(f"업데이트 - {APP_TITLE}")
        self.setWindowIcon(icons.icon("app"))
        self.setMinimumWidth(440)

        title = QLabel(f"새 버전 <b>{info['version']}</b> 이(가) 나왔습니다.")
        title.setObjectName("title")
        cur = QLabel(f"현재 버전: {__version__}")
        cur.setObjectName("hint")
        notes = QTextBrowser()
        notes.setMarkdown(info["notes"] or "변경 내용이 없습니다.")
        notes.setOpenExternalLinks(True)
        notes.setMaximumHeight(180)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        self.btn_update = QPushButton("지금 업데이트")
        self.btn_update.setDefault(True)
        self.btn_later = QPushButton("나중에")
        self.btn_skip = QPushButton("이 버전 건너뛰기")
        for b in (self.btn_later, self.btn_skip):
            b.setStyleSheet("QPushButton { background: #FFFFFF; color: #3D3D3D; border: 1px solid #C5D0E2; }"
                            "QPushButton:hover { background: #E6ECF5; }")
        self.btn_update.clicked.connect(self._update)
        self.btn_later.clicked.connect(self.reject)
        self.btn_skip.clicked.connect(self._skip)

        row = QHBoxLayout()
        row.addWidget(self.btn_skip)
        row.addStretch()
        row.addWidget(self.btn_later)
        row.addWidget(self.btn_update)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addWidget(cur)
        lay.addWidget(QLabel("변경 내용"))
        lay.addWidget(notes)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addLayout(row)

        self._dl = None

    def _skip(self):
        self.cfg.set("general/skip_version", self.info["version"])
        self.cfg.sync()
        self.reject()

    def _update(self):
        if not can_self_update() or not self.info.get("url"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self.info["page"]))
            self.accept()
            return
        for b in (self.btn_update, self.btn_later, self.btn_skip):
            b.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.status.setText("다운로드 중...")
        dest = os.path.join(tempfile.gettempdir(), f"DaCapture_{self.info['version']}.exe")
        self._dl = _Downloader()
        self._dl.progress.connect(self._progress)
        self._dl.done.connect(self._downloaded)
        self._dl.start(self.info["url"], self.info["size"], dest)

    def _progress(self, got, total):
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(got)
            self.status.setText(f"다운로드 중... {got / 1048576:.1f} / {total / 1048576:.1f} MB")

    def _downloaded(self, path, err):
        if err:
            self.status.setText(f"다운로드에 실패했습니다. 잠시 후 다시 시도하세요.\n({err})")
            self.bar.setVisible(False)
            for b in (self.btn_update, self.btn_later, self.btn_skip):
                b.setEnabled(True)
            return
        self.status.setText("설치를 위해 프로그램을 다시 시작합니다...")
        self._dl = None
        self.accept()
        # 편집기에 저장 안 한 내용이 있으면 사용자가 취소할 수 있음 -> 그때는 교체하지 않음
        if not self.quit_app(lambda: launch_replacer(path, sys.executable, [os.getpid(), os.getppid()])):
            try:
                os.remove(path)
            except OSError:
                pass

    def closeEvent(self, e):
        if self._dl is not None and not self.btn_later.isEnabled():
            e.ignore()  # 다운로드 중에는 닫지 않음
            return
        super().closeEvent(e)
