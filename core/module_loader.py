# /app/core/module_loader.py
import os
import importlib
import traceback
from .logging import log, sublog


def load_all_modules(bot):

    BASE_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "modules")
    )

    log("===========================================")
    log("         Loading WGGBot Modules")
    log("===========================================")

    if not os.path.isdir(BASE_DIR):
        log(f"[ERR] Missing modules folder: {BASE_DIR}")
        return

    # list dirs except pycache
    entries = [
        name for name in sorted(os.listdir(BASE_DIR))
        if name != "__pycache__"
    ]

    total_commands = 0

    for name in entries:
        module_dir = os.path.join(BASE_DIR, name)

        # non-directories still get listed
        if not os.path.isdir(module_dir):
            log(f"[{name}] Skipped not a directory")
            continue

        # must have __init__.py
        init_path = os.path.join(module_dir, "__init__.py")
        if not os.path.isfile(init_path):
            log(f"[{name}] Skipped (no __init__.py)")
            log("")
            continue

        # module begins loading
        log(f"[{name}]")

        module_root = f"modules.{name}"

        expected_files = [
            module_root,
            f"{module_root}.{name}_base",
            f"{module_root}.{name}_commands",
        ]

        for import_target in expected_files:

            # ------------------------
            # IMPORT MODULE
            # ------------------------
            try:
                mod = importlib.import_module(import_target)
            except ModuleNotFoundError:
                # Missing file is NOT an error — just skip
                continue
            except Exception as e:
                log(f"   [ERR] Failed to import {import_target}: {e}")
                traceback.print_exc()
                continue

            # ------------------------
            # INIT
            # ------------------------
            if hasattr(mod, "init"):
                try:
                    sublog(f"[{name}] init()")
                    mod.init(bot)
                except Exception:
                    sublog(f"[{name}] init() failed")
                    traceback.print_exc()

            # ------------------------
            # REGISTER
            # ------------------------
            if hasattr(mod, "register"):
                try:
                    before = len(bot.tree.get_commands())
                    mod.register(bot)
                    after = len(bot.tree.get_commands())
                    added = after - before
                    total_commands += added
                    sublog(f"[{name}] register() ({added} commands)")
                except Exception:
                    sublog(f"[{name}] register() failed")
                    traceback.print_exc()

            # ------------------------
            # SETUP
            # ------------------------
            if hasattr(mod, "setup"):
                try:
                    mod.setup(bot)
                    sublog(f"[{name}] setup()")
                except Exception:
                    sublog(f"[{name}] setup() failed")
                    traceback.print_exc()

        sublog(f"[{name}] Initialized!")
        log("")

    # done
    log(f"[INFO] Total slash commands loaded: {total_commands}")
    log("===========================================")
    log("        WGGBot Modules Loaded")
    log("===========================================")
