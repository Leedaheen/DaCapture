"""앱 아이콘(.ico) 생성: python tools/make_icon.py assets/dacapture.ico"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QGuiApplication

from dacapture import icons

app = QGuiApplication(sys.argv)
out = sys.argv[1] if len(sys.argv) > 1 else "assets/dacapture.ico"
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
ok = icons.pixmap("app", 256).save(out, "ICO")
print("icon", out, ok)
sys.exit(0 if ok else 1)
