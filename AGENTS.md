# Agent Guide: td5m_app_webview

## Project Overview

TDS530 TCP Logger — a PyWebView-based native desktop application that receives and displays real-time measurement data from a TDS530 device over TCP.

- **Language**: Python 3.13.11
- **Package manager**: `uv` (strongly preferred; `conda` is the next best option)
- **UI framework**: PyWebView with a single-page HTML/JS frontend (`www/index.html`)
- **Build tool**: PyInstaller (`TDS530Logger.spec`)

## Directory Layout

```
.
├── main.py              # Application entry point; TCP collector; pywebview API
├── calibration.py       # Quadratic calibration store (calibration.json)
├── units.py             # Unit-label store (units.json)
├── www/
│   ├── index.html       # Main UI (HTML + inline JS + Tailwind CSS classes)
│   ├── chart.min.js     # Chart.js library
│   └── tailwind.min.js  # Tailwind CSS CDN script
├── TDS530Logger.spec    # PyInstaller spec
├── pyproject.toml
├── temp/                # Preview/test output directory (gitignored)
├── calibration.json     # Runtime-generated calibration config
└── units.json           # Runtime-generated unit config
```

## How to Run

```bash
uv run python main.py
```

A native window opens at 1900x1000 showing the data monitor. The app tries to connect to the TDS530 at `192.168.100.100:4242`.

## How to Build

```bash
uv run pyinstaller TDS530Logger.spec --noconfirm
```

The executable is produced in `dist/TDS530Logger.exe`.

## Coding Conventions

- Keep changes minimal and follow the existing style.
- Frontend code lives in `www/index.html` as inline JavaScript; avoid adding extra JS files unless necessary.
- Tailwind CSS utility classes are used for styling.
- Backend API methods exposed to JavaScript are defined on `TDS530Api` in `main.py`.
- Calibration and units are persisted as JSON and managed by dedicated store classes.

## Runtime Config Files

- `calibration.json` — quadratic calibration coefficients for groups `Z`, `X`, `Disp`, `AUX0`..`AUX4`.
- `units.json` — unit labels for the same groups. `Z` and `X` are fixed to `N`, `Disp` is fixed to `mm`; only `AUX0`..`AUX4` are user-editable.

## Preview / Verification

To verify UI changes without running the full app, generate a preview:

1. Create a mocked `temp/index.html` that injects a fake `pywebview.api` and sample data.
2. Render it headlessly with Chrome/Edge and save a screenshot to `temp/preview.png`.

Expected output files:

- `./temp/index.html` — test-renderable HTML
- `./temp/preview.png` — verification screenshot
