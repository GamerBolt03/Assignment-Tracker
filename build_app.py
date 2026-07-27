"""
Build Assignment Tracker into a standalone EXE.
Usage: python build_app.py
"""
import os
import subprocess
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))

    templates = os.path.join(here, "templates")
    if not os.path.isdir(templates):
        print("ERROR: templates/ folder not found")
        sys.exit(1)

    # Convert PNG icon to ICO if needed
    ico_path = os.path.join(here, "app_icon.ico")
    png_path = os.path.join(here, "Assignment-Tracker-ICON-NoBackground.png")
    if not os.path.exists(ico_path) and os.path.exists(png_path):
        try:
            from PIL import Image
            img = Image.open(png_path)
            img.save(ico_path, format="ICO", sizes=[(256, 256)])
            print("Icon converted to ICO")
        except Exception as e:
            print(f"Warning: could not convert icon: {e}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "AssignmentTracker",
        "--windowed",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"requirements.txt{os.pathsep}.",
        "--hidden-import", "flask",
        "--hidden-import", "googleapiclient",
        "--hidden-import", "google_auth_oauthlib",
        "--hidden-import", "google.auth",
        "--hidden-import", "transformers",
        "--hidden-import", "huggingface_hub",
        "--hidden-import", "sqlite3",
        "--hidden-import", "webview",
        "--hidden-import", "oauthlib",
        "--hidden-import", "requests",
        "--collect-submodules", "email",
        os.path.join(here, "app.py"),
    ]

    if os.path.exists(ico_path):
        cmd.insert(cmd.index("--windowed") + 1, "--icon")
        cmd.insert(cmd.index("--windowed") + 2, ico_path)

    print("Running PyInstaller...")
    result = subprocess.run(cmd, cwd=here)
    if result.returncode != 0:
        print(f"PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)

    exe_path = os.path.join(here, "dist", "AssignmentTracker.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\nSUCCESS! EXE built at: {exe_path} ({size_mb:.1f} MB)")
    print()
    print("NOTE: client_secret.json and .db files are created at runtime.")
    print("Place client_secret.json next to the EXE for Gmail API auth.")


if __name__ == "__main__":
    main()
