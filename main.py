import webview
import socket
import datetime
import os
import threading
import time


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
                            raise ConnectionError("サーバーにより切断されました。")
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
    
    def __init__(self):
        self.latest_data: dict = {}
        self._lock = threading.Lock()
        self._save_file = None
        self._header_written = False
    
    def update_data(self, data: dict):
        """Called by the data collector when new data is received."""
        with self._lock:
            self.latest_data = data
            
            # Save to file if saving is enabled
            if self._save_file is not None:
                try:
                    self._write_data_to_file(data)
                except Exception:
                    pass
    
    def _write_data_to_file(self, data: dict):
        """Write data to TSV file."""
        if self._save_file is None:
            return
        
        if not self._header_written:
            header = "\t".join(["Time"] + [f"CH{idx:03}" for idx in range(len(data["data"]))]) + "\n"
            self._save_file.write(header)
            self._header_written = True
        
        time_str = data["time"].strftime("%Y/%m/%d %H:%M:%S")
        data_strs = [str(val) if val is not None else "" for val in data["data"]]
        line = "\t".join([time_str] + data_strs) + "\n"
        self._save_file.write(line)
        self._save_file.flush()
    
    def get_latest_data(self):
        """Get latest data - called from JavaScript."""
        with self._lock:
            if not self.latest_data:
                return {"error": "No data available"}
            return {
                "time": self.latest_data["time"].strftime("%Y/%m/%d %H:%M:%S"),
                "data": self.latest_data["data"]
            }
    
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
            webview.SAVE_DIALOG,
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


def main():
    HOST = "192.168.100.100"
    PORT = 4242
    
    # Create API instance
    api = TDS530Api()
    
    # Create data collector
    collector = TDS530DataCollector(HOST, PORT, recv_callback=api.update_data)
    
    # Get the path to the HTML template
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "templates", "index.html")
    
    # Create webview window
    window = webview.create_window(
        'TDS530 TCP Logger',
        html_path,
        js_api=api,
        width=1200,
        height=800
    )
    
    # Start data collector when window is ready
    def on_loaded():
        collector.start()
    
    def on_closed():
        collector.stop()
    
    window.events.loaded += on_loaded
    window.events.closed += on_closed
    
    # Start the GUI
    webview.start()


if __name__ == "__main__":
    main()
