"""GitHub release update checker for the OEL launcher."""
import json
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

_API_URL = "https://api.github.com/repos/{repo}/releases"
_TIMEOUT = 10


def _parse_version(tag: str) -> tuple[int, ...] | None:
    """Return a comparable version tuple from a tag like 'v1.0.2.3', or None."""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(p) for p in tag.split("."))
    except ValueError:
        return None


def _pick_release(releases: list, channel: str) -> dict | None:
    """Return the best candidate release for the given channel."""
    candidates = [r for r in releases if not r.get("draft")]
    if channel == "main":
        candidates = [r for r in candidates if not r.get("prerelease")]
        return candidates[0] if candidates else None
    # experimental: highest version across stable + pre-release
    scored = []
    for r in candidates:
        v = _parse_version(r.get("tag_name", ""))
        if v is not None:
            scored.append((v, r))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


class UpdateChecker(QObject):
    update_available = Signal(str, str)  # (tag_name, html_url)
    check_complete   = Signal()

    def check(self, repo: str, channel: str, current_version: str):
        t = threading.Thread(
            target=self._run,
            args=(repo, channel, current_version),
            daemon=True,
        )
        t.start()

    def _run(self, repo: str, channel: str, current_version: str):
        try:
            url = _API_URL.format(repo=repo)
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "OEL-Launcher"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                releases = json.loads(resp.read().decode())

            candidate = _pick_release(releases, channel)
            if candidate:
                current_v = _parse_version(current_version)
                candidate_v = _parse_version(candidate.get("tag_name", ""))
                if current_v is not None and candidate_v is not None and candidate_v > current_v:
                    self.update_available.emit(candidate["tag_name"], candidate["html_url"])
        except Exception:
            pass
        finally:
            self.check_complete.emit()
