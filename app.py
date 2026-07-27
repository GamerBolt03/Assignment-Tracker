import os
import sys
import threading
import time
import urllib.request
import webbrowser

FLASK_PORT = 5000


def wait_for_server(host="127.0.0.1", port=FLASK_PORT, timeout=15):
    url = f"http://{host}:{port}/"
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(url)
            return True
        except:
            time.sleep(0.5)
    return False


def start_flask():
    from main import app
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False, use_reloader=False)


def main():
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()

    if not wait_for_server():
        print("Server failed to start")
        sys.exit(1)

    try:
        import webview
        webview.create_window(
            "Assignment Tracker",
            f"http://127.0.0.1:{FLASK_PORT}",
            width=1100,
            height=750,
            resizable=True,
        )
        webview.start()
    except ImportError:
        webbrowser.open(f"http://127.0.0.1:{FLASK_PORT}")
        t.join()


if __name__ == "__main__":
    main()
