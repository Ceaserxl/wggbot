# core/logging.py
import os
import inspect
from datetime import datetime

LOG_DIR = "logs"

# --- Clear logs on startup ---
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)
else:
    for file in os.listdir(LOG_DIR):
        if file.endswith(".log"):
            try:
                os.remove(os.path.join(LOG_DIR, file))
            except:
                pass


# -------------------------------------------------
# Determine correct log file name based on rules
# -------------------------------------------------
def _get_module_log_name(frame):
    module = inspect.getmodule(frame)

    if not module or not hasattr(module, "__file__"):
        return "unknown"

    path = module.__file__.replace("\\", "/")

    # Everything should be under "app/"
    if "app/" not in path:
        return "unknown"

    subpath = path.split("app/", 1)[1]   # e.g. "modules/musicplayer/foo.py"
    parts = subpath.split("/")

    top = parts[0]                       # "core", "modules", or a top-level file

    # ----------------------------------------
    # 1. MODULES: modules/<name>/... → modules_<name>.log
    # ----------------------------------------
    if top == "modules":
        module_name = parts[1]           # musicplayer, ping, scraper...
        return f"modules_{module_name}"

    # ----------------------------------------
    # 2. CORE: core/<file>.py → core.log
    # ----------------------------------------
    if top == "core":
        return "core"

    # ----------------------------------------
    # 3. APP ROOT FILES: bot.py / controller.py → app.log
    # ----------------------------------------
    # top-level files directly under app/ (length == 1)
    if len(parts) == 1:
        return "app"

    # fallback
    return "unknown"


# -------------------------------------------------
# Get the filename for extra `[file.py]` tag
# -------------------------------------------------
def _get_source_filename(frame):
    module = inspect.getmodule(frame)
    if not module or not hasattr(module, "__file__"):
        return "unknown"
    return os.path.basename(module.__file__)


# -------------------------------------------------
# Write the log entry with timestamp + file tag
# -------------------------------------------------
def _write_log(module_name: str, message: str, print_console: bool, frame):
    filename = _get_source_filename(frame)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    final_text = f"[{ts}] [{filename}] {message}"

    if print_console:
        print(message)

    logfile = os.path.join(LOG_DIR, f"{module_name}.log")
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(final_text + "\n")


# -------------------------------------------------
# PUBLIC LOGGING FUNCTIONS
# -------------------------------------------------
def log(message: str, *, print_console: bool = True):
    frame = inspect.stack()[1].frame
    module_name = _get_module_log_name(frame)
    _write_log(module_name, message, print_console, frame)


def sublog(message: str, *, print_console: bool = True):
    frame = inspect.stack()[1].frame
    module_name = _get_module_log_name(frame)
    indented = f"   {message}"
    _write_log(module_name, indented, print_console, frame)
