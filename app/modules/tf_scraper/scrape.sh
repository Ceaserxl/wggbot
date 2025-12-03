#!/bin/bash

# Always run relative to the script’s location
cd "$(dirname "$0")"

# Activate venv
source python/win-x64/wvenv/bin/activate

# Run scraper (relative)
python app/modules/scraper/scraper_base.py "$@"
