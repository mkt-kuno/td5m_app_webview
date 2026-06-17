# Future Plan: Migrate to Wails v2 + Go

## Background

The current application is a Python + pywebview native desktop app. While functional, deployment requires PyInstaller, which is heavy and inconvenient. The goal is to migrate to a backend and build toolchain that can produce small native executables for Windows and Linux easily.

## Decision

**Adopt Wails v2 with Go.**

- Language: Go
- UI framework: Wails v2 (embeds existing HTML/JS/Tailwind/Chart.js frontend)
- Build command: `wails build`
- Target platforms: Windows (amd64) and Linux (amd64)

## Why Wails + Go

| Requirement | Fit |
|---|---|
| Backend language = Go | Yes |
| Cross-platform Windows/Linux | Yes |
| Reuse existing WebUI | Yes, frontend files are embedded as-is |
| Small binary size (< 100 MB) | Yes, typically 10–30 MB |
| Easy executable generation | Yes, `wails build` per platform |
| TCP networking | Yes, Go's standard library is well suited |

Alternatives considered:

- **Tauri (Rust)**: Smaller binaries, but requires Rust, which was not the user's preference.
- **Electron (Node.js)**: Familiar ecosystem, but binaries are large (> 100 MB), defeating the goal.
- **Flutter / .NET MAUI**: Would require rewriting the UI from scratch.

## Project Structure After Migration

```
td5m_app_webview/
├── app.go              # Wails App struct: JS-exposed methods and lifecycle
├── main.go             # Wails entry point
├── tds530.go           # TCP collector and TDS530 protocol parser
├── calibration.go      # calibration.json load/save/apply
├── go.mod              # Go module definition
├── wails.json          # Wails project configuration
├── FUTURE_PLAN.md      # This document
├── README.md           # Updated build/run instructions
├── calibration.json    # Runtime calibration config (next to executable)
└── frontend/           # Embedded web frontend (moved from www/)
    ├── index.html      # Adapted from www/index.html
    ├── chart.min.js
    └── tailwind.min.js
```

## Backend Porting Details

### 1. TDS530 TCP Collector (`tds530.go`)

Port `TDS530DataCollector` from Python to Go:

- Use `net.Dialer` / `net.Conn` for TCP.
- Run the read loop in a goroutine.
- Send `"ST\r\n"` request.
- Read chunks until terminator `"END       "` is found.
- Parse first line as `YYYY/MM/DD HH:MM:SS`.
- Parse subsequent lines as `M%03d  %lf`.
- Apply calibration and store latest data under a mutex.
- Auto-reconnect with backoff on disconnect or error.

```go
// Pseudo-signature
type Collector struct {
    Host string
    Port int
    OnData func(DataPacket)
    // running, conn, mu, etc.
}
```

### 2. Calibration Store (`calibration.go`)

Port `CalibrationStore` from `calibration.py`:

- Load `calibration.json` from the executable's directory on startup.
- Default all groups to `a: 0, b: 1, c: 0`.
- Save on every update.
- Provide `ChannelGroup(ch int) string` mapping.
- Provide `Apply(raw []float64) []float64`.

Path resolution: use the directory of `os.Executable()` at runtime, falling back to the current working directory.

### 3. Wails App (`app.go`)

Expose the following methods to JavaScript:

```go
func (a *App) GetLatestData() (map[string]interface{}, error)
func (a *App) GetCalibration() (map[string]CalibCoeffs, error)
func (a *App) SetCalibration(values map[string]CalibCoeffs) error
func (a *App) StartSaving(filepath string) error
func (a *App) StopSaving() error
func (a *App) IsSaving() bool
func (a *App) SelectSaveFile() (string, error)  // uses runtime.SaveFileDialog
```

The collector pushes data into the App, and the JS frontend polls `GetLatestData()` every 500 ms.

### 4. Single Instance Lock

Implement in `main.go` or a separate `lock.go`:

- **Windows**: use `CreateMutexW` via `syscall`. If it already exists, show a message box and exit.
- **Linux**: use `flock` on a lock file in `/tmp` or the executable directory.

Requirement confirmed: keep this behavior in the new app.

### 5. File Save Dialog

In pywebview, the dialog was opened from Python via `webview.windows[0].create_file_dialog`. In Wails, the dialog is invoked from Go using the runtime:

```go
import "github.com/wailsapp/wails/v2/pkg/runtime"

func (a *App) SelectSaveFile() (string, error) {
    return runtime.SaveFileDialog(a.ctx, runtime.SaveDialogOptions{
        DefaultFilename: "tds530_log.tsv",
        Filters: []runtime.FileFilter{
            {DisplayName: "TSV files (*.tsv)", Pattern: "*.tsv"},
        },
    })
}
```

## Frontend Changes

The frontend remains visually identical. Only the bridge between JS and the backend changes.

### API Call Mapping

```javascript
// Before (pywebview)
const data = await pywebview.api.get_latest_data();

// After (Wails)
const data = await window.go.main.App.GetLatestData();
```

Full mapping:

| Old | New |
|---|---|
| `pywebview.api.get_latest_data()` | `window.go.main.App.GetLatestData()` |
| `pywebview.api.get_calibration()` | `window.go.main.App.GetCalibration()` |
| `pywebview.api.set_calibration(v)` | `window.go.main.App.SetCalibration(v)` |
| `pywebview.api.start_saving(path)` | `window.go.main.App.StartSaving(path)` |
| `pywebview.api.stop_saving()` | `window.go.main.App.StopSaving()` |
| `pywebview.api.get_saving_status()` | `window.go.main.App.IsSaving()` |
| `pywebview.api.select_save_file()` | `window.go.main.App.SelectSaveFile()` |

### Initialization Event

Replace the `pywebviewready` event listener with Wails DOM-ready handling. Options:

1. Use `OnDomReady` lifecycle hook in Go to emit a custom event, then listen in JS.
2. Poll for `window.go` availability in JS.

Recommended: wrap startup logic in a helper that waits for `window.go`:

```javascript
function waitForWails(callback) {
    if (window.go && window.go.main && window.go.main.App) {
        callback();
        return;
    }
    setTimeout(() => waitForWails(callback), 50);
}

waitForWails(() => {
    loadCalibration();
    fetchData();
    setInterval(fetchData, 500);
});
```

### Polling

Keep the current 500 ms polling loop. The Go backend stores the latest packet in memory; `GetLatestData()` returns it immediately.

## Build Instructions

### Prerequisites

- Go 1.22 or later
- Wails CLI:
  ```bash
  go install github.com/wailsapp/wails/v2/cmd/wails@latest
  ```
- Windows target: WebView2 runtime (usually present; Wails installer handles missing cases)
- Linux target: GTK3 and WebKit2GTK development headers

### Build Commands

```bash
# Windows executable
wails build -platform windows/amd64

# Linux executable
wails build -platform linux/amd64

# Development mode with hot reload
wails dev
```

Outputs:

- Windows: `build/bin/tds530-logger.exe`
- Linux: `build/bin/tds530-logger`

## Migration Checklist

- [ ] Install Go and Wails CLI
- [ ] Create Wails project skeleton (`wails init` or manual)
- [ ] Move `www/*` to `frontend/`
- [ ] Port `CalibrationStore` to `calibration.go`
- [ ] Port `TDS530DataCollector` to `tds530.go`
- [ ] Create `App` struct with JS-exposed methods
- [ ] Implement `SelectSaveFile` using `runtime.SaveFileDialog`
- [ ] Implement single-instance lock for Windows and Linux
- [ ] Update `frontend/index.html` to use Wails runtime API
- [ ] Wire collector lifecycle (start on window load, stop on close)
- [ ] Test build on Windows
- [ ] Test build on Linux
- [ ] Update `README.md` with new build/run instructions
- [ ] Remove Python files (`main.py`, `calibration.py`) or move to `legacy/`

## Open Questions / Notes

- The TDS530 communication protocol is documented only as an image PDF requiring OCR. The existing Python parser should be treated as the authoritative implementation during migration.
- If future requirements include macOS, Wails supports it with minimal changes.
- Auto-updater and code signing are out of scope for now.
