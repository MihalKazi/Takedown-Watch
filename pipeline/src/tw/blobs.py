"""Content-addressed store for raw fetched bytes (HTML, XML). Write-once: a blob is never modified."""

from __future__ import annotations

import gzip
import hashlib
import os
import tempfile
from pathlib import Path


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:4] / f"{digest}.gz"

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        if path.exists():
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
                gz.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return digest

    def get(self, digest: str) -> bytes:
        with gzip.open(self._path(digest), "rb") as fh:
            return fh.read()

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()
