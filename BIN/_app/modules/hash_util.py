import hashlib
from pathlib import Path


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    ):
        rel = p.relative_to(root).as_posix().encode("utf-8")
        # length-prefix so "a/bc" and "ab/c" cannot collide
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
    return h.hexdigest()
