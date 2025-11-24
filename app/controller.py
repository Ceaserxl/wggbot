import os
import sys
import subprocess
import time
import signal

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
    """Returns True if bot.pid exists AND process is alive."""
    if not os.path.exists("bot.pid"):
        return False

    try:
        with open("bot.pid", "r") as f:
            pid = int(f.read().strip())
    except:
        return False

    try:
        out = subprocess.check_output(f"tasklist /FI \"PID eq {pid}\"", shell=True)
        return str(pid) in out.decode()
    except:
        return False

# ============================================================
# START BOT — INTERACTIVE (NORMAL) MODE
# ============================================================

def start_bot_interactive():
    cls()
    header()

    if bot_running():
        print("[!] Bot is already running (headless mode).")
        input("\nPress ENTER...")
        return

    python = get_venv_python()
    if not os.path.exists(python):
        print("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    print("[*] Launching bot in interactive mode...\n")
    print("[INFO] Press CTRL+C to stop the bot manually.")
    print("===========================================\n")

    try:
        subprocess.call([python, "app/bot.py"])
    except KeyboardInterrupt:
        print("\n[OK] Bot stopped via CTRL+C")

    input("\nPress ENTER...")

# ============================================================
# START BOT — HEADLESS MODE
# ============================================================

def start_bot_headless():
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

    print("[*] Starting bot headless...")

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "bot.log")

    with open(log_path, "w") as log:
        process = subprocess.Popen(
            [python, "app/bot.py"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL
        )

    with open("bot.pid", "w") as f:
        f.write(str(process.pid))

    print(f"[OK] Bot started headless (PID {process.pid})")
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
        os.kill(pid, signal.SIGINT)
    except:
        pass

    time.sleep(1)

    if bot_running():
        print("[!] Graceful shutdown failed — sending SIGTERM...")
        try:
            os.kill(pid, signal.SIGTERM)
        except:
            pass
        time.sleep(0.5)

    if bot_running():
        print("[!] Final fallback — force killing...")
        try:
            os.kill(pid, signal.SIGKILL)
        except:
            pass

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
            data = f.read()
            print(data if data.strip() else "[log is empty]")
    except Exception as e:
        print(f"[!] Unable to read logs: {e}")

    print("\n==============================")
    input("\nPress ENTER...")

# ============================================================
# PIP PACKAGE INSTALLER
# ============================================================

def install_pip_package():
    cls()
    header()
    pkg = input("Package name: ").strip()

    if not pkg:
        input("No package entered. Press ENTER...")
        return

    print(f"\n[*] Installing '{pkg}'...\n")
    pip_cmd(["install", pkg])
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

    pip_cmd(["install", "-r", "requirements.txt"])
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
        print("[OK] All module requirements installed.")

    input("\nPress ENTER...")

# ============================================================
# MAIN MENU
# ============================================================

def main_menu():
    while True:
        cls()
        header()

        running = bot_running()

        print("1) Start Bot (Interactive)")
        print("2) Start Bot (Headless)")
        print("3) Stop Bot" if running else "3) Check for Updates")
        print("4) Open Logs")
        print("5) Install a Pip Package")
        print("6) Export Requirements")
        print("7) Install Bot requirements.txt")
        print("8) Install Module requirements")
        print("E) Exit\n")

        choice = input("Select an option: ").strip().lower()

        if choice == "1":
            start_bot_interactive()

        elif choice == "2":
            start_bot_headless()

        elif choice == "3":
            if running:
                stop_bot()
            else:
                check_updates()

        elif choice == "4":
            open_logs()

        elif choice == "5":
            install_pip_package()

        elif choice == "6":
            export_requirements()

        elif choice == "7":
            install_bot_requirements()

        elif choice == "8":
            install_module_requirements()

        elif choice == "e":
            cls()
            print("Exiting WGGBot controller...")
            sys.exit(0)

        else:
            input("Invalid option. Press ENTER...")


# ============================================================
if __name__ == "__main__":
    main_menu()
