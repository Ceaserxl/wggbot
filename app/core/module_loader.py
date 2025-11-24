# core/module_loader.py

import os
import importlib
import traceback


def load_all_modules(bot):
    """
    WGGBot Dynamic Module Loader
    Loads ./modules/<name>/

    Each module may define:
       - init(bot)
       - register(bot)
       - setup(bot)
    """

    BASE_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "modules")
    )

    print("\n===========================================")
    print("         Loading WGGBot Modules")
    print("===========================================\n")

    if not os.path.isdir(BASE_DIR):
        print(f"[ERR] Missing modules folder: {BASE_DIR}")
        return

    module_names = sorted(os.listdir(BASE_DIR))
    total_commands = 0  # <── count registered slash commands

    for name in module_names:
        module_dir = os.path.join(BASE_DIR, name)
        if not os.path.isdir(module_dir):
            continue

        if not os.path.isfile(os.path.join(module_dir, "__init__.py")):
            print(f"[SKIP] {name} — No __init__.py")
            continue

        print(f"[MODULE] {name}")

        # Import targets
        module_root = f"modules.{name}"

        expected_files = [
            module_root,
            f"{module_root}.{name}_base",
            f"{module_root}.{name}_commands",
        ]

        # Process each file
        for import_target in expected_files:

            try:
                mod = importlib.import_module(import_target)
            except ModuleNotFoundError:
                continue
            except Exception as e:
                print(f"   [ERR] Failed to import {import_target}: {e}")
                traceback.print_exc()
                continue

            # -----------------------------
            # init()
            # -----------------------------
            if hasattr(mod, "init"):
                try:
                    mod.init(bot)
                    print(f"   [OK] init()    — {import_target}")
                except Exception:
                    print(f"   [ERR] init() failed — {import_target}")
                    traceback.print_exc()

            # -----------------------------
            # register()  ← count commands
            # -----------------------------
            if hasattr(mod, "register"):
                try:
                    before = len(bot.tree.get_commands())
                    mod.register(bot)
                    after = len(bot.tree.get_commands())

                    added = after - before
                    total_commands += added

                    print(f"   [OK] register() — {import_target}  ({added} commands)")
                except Exception:
                    print(f"   [ERR] register() failed — {import_target}")
                    traceback.print_exc()

            # -----------------------------
            # setup()
            # -----------------------------
            if hasattr(mod, "setup"):
                try:
                    mod.setup(bot)
                    print(f"   [OK] setup()   — {import_target}")
                except Exception:
                    print(f"   [ERR] setup() failed — {import_target}")
                    traceback.print_exc()

        print()

    # ---------------------------------------
    # 🎉 Print total commands loaded
    # ---------------------------------------
    print(f"[INFO] Total slash commands loaded: {total_commands}\n")

    print("===========================================")
    print("        WGGBot Modules Loaded")
    print("===========================================\n")
