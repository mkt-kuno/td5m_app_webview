import webview
import socket
import datetime
import json
import os
import sys
import threading
import time
import tempfile
import atexit

from calibration import CalibrationStore
from units import UnitStore, UNIT_GROUPS

# Platform-specific imports for file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class SingleInstanceLock:
    """
    Prevents multiple instances of the application from running simultaneously.
    Works on both Windows and Linux by using exclusive file locking.
    """
    
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.lock_file_path = os.path.join(tempfile.gettempdir(), f"{app_name}.lock")
        self._lock_file = None
    
    def acquire(self) -> bool:
        """
        Attempt to acquire the lock.
        Returns True if the lock was acquired, False if another instance is running.
        """
        try:
            # Open or create the lock file
            self._lock_file = open(self.lock_file_path, "w")
            
            if sys.platform == "win32":
                # Windows: use msvcrt for locking
                try:
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except (IOError, OSError):
                    self._lock_file.close()
                    self._lock_file = None
                    return False
            else:
                # Linux/macOS: use fcntl for locking
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except (IOError, OSError):
                    self._lock_file.close()
                    self._lock_file = None
                    return False
        except Exception:
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False
    
    def release(self):
        """Release the lock."""
        if self._lock_file:
            try:
                if sys.platform == "win32":
                    try:
                        msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    try:
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                self._lock_file.close()
            except Exception:
                pass
            finally:
                self._lock_file = None
            
            # Try to remove the lock file
            try:
                os.remove(self.lock_file_path)
            except Exception:
                pass


class TDS530DataCollector:
    """Thread-based TCP data collector for TDS530 device."""
    
    def __init__(self, host: str, port: int, recv_callback=None):
        self.host = host
        self.port = port
        self.recv_callback = recv_callback
        self._running = False
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
    
    def start(self):
        """Start the data collection thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the data collection thread."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
    
    def _run(self):
        """Main data collection loop running in a separate thread."""
        while self._running:
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(2.0)
                self._socket.connect((self.host, self.port))
                
                while self._running:
                    ret: dict = {}
                    request_message = "ST\r\n"
                    self._socket.sendall(request_message.encode("utf-8"))
                    
                    received_buffer = ""
                    terminator = "END       "  # "END" + 7 spaces + newline
                    
                    while self._running:
                        try:
                            chunk = self._socket.recv(1024)
                        except socket.timeout:
                            continue
                        except Exception:
                            break
                        if not chunk:
                            raise ConnectionError("Disconnected by server.")
                        text_chunk = chunk.decode("utf-8", errors="replace")
                        received_buffer += text_chunk
                        if terminator in received_buffer:
                            break
                    
                    if not self._running:
                        break
                    
                    # Parse received data:
                    # 1st(time): YYYY/MM/DD HH:MM:SS
                    # 2nd (1ch data): M%03d  %lf
                    lines = received_buffer.splitlines()
                    if len(lines) < 2:
                        continue
                    
                    try:
                        ret["time"] = datetime.datetime.strptime(lines[0], "%Y/%m/%d %H:%M:%S")
                    except ValueError:
                        continue
                    
                    ret["data"] = []
                    for line in lines[1:]:
                        parts = line.split("  ")
                        if len(parts) == 2:
                            _, val_str = parts
                            try:
                                val = float(val_str)
                                ret["data"].append(val)
                            except ValueError:
                                ret["data"].append(None)
                    
                    if self.recv_callback is not None:
                        self.recv_callback(ret)
                    time.sleep(0.1)
                
            except (ConnectionRefusedError, socket.timeout, OSError):
                # Connection failed, retry after delay
                pass
            except Exception:
                pass
            finally:
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None
            
            # Wait before retry if still running
            if self._running:
                time.sleep(1.0)


class TDS530Api:
    """API class exposed to JavaScript via pywebview."""
    
    def __init__(self, calibration: CalibrationStore, units: UnitStore):
        self.calibration = calibration
        self.units = units
        self.latest_data: dict = {}
        self._lock = threading.Lock()
        self._save_file = None
        self._header_written = False
        self.window = None
    
    def set_window(self, window):
        """Set the pywebview window reference for JS push updates."""
        self.window = window

    def _push_to_js(self, data: dict):
        """Push the latest data to the frontend via evaluate_js."""
        if self.window is None:
            return
        try:
            payload = {
                "time": data["time"].strftime("%Y/%m/%d %H:%M:%S"),
                "raw": data["raw"],
                "physical": data["physical"],
            }
            js = f"window.updateDataFromPython({json.dumps(payload)})"
            self.window.evaluate_js(js)
        except Exception:
            # Window may not be ready or JS side may be unavailable; ignore.
            pass

    def update_data(self, data: dict):
        """Called by the data collector when new data is received."""
        with self._lock:
            raw_data = data["data"]
            physical_data = self.calibration.apply(raw_data)
            stored = {
                "time": data["time"],
                "raw": raw_data,
                "physical": physical_data,
            }
            self.latest_data = stored

            # Save to file if saving is enabled
            if self._save_file is not None:
                try:
                    self._write_data_to_file(stored)
                except Exception:
                    pass

            # Push the data to the frontend immediately
            self._push_to_js(stored)
    
    @staticmethod
    def _format_raw_value(value):
        """Format raw value like the reference TSV (integer when whole)."""
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    @staticmethod
    def _format_phy_value(value):
        """Format physical value with 3 decimals like the reference TSV."""
        if value is None:
            return ""
        return f"{value:.3f}"

    def _write_data_to_file(self, data: dict):
        """Write raw and physical data to TSV file."""
        if self._save_file is None:
            return

        if not self._header_written:
            header_parts = ["timestamp"]
            for idx in range(len(data["raw"])):
                header_parts.append(f"ai_raw_{idx:02d}")
            for idx in range(len(data["physical"])):
                header_parts.append(f"ai_phy_{idx:02d}")
            self._save_file.write("\t".join(header_parts) + "\n")
            self._header_written = True

        time_str = data["time"].strftime("%Y/%m/%d %H:%M:%S") + ".000"
        data_strs = [time_str]
        for raw in data["raw"]:
            data_strs.append(self._format_raw_value(raw))
        for phy in data["physical"]:
            data_strs.append(self._format_phy_value(phy))
        line = "\t".join(data_strs) + "\n"
        self._save_file.write(line)
        self._save_file.flush()
    
    def get_latest_data(self):
        """Get latest raw and physical data - called from JavaScript."""
        with self._lock:
            if not self.latest_data:
                return {"error": "No data available"}
            return {
                "time": self.latest_data["time"].strftime("%Y/%m/%d %H:%M:%S"),
                "raw": self.latest_data["raw"],
                "physical": self.latest_data["physical"]
            }
    
    def get_calibration(self):
        """Get current calibration coefficients - called from JavaScript."""
        return self.calibration.to_dict()
    
    def set_calibration(self, values: dict):
        """Update calibration coefficients - called from JavaScript."""
        try:
            self.calibration.set_from_dict(values)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def get_units(self):
        """Get current unit settings - called from JavaScript."""
        return self.units.to_dict()
    
    def set_units(self, values: dict):
        """Update unit settings - called from JavaScript."""
        try:
            self.units.set_from_dict(values)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def start_saving(self, filepath: str):
        """Start saving data to a file - called from JavaScript."""
        with self._lock:
            if self._save_file is not None:
                return {"error": "Already saving"}
            
            try:
                self._save_file = open(filepath, "w", encoding="utf-8")
                self._header_written = False
                return {"success": True, "filepath": filepath}
            except Exception as e:
                return {"error": str(e)}
    
    def stop_saving(self):
        """Stop saving data - called from JavaScript."""
        with self._lock:
            if self._save_file is None:
                return {"error": "Not saving"}
            
            try:
                self._save_file.close()
            except Exception:
                pass
            finally:
                self._save_file = None
                self._header_written = False
            
            return {"success": True}
    
    def is_saving(self):
        """Check if currently saving - called from JavaScript."""
        with self._lock:
            return self._save_file is not None
    
    def select_save_file(self):
        """Open file dialog to select save location - called from JavaScript."""
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename='tds530_log.tsv',
            file_types=('TSV files (*.tsv)',)
        )
        if result:
            # Handle both string and tuple/list return types
            if isinstance(result, str):
                filepath = result
            elif len(result) > 0:
                filepath = result[0]
            else:
                return {"cancelled": True}
            
            if not filepath.lower().endswith(".tsv"):
                filepath += ".tsv"
            return {"filepath": filepath}
        return {"cancelled": True}

if __name__ == "__main__":
    APP_NAME = "TDS530Logger"
    
    # Prevent multiple instances
    instance_lock = SingleInstanceLock(APP_NAME)
    if not instance_lock.acquire():
        # Show error message and exit
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "The application is already running.",
                APP_NAME,
                0x30  # MB_ICONWARNING
            )
        else:
            print("The application is already running.", file=sys.stderr)
        sys.exit(1)
    
    # Register cleanup on exit
    atexit.register(instance_lock.release)
    
    HOST = "192.168.100.100"
    PORT = 4242
    HOST = "192.168.100.100"
    PORT = 4242
    
    # Load calibration and unit configuration (auto-restore on startup)
    calibration = CalibrationStore()
    units = UnitStore()
    
    # Ensure configuration is saved on app exit (auto-store on shutdown)
    atexit.register(calibration.save)
    atexit.register(units.save)
    
    # Create API instance
    api = TDS530Api(calibration, units)
    
    # Create data collector
    collector = TDS530DataCollector(HOST, PORT, recv_callback=api.update_data)

    window = webview.create_window(
        'TrapDoor 5-Axis Motor Logger',
        'www/index.html',
        js_api=api,
        width=1900,
        height=1000)

    # Provide the window reference so the API can push data to JS
    api.set_window(window)

    # Start data collector when window is ready
    def on_loaded():
        collector.start()
    
    def on_closed():
        collector.stop()
        instance_lock.release()
    
    window.events.loaded += on_loaded
    window.events.closed += on_closed

    webview.start()