import threading
import webview
from waitress import serve
from Hazmat_Dashboard import app

def start_server():
    serve(app.server, host="127.0.0.1", port=8050)

if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    webview.create_window("Hazmat Global Support Services", "http://127.0.0.1:8050", width=1400, height=900)
    webview.start()