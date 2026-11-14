"""CoStar data kit reader.

The kit is a password-protected zip (~160 MB) of property and listing records. A zip keeps its table of contents
at the end, so a remote kit is read with HTTP range requests: only the files we open are downloaded.
Commercial records join to Matterport models by CoStar property id; residential listings by Homes listing id.

List the kit's files and columns from backend/:  .venv/bin/python -m app.integrations.costar
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator

import httpx
import pyzipper

PROPERTY_ID_COLS = ("costar_property_id", "property_id", "propertyid", "costar_id")
LISTING_ID_COLS = ("homes_listing_id", "listing_id", "listingid")


class CostarError(RuntimeError):
    pass


class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests, with a small read-ahead buffer."""

    def __init__(self, url: str, http: httpx.Client | None = None, block: int = 1 << 20):
        self.url, self.http, self.block = url, http or httpx.Client(timeout=60, follow_redirects=True), block
        head = self.http.get(url, headers={"Range": "bytes=0-0"})
        if head.status_code != 206:
            raise CostarError(f"The kit link does not support range requests (HTTP {head.status_code}).")
        self.size = int(head.headers["content-range"].split("/")[-1])
        self.pos, self._buf, self._buf_at = 0, b"", 0
        self.requests = 1

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: offset, io.SEEK_CUR: self.pos + offset, io.SEEK_END: self.size + offset}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        if n == 0:
            return b""
        start, end = self.pos, self.pos + n
        if not (self._buf_at <= start and end <= self._buf_at + len(self._buf)):
            fetch_end = min(self.size, max(end, start + self.block)) - 1
            res = self.http.get(self.url, headers={"Range": f"bytes={start}-{fetch_end}"})
            self.requests += 1
            if res.status_code != 206:
                raise CostarError(f"Range request failed (HTTP {res.status_code}).")
            self._buf, self._buf_at = res.content, start
        out = self._buf[start - self._buf_at:end - self._buf_at]
        self.pos = end
        return out

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


class CostarKit:
    def __init__(self, zip_file, password: str):
        if not password:
            raise CostarError("CoStar zip password is not set (COSTAR_ZIP_PASSWORD).")
        try:
            self.zip = pyzipper.AESZipFile(zip_file)
        except pyzipper.BadZipFile as e:
            raise CostarError(f"Not a readable zip: {e}")
        self.zip.setpassword(password.encode())

    @classmethod
    def open(cls, *, path: str | None = None, url: str | None = None, password: str | None = None, http=None) -> "CostarKit":
        if path:
            if not Path(path).exists():
                raise CostarError(f"Kit zip not found at {path}.")
            return cls(path, password or "")
        if url:
            return cls(HttpRangeFile(url, http), password or "")
        raise CostarError("Set COSTAR_KIT_ZIP (a local path) or COSTAR_KIT_URL (the kit's download link).")

    def files(self) -> list[tuple[str, int]]:
        return [(i.filename, i.file_size) for i in self.zip.infolist() if not i.is_dir()]

    def find(self, contains: str) -> str:
        hits = [n for n, _ in self.files() if contains.lower() in n.lower()]
        if not hits:
            raise CostarError(f"No file in the kit matches '{contains}'.")
        return hits[0]

    def rows(self, name: str) -> Iterator[dict]:
        """Stream a CSV from the kit as dicts with lower-cased, stripped column names."""
        try:
            raw = self.zip.open(name)
        except RuntimeError as e:  # wrong password
            raise CostarError(f"Could not open {name}: {e}. Check COSTAR_ZIP_PASSWORD.")
        with raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            for row in csv.DictReader(text):
                yield {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}

    def columns(self, name: str) -> list[str]:
        return list(next(self.rows(name), {}).keys())

    def lookup(self, name: str, ids: set[str], id_cols: tuple[str, ...]) -> dict[str, dict]:
        """Rows whose id (first matching column) is in `ids`, keyed by id. One pass over the file."""
        found = {}
        for row in self.rows(name):
            rid = next((row[c] for c in id_cols if row.get(c)), None)
            if rid in ids:
                found[rid] = row
                if len(found) == len(ids):
                    break
        return found


if __name__ == "__main__":
    from ..settings import settings

    kit = CostarKit.open(path=settings.costar_kit_zip, url=settings.costar_kit_url, password=settings.costar_zip_password)
    for name, size in kit.files():
        cols = kit.columns(name) if name.lower().endswith(".csv") else []
        print(f"{size / 1e6:8.1f} MB  {name}")
        if cols:
            print("            " + ", ".join(cols[:25]) + (" …" if len(cols) > 25 else ""))
