import os
import sys
import subprocess
import time

# ============================================================
# UTILITIES
# ============================================================

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def header():
    print("===========================================")
    print("               WGGBot Controller")
    print("===========================================\n")

def get_venv_python():
    return os.path.join("python", "win-x64", "wvenv", "Scripts", "python.exe")

def pip_cmd(args):
    python = get_venv_python()
    if not os.path.exists(python):
        print("[!] Virtual environment not found.")
        input("\nPress ENTER...")
        return False
    return subprocess.call([python, "-m", "pip"] + args)

def bot_running():
    """Returns True if bot.pid exists AND the process is alive."""
    if not os.path.exists("bot.pid"):
        return False

    try:
        with open("bot.pid", "r") as f:
            pid = int(f.read().strip())
    except:
        return False

    # Check if the PID exists
    try:
        out = subprocess.check_output(f"tasklist /FI \"PID eq {pid}\"", shell=True)
        return str(pid) in out.decode()
    except:
        return False

# ============================================================
# MAIN MENU
# ============================================================

def main_menu():
    while True:
        cls()
        header()

        running = bot_running()

        print("1) Start Bot" if not running else "1) Bot is running")
        if running:
            print("2) Stop Bot")
        else:
            print("2) Check for Updates")

        print("3) Open Logs")
        print("4) Install a Pip Package")
        print("5) Export Requirements")
        print("6) Install Bot requirements.txt")
        print("7) Install Module requirements")
        print("8) Exit\n")

        choice = input("Select an option: ").strip()

        if not running:
            if choice == "1":
                start_bot()
            elif choice == "2":
                check_updates()
        else:
            if choice == "2":
                stop_bot()

        if choice == "3":
            open_logs()
        elif choice == "4":
            install_pip_package()
        elif choice == "5":
            export_requirements()
        elif choice == "6":
            install_bot_requirements()
        elif choice == "7":
            install_module_requirements()
        elif choice == "8":
            cls()
            print("Exiting WGGBot controller...")
            sys.exit(0)

# ============================================================
# START BOT (HEADLESS)
# ============================================================
import subprocess
import os
import time
import signal

def start_bot():
    cls()
    header()

    if bot_running():
        print("[!] Bot is already running.")
        input("\nPress ENTER...")
        return

    python = get_venv_python()

    if not os.path.exists(python):
        print("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    print("[*] Starting bot (cross-platform headless)...")

    # Ensure logs folder exists
    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "bot.log")

    # Start bot process (UNIVERSAL)
    with open(log_path, "w") as log:
        process = subprocess.Popen(
            [python, "app/bot.py"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL
        )

    # Save PID
    with open("bot.pid", "w") as f:
        f.write(str(process.pid))

    print(f"[OK] Bot started (PID {process.pid})")
    input("\nPress ENTER...")

# ============================================================
# STOP BOT
# ============================================================
def stop_bot():
    cls()
    header()

    if not bot_running():
        print("[!] Bot is not running.")
        input("\nPress ENTER...")
        return

    with open("bot.pid", "r") as f:
        pid = int(f.read().strip())

    print(f"[*] Sending graceful shutdown to PID {pid}...\n")

    try:
        os.kill(pid, signal.SIGINT)   # ask python to quit cleanly
    except Exception:
        pass

    time.sleep(1)

    # Check if still running
    if bot_running():
        print("[!] Graceful shutdown failed, forcing stop...")
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(0.5)

    if bot_running():
        print("[!] Process still alive — final force kill...")
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    # Remove PID file
    if os.path.exists("bot.pid"):
        os.remove("bot.pid")

    print("[OK] Bot stopped.")
    input("\nPress ENTER...")

# ============================================================
# CHECK UPDATES
# ============================================================
def check_updates():
    cls()
    header()
    print("[*] Checking for updates...\n")
    os.system("git pull")
    input("\nDone. Press ENTER...")

# ============================================================
# OPEN LOGS
# ============================================================
def open_logs():
    cls()
    header()

    log_file = os.path.join("logs", "bot.log")

    if not os.path.exists(log_file):
        print("[!] No bot.log found.")
        input("\nPress ENTER...")
        return

    print("========== BOT LOGS ==========\n")

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            print(content if content.strip() else "[log is empty]")
    except Exception as e:
        print(f"[!] Failed to read logs: {e}")

    print("\n==============================")
    input("\nPress ENTER...")

# ============================================================
# INSTALL A PIP PACKAGE
# ============================================================
def install_pip_package():
    cls()
    header()
    pkg = input("Package name (example: requests or requests==2.31): ").strip()

    if not pkg:
        input("No package entered. Press ENTER...")
        return

    print(f"\n[*] Installing '{pkg}'...\n")

    if pip_cmd(["install", pkg]) == 0:
        print("\n[OK] Package installed.")
    else:
        print("\n[!] Installation failed.")

    input("\nPress ENTER...")

# ============================================================
# EXPORT REQUIREMENTS
# ============================================================
def export_requirements():
    cls()
    header()
    print("[*] Exporting pip freeze -> requirements.txt...\n")

    python = get_venv_python()
    if not os.path.exists(python):
        print("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    with open("requirements.txt", "w") as f:
        subprocess.call([python, "-m", "pip", "freeze"], stdout=f)

    print("[OK] Requirements exported.")
    input("\nPress ENTER...")

# ============================================================
# INSTALL BOT REQUIREMENTS
# ============================================================
def install_bot_requirements():
    cls()
    header()
    print("[*] Installing bot requirements.txt...\n")

    if not os.path.exists("requirements.txt"):
        print("[!] No requirements.txt found.")
        input("\nPress ENTER...")
        return

    if pip_cmd(["install", "-r", "requirements.txt"]) == 0:
        print("\n[OK] Bot requirements installed.")
    else:
        print("\n[!] Failed to install bot requirements.")

    input("\nPress ENTER...")

# ============================================================
# INSTALL MODULE REQUIREMENTS
# ============================================================
def install_module_requirements():
    cls()
    header()
    print("[*] Installing module dependencies...\n")

    base = os.path.join("app", "modules")

    if not os.path.exists(base):
        print("[!] No modules folder found.")
        input("\nPress ENTER...")
        return

    found = False

    for folder in os.listdir(base):
        path = os.path.join(base, folder)
        req = os.path.join(path, "requirements.txt")

        if os.path.exists(req):
            found = True
            print(f"[*] Installing: {folder}")
            pip_cmd(["install", "-r", req])

    if not found:
        print("[!] No module requirements.txt files found.")
    else:
        print("\n[OK] All module requirements installed.")

    input("\nPress ENTER...")

# ============================================================
if __name__ == "__main__":
    main_menu()
