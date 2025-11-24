import os
import sys
import subprocess

# Clear screen
def cls():
    os.system("cls" if os.name == "nt" else "clear")

# Header
def header():
    print("===========================================")
    print("               WGGBot Controller           ")
    print("===========================================\n")

def main_menu():
    while True:
        cls()
        header()

        print("1) Start Bot")
        print("2) Check for Updates")
        print("3) Open Logs")
        print("4) Exit\n")

        choice = input("Select an option: ").strip()

        if choice == "1":
            start_bot()

        elif choice == "2":
            check_updates()

        elif choice == "3":
            open_logs()

        elif choice == "4":
            cls()
            print("Exiting WGGBot controller...")
            sys.exit(0)

        else:
            input("Invalid option. Press ENTER...")

# ---- Actions ----

def start_bot():
    cls()
    header()
    print("[*] Launching bot...\n")

    venv_python = os.path.join("python", "win-x64", "wvenv", "Scripts", "python.exe")

    if not os.path.exists(venv_python):
        print("[!] Virtual environment missing.")
        input("\nPress ENTER...")
        return

    subprocess.call([venv_python, "app/main.py"])
    input("\nBot stopped. Press ENTER...")

def check_updates():
    cls()
    header()
    print("[*] Checking for updates...\n")
    os.system("git pull")
    input("\nDone. Press ENTER...")

def open_logs():
    cls()
    header()

    log_dir = "logs"

    if not os.path.exists(log_dir):
        print("[!] No logs found.")
        input("\nPress ENTER...")
        return

    print("[*] Opening logs folder...\n")
    os.startfile(log_dir)
    input("Press ENTER...")

# ----------------------------------------

if __name__ == "__main__":
    main_menu()
