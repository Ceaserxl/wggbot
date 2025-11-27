# app/controller.py
import os
import sys
import subprocess
import time
import signal
from core.logging import log

# ============================================================
# UTILITIES
# ============================================================
def header():
    log("===========================================")
    log("               WGGBot Controller")
    log("===========================================")

def get_venv_python():
    return os.path.join("python", "win-x64", "wvenv", "Scripts", "python.exe")

def pip_cmd(args):
    python = get_venv_python()
    if not os.path.exists(python):
        log("[!] Virtual environment not found.")
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
# DIRECTORY TREE VIEWER
# ============================================================
IGNORE_FOLDERS = {"__pycache__", "downloads", "downloads_win", "python"}

# ANSI colors (Windows terminal supports these)
BLUE = "\033[94m"
WHITE = "\033[97m"
GRAY = "\033[90m"
RESET = "\033[0m"

def color_name(name, is_dir, ignored):
    """Returns a colorized name depending on type."""
    if ignored:
        return f"{GRAY}{name}{RESET}"
    if is_dir:
        return f"{BLUE}{name}{RESET}"
    return f"{WHITE}{name}{RESET}"


def tree(path=".", prefix="", depth=0):
    """Colorized & depth-aware tree that shows ignored folders but does not recurse into them."""
    try:
        entries = sorted(os.listdir(path))
    except FileNotFoundError:
        return

    for index, name in enumerate(entries):
        full = os.path.join(path, name)
        is_dir = os.path.isdir(full)
        ignored = name in IGNORE_FOLDERS

        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "

        # color the name
        colored = color_name(name, is_dir, ignored)

        # print depth + tree line
        log(f"[{depth}] {prefix}{connector}{colored}")

        # STOP recursion if ignored or not a folder
        if ignored or not is_dir:
            continue

        # recursion into children
        extension = "    " if is_last else "│   "
        tree(full, prefix + extension, depth + 1)


def print_directory_tree():
    header()
    log("[*] Directory Tree:", print_console=True)
    log(f"[0] {BLUE}app{RESET}", print_console=True)
    tree("app", depth=0)
    input("\nPress ENTER...")


# ============================================================
# START BOT — INTERACTIVE (NORMAL) MODE
# ============================================================

def start_bot_interactive():
    header()

    if bot_running():
        log("[!] Bot is already running (headless mode).")
        input("\nPress ENTER...")
        return

    python = get_venv_python()
    if not os.path.exists(python):
        log("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    log("[*] Launching bot in interactive mode...")
    log("[INFO] Press CTRL+C to stop the bot manually.")
    log("===========================================")

    try:
        subprocess.call([python, "-m", "app.bot"])
    except KeyboardInterrupt:
        log("[OK] Bot stopped via CTRL+C")
    input("\nPress ENTER...")

# ============================================================
# START BOT — HEADLESS MODE
# ============================================================

def start_bot_headless():
    header()

    if bot_running():
        log("[!] Bot is already running.")
        input("\nPress ENTER...")
        return

    python = get_venv_python()
    if not os.path.exists(python):
        log("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    log("[*] Starting bot headless...")

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", "bot.log")

    with open(log_path, "w") as logfile:
        process = subprocess.Popen(
            [python, "app/bot.py"],
            stdout=logfile,
            stderr=logfile,
            stdin=subprocess.DEVNULL
        )

    with open("bot.pid", "w") as f:
        f.write(str(process.pid))

    log(f"[OK] Bot started headless (PID {process.pid})")
    input("\nPress ENTER...")

# ============================================================
# STOP BOT
# ============================================================

def stop_bot():
    header()

    if not bot_running():
        log("[!] Bot is not running.")
        input("\nPress ENTER...")
        return

    with open("bot.pid", "r") as f:
        pid = int(f.read().strip())

    log(f"[*] Sending graceful shutdown to PID {pid}...")

    try:
        os.kill(pid, signal.SIGINT)
    except:
        pass

    time.sleep(1)

    if bot_running():
        log("[!] Graceful shutdown failed — sending SIGTERM...")
        try:
            os.kill(pid, signal.SIGTERM)
        except:
            pass
        time.sleep(0.5)

    if bot_running():
        log("[!] Final fallback — force killing...")
        try:
            os.kill(pid, signal.SIGKILL)
        except:
            pass

    if os.path.exists("bot.pid"):
        os.remove("bot.pid")

    log("[OK] Bot stopped.")
    input("\nPress ENTER...")

# ============================================================
# CHECK UPDATES
# ============================================================

def check_updates():
    header()
    log("[*] Checking for updates...")
    os.system("git pull")
    log("[*] Done.")
    input("\nPress ENTER...")

# ============================================================
# OPEN LOGS
# ============================================================

def open_logs():
    header()

    log_file = os.path.join("logs", "bot.log")

    if not os.path.exists(log_file):
        log("[!] No bot.log found.")
        input("\nPress ENTER...")
        return

    log("========== BOT LOGS ==========")

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
            log(data if data.strip() else "[log is empty]")
    except Exception as e:
        log(f"[!] Unable to read logs: {e}")

    log("==============================")
    input("\nPress ENTER...")

# ============================================================
# PIP PACKAGE INSTALLER
# ============================================================

def install_pip_package():
    header()
    pkg = input("Package name: ").strip()

    if not pkg:
        input("No package entered. Press ENTER...")
        return

    log(f"\n[*] Installing '{pkg}'...")
    pip_cmd(["install", pkg])
    input("\nPress ENTER...")

# ============================================================
# EXPORT REQUIREMENTS
# ============================================================

def export_requirements():
    header()
    log("[*] Exporting pip freeze -> requirements.txt...")

    python = get_venv_python()
    if not os.path.exists(python):
        log("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    with open("requirements.txt", "w") as f:
        subprocess.call([python, "-m", "pip", "freeze"], stdout=f)

    log("[OK] Requirements exported.")
    input("\nPress ENTER...")

# ============================================================
# INSTALL BOT REQUIREMENTS
# ============================================================

def install_bot_requirements():
    header()
    log("[*] Installing bot requirements.txt...")

    if not os.path.exists("requirements.txt"):
        log("[!] No requirements.txt found.")
        input("\nPress ENTER...")
        return

    pip_cmd(["install", "-r", "requirements.txt"])
    input("\nPress ENTER...")

# ============================================================
# INSTALL MODULE REQUIREMENTS
# ============================================================

def install_module_requirements():
    header()
    log("[*] Installing module dependencies...")

    base = os.path.join("app", "modules")

    if not os.path.exists(base):
        log("[!] No modules folder found.")
        input("\nPress ENTER...")
        return

    found = False

    for folder in os.listdir(base):
        path = os.path.join(base, folder)
        req = os.path.join(path, "requirements.txt")

        if os.path.exists(req):
            found = True
            log(f"[*] Installing: {folder}")
            pip_cmd(["install", "-r", req])

    if not found:
        log("[!] No module requirements.txt files found.")
    else:
        log("[OK] All module requirements installed.")

    input("\nPress ENTER...")

# ============================================================
# MAIN MENU
# ============================================================

def main_menu():
    while True:
        header()

        running = bot_running()

        log("1) Start Bot (Interactive)")
        log("2) Start Bot (Headless)")
        log("3) Stop Bot" if running else "3) Check for Updates")
        log("4) Open Logs")
        log("5) Install a Pip Package")
        log("6) Export Requirements")
        log("7) Install Bot requirements.txt")
        log("8) Install Module requirements")
        log("9) Print Directory Tree")
        log("E) Exit")

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

        elif choice == "9":
            print_directory_tree()

        elif choice == "e":
            log("Exiting WGGBot controller...")
            sys.exit(0)

        else:
            input("Invalid option. Press ENTER...")


# ============================================================
if __name__ == "__main__":
    main_menu()
