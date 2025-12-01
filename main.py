import flask
import asyncio
import datetime
import os
import sys
import tkinter.filedialog

latest_data = {}
app = flask.Flask(__name__)

async def tds530_main(host: str, port: int, filepath: str | None = None, recv_callback=None):
    try:
        reader, writer = await asyncio.open_connection(host, port)

        while True:
            ret: dict = {}
            request_message = "ST\r\n"
            writer.write(request_message.encode("utf-8"))
            await writer.drain()

            received_buffer = ""
            terminator = "END       "  # "END" + スペース7個 + 改行1個

            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.IncompleteReadError as e:
                    chunk = e.partial or b""
                if chunk is None:
                    chunk = b""
                if not chunk:
                    raise ConnectionError("サーバーにより切断されました。")
                text_chunk = chunk.decode("utf-8", errors="replace")
                received_buffer += text_chunk
                if terminator in received_buffer:
                    break

            # recv data:
            # 1st(time): YYYY/MM/DD HH:MM:SS
            # 2nd (1ch data): M%03d  %lf
            lines = received_buffer.splitlines()
            if len(lines) < 2:
                raise ValueError("受信データの形式が不正です。")
            ret["time"] = datetime.datetime.strptime(lines[0], "%Y/%m/%d %H:%M:%S")
            ret["data"] = []
            for line in lines[1:]:
                parts = line.split("  ")
                if len(parts) == 2:
                    # format : M%03d  %lf
                    ch_str, val_str = parts
                    # ch_num = int(ch_str[1:])  # 'M'を除去 (未使用)
                    try:
                        val = float(val_str)
                        ret["data"].append(val)
                    except ValueError:
                        ret["data"].append(None)  # 変換できない場合はNoneを設定
            
            if recv_callback is not None:
                recv_callback(ret)

            # Save to TSV file if filepath is provided
            if filepath is None:
                continue

            with open(filepath, "a", encoding="utf-8") as f:
                if f.tell() == 0:
                    header = "\t".join(["Time"] + [f"CH{idx:03}" for idx in range(len(ret["data"]))]) + "\n"
                    f.write(header)
                time_str = ret["time"].strftime("%Y/%m/%d %H:%M:%S")
                data_strs = [str(val) if val is not None else "" for val in ret["data"]]
                line = "\t".join([time_str] + data_strs) + "\n"
                f.write(line)
            

    except KeyboardInterrupt:
        pass

@app.route('/')
def index():
    return flask.render_template('index.html')

@app.route("/v1/", methods=["GET"])
def v1_endpoint():
    global latest_data
    if not latest_data:
        return flask.jsonify({"error": "No data available"}), 503
    response = {
        "time": latest_data["time"].strftime("%Y/%m/%d %H:%M:%S"),
        "data": latest_data["data"]
    }
    return flask.jsonify(response)

def latest_data_callback(data: dict):
    global latest_data
    latest_data = data

async def main(filepath: str | None = None):
    loop = asyncio.get_running_loop()
    tds530_task = loop.create_task(tds530_main(HOST, PORT, filepath, latest_data_callback))
    flask_task = loop.run_in_executor(None, app.run, "localhost", 5000)
    await asyncio.gather(tds530_task, flask_task)

if __name__ == "__main__":
    HOST = "192.168.100.100"
    PORT = 4242

    # # ファイル保存ダイアログを表示して保存先を取得
    # filetypes = [("Tab Separated Values", "*.tsv")]
    # initialdir = os.path.abspath(os.path.dirname(__file__))
    # filepath = tkinter.filedialog.asksaveasfilename(filetypes=filetypes, initialdir=initialdir)
    # # If has no extension, add ".tsv"
    # if filepath and not filepath.lower().endswith(".tsv"):
    #     filepath += ".tsv"

    # #asyncio.run(async_main(HOST, PORT, filepath))
    # # run tds530_main and flask app concurrently
    # if "--dry-run" in sys.argv:
    #     filepath = None

    asyncio.run(main(None))
