# Scripts

Dev and build helper scripts for Calibration Tracker. Run from the project root.

- **debug_types.py** — List instrument types from the database (dev-only; requires DB connection)
- **build_update_package.py** — Create the update zip for in-app updater (run after build_executable.bat)
- **release.py** — Full release sequence: version, build exe, update zip, installer, git commit
