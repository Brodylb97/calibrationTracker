# Calibration Tracker – dependency installation and install checks
# Use for CI or to verify dependencies; GUI runs on the host (Windows).
# Python 3.11+ per project rules.
#
# Build:  docker build -t calibration-tracker .
# Check:  docker run --rm calibration-tracker
# Shell:  docker run --rm -it calibration-tracker bash

FROM python:3.11-slim-bookworm

# System dependencies for PyQt5 (headless/import checks on Linux)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxcb-xinerama0 \
        libxkbcommon0 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-xfixes0 \
        libxcb-xkb1 \
        libxkbcommon-x11-0 \
        libegl1 \
        libgl1-mesa-glx \
        libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install check: verify imports and entry point
RUN python -c "\
from database import DB_PATH, CalibrationRepository, get_connection, initialize_db, is_server_db_path; \
from ui_main import run_gui; \
from tolerance_service import evaluate_tolerance_equation; \
print('Calibration Tracker: imports OK')"

# Optional: run tests if present (uncomment to enable)
# RUN python -m pytest test_tolerance_service.py test_migrations.py -v --tb=short 2>/dev/null || true

# Default: run install check again (can override for interactive use)
CMD ["python", "-c", "from database import DB_PATH; from ui_main import run_gui; print('Install check OK')"]
