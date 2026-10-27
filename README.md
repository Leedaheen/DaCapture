# 다캡처 (DaCapture)

Windows용 화면 캡처 프로그램입니다. 단축키 한 번으로 원하는 영역을 캡처하고, 바로 편집기에서 표시/저장/복사할 수 있습니다.

## 다운로드

[Releases](../../releases) 에서 `DaCapture.exe` 를 받아 실행하면 됩니다. 설치가 필요 없는 단일 실행 파일입니다.

## 캡처 방식

| 기능 | 기본 단축키 | 설명 |
|------|------------|------|
| 직접 지정 | `Ctrl+Shift+C` | 드래그로 영역 지정. 드래그 없이 클릭하면 마우스 아래 창 캡처 |
| 창 캡처 | `Ctrl+Shift+W` | 마우스를 올린 창을 강조 표시, 클릭하면 캡처 |
| 단위 영역 | `Ctrl+Shift+D` | 버튼, 패널, 목록 등 UI 요소 단위 자동 감지. 마우스 휠로 상위/하위 영역 이동 |
| 전체 화면 | `Ctrl+Shift+A` | 마우스가 있는 모니터 전체 (설정에서 모든 모니터 선택 가능) |
| 스크롤 캡처 | `Ctrl+Shift+S` | 스크롤 영역을 클릭하면 자동으로 스크롤하며 긴 이미지로 이어 붙임. ESC로 중지 |
| 지정 사이즈 | `Ctrl+Shift+Z` | 설정한 크기(기본 800x600)의 사각형을 클릭 위치에 캡처 |

단축키는 **설정 > 단축키** 에서 바꿀 수 있습니다. Print Screen 키(단독, Ctrl/Shift 조합)도 지정할 수 있으며,
입력란에서 직접 누르거나 옆의 [PrtSc] 버튼으로 고르면 됩니다. Print Screen 을 눌렀을 때 Windows 캡처 도구가 대신 열리면
Windows 설정 > 접근성 > 키보드 에서 "Print Screen 키를 사용하여 화면 캡처 열기"를 끄세요.

영역 선택 화면 공통 조작
- 돋보기: 커서 주변 8배 확대, 좌표와 RGB 색상 표시
- 방향키: 커서 1px 이동 (Shift: 10px)
- Enter: 현재 영역으로 캡처
- ESC / 우클릭: 취소

## 편집기

캡처가 끝나면 편집기가 열리고 이미지는 자동으로 클립보드에도 복사됩니다.

| 도구 | 키 | 도구 | 키 |
|------|----|------|----|
| 이동(손) | H | 사각형 | R |
| 펜 | P | 원 | E |
| 형광펜 | G | 텍스트 | T |
| 직선 | L | 번호 마커 | N |
| 화살표 | A | 모자이크 | M |
| 자르기 | C | | |

- Shift + 드래그: 직선/화살표 45도 고정, 사각형/원 정사각형
- 색상 팔레트, 굵기, 글자 크기, 도형 채우기, 번호 시작값 설정
- `Ctrl+Z` / `Ctrl+Y` 실행 취소/다시 실행, `Ctrl+S` 저장, `Ctrl+C` 복사, `Ctrl+P` 인쇄
- `Ctrl+휠` 확대/축소, `Ctrl+0` 실제 크기, `Ctrl+9` 창에 맞춤
- PNG / JPG / BMP 저장

## 기타 기능

- 트레이 상주: 창을 닫아도 트레이에서 단축키 대기
- 자동 저장: 캡처할 때마다 지정 폴더에 자동 저장 (기본: `사진\DaCapture`)
- Windows 시작 시 자동 실행
- 이미지 파일 열기 / 클립보드 이미지 편집
- 멀티 모니터, 고해상도(DPI 배율) 환경 지원

설정 파일 위치: `%APPDATA%\DaCapture\DaCapture.ini`

## 직접 빌드

Python 3.11 이상 필요.

```powershell
.\build.ps1
```

결과물: `dist\DaCapture.exe`

소스에서 바로 실행:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

## 구조

```
dacapture/
  app.py              메인 창, 트레이, 캡처 흐름 제어, 단일 실행
  overlay.py          영역/창/단위영역/지정사이즈 선택 오버레이 + 돋보기
  scroll.py           스크롤 캡처 (자동 휠 스크롤 + 이미지 이어 붙이기)
  editor.py           이미지 편집기
  winapi.py           Win32, DWM, UI Automation 래퍼
  hotkeys.py          전역 단축키 (RegisterHotKey)
  grabber.py          화면 이미지 획득 (mss)
  settings_dialog.py  환경 설정
  config.py           설정 저장
  icons.py            벡터 아이콘
```
