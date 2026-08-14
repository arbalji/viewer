#!/usr/bin/env python3
"""AB2 Violentmonkey deployment agent.

Serves the userscript folder over a local HTTP server and opens each
``log<N>.user.js`` in Firefox so Violentmonkey shows its install page:

    user1  -> log1.user.js
    ...
    user50 -> log50.user.js

Violentmonkey only offers to install a script when it is loaded over http(s)
with a URL ending in ``.user.js`` (opening a local ``file://`` path does not
trigger it), which is why the folder is served from ``http://127.0.0.1:<port>``.

Any constant below can be overridden with an environment variable so you do not
have to edit the file:

    AB2_SCRIPT_FOLDER, AB2_FIREFOX, AB2_PORT, AB2_START_USER, AB2_END_USER

Set AB2_NO_WAIT=1 to open every tab at once instead of one at a time.
"""

from pathlib import Path
import os
import subprocess
import sys
import time

# --- Configuration (edit here or override via environment variables) --------
SCRIPT_FOLDER = Path(os.environ.get("AB2_SCRIPT_FOLDER", r"C:\Users\DELL\ab2gents\workers"))
START_USER = int(os.environ.get("AB2_START_USER", "1"))
END_USER = int(os.environ.get("AB2_END_USER", "50"))
PORT = int(os.environ.get("AB2_PORT", "8765"))

# Real Firefox executable is firefox.exe (NOT chrome.exe).
FIREFOX_PATHS = [
    Path(r"C:\Program Files\Mozilla Firefox\firefox.exe"),
    Path(r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"),
]

# Open one tab at a time (waiting for you to click Install) unless disabled.
WAIT_BETWEEN = os.environ.get("AB2_NO_WAIT", "") == ""


def find_firefox() -> Path:
    override = os.environ.get("AB2_FIREFOX")
    if override:
        path = Path(override)
        if path.exists():
            return path
        raise FileNotFoundError(f"AB2_FIREFOX points to a missing file: {path}")

    for path in FIREFOX_PATHS:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Firefox not found in the usual locations.\n"
        "Install Firefox, or set AB2_FIREFOX to firefox.exe's full path."
    )


def check_scripts() -> bool:
    missing = []
    for number in range(START_USER, END_USER + 1):
        script = SCRIPT_FOLDER / f"log{number}.user.js"
        if not script.exists():
            missing.append(script.name)

    if missing:
        print("\nMissing script files:")
        for name in missing:
            print("   ", name)
        return False

    print(f"All {END_USER - START_USER + 1} userscripts found.")
    return True


def start_script_server() -> subprocess.Popen:
    print("\nStarting local userscript server...")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(PORT),
            "--bind",
            "127.0.0.1",
        ],
        cwd=str(SCRIPT_FOLDER),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    time.sleep(2)
    return process


def install_for_user(firefox: Path, number: int) -> None:
    username = f"user{number}"
    script_name = f"log{number}.user.js"
    url = f"http://127.0.0.1:{PORT}/{script_name}"

    print("=" * 55)
    print(f"{username}")
    print(f"Script : {script_name}")
    print(f"URL    : {url}")

    # -new-tab tells Firefox to open the URL in a new tab of the running
    # instance (or launch it). Violentmonkey then shows its install page.
    subprocess.Popen([str(firefox), "-new-tab", url])


def main() -> None:
    print("=" * 60)
    print("AB2 VIOLENTMONKEY DEPLOYMENT AGENT")
    print("=" * 60)
    print(f"Script folder: {SCRIPT_FOLDER}")
    print(f"Users        : user{START_USER} - user{END_USER}")

    if not SCRIPT_FOLDER.exists():
        raise FileNotFoundError(f"Folder not found:\n{SCRIPT_FOLDER}")

    if not check_scripts():
        return

    firefox = find_firefox()
    print(f"\nFirefox: {firefox}")

    server = start_script_server()
    try:
        print("\nLocal installer server running:")
        print(f"http://127.0.0.1:{PORT}")

        for number in range(START_USER, END_USER + 1):
            install_for_user(firefox, number)
            if WAIT_BETWEEN and number < END_USER:
                input("Click 'Install' in Violentmonkey, then press ENTER for the next user...")
            else:
                time.sleep(0.5)

        print("\nAll userscripts opened for installation.")
        input("\nPress ENTER to stop the server...")
    finally:
        server.terminate()
        print("Server stopped.")


if __name__ == "__main__":
    main()
