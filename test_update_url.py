"""One-off test: can we fetch the remote VERSION from this machine (API + raw, multiple casings)?"""
import base64
import json
import urllib.request

owner, path, branch = "Brodylb97", "VERSION", "main"
# GitHub repo names are case-sensitive; try both common spellings
for repo in ("calibrationTracker", "CalibrationTracker", "Calibration-Tracker"):
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    headers = {"User-Agent": "CalibrationTracker-Test/1.0"}

    print(f"Repo {repo!r}:")
    # GitHub API
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        text = base64.b64decode(data.get("content", "") or "").decode("utf-8").strip()
        print(f"  API OK -> version {text!r}")
        break
    except urllib.error.HTTPError as e:
        print(f"  API HTTP {e.code}")
    except Exception as e:
        print(f"  API FAIL: {e}")

    # Raw URL
    try:
        req = urllib.request.Request(raw_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode().strip()
        print(f"  raw OK -> version {text!r}")
        break
    except urllib.error.HTTPError as e:
        print(f"  raw HTTP {e.code}")
    except Exception as e:
        print(f"  raw FAIL: {e}")
else:
    print("None of the repo names worked. Check the repo URL in your browser (Settings -> General -> Repository name).")
