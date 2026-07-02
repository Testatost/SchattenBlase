from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from config import CACHE_DIR, OSM_TILE_URL, OSM_USER_AGENT


class TileManager(QObject):
    tile_ready = Signal(int, int, int, QPixmap)
    tile_failed = Signal(int, int, int)

    def __init__(self, cache_dir: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._network = QNetworkAccessManager(self)
        self._pending: dict[QNetworkReply, tuple[int, int, int, Path]] = {}
        self._inflight: set[tuple[int, int, int]] = set()
        self.offline_only = False

    def set_offline_only(self, enabled: bool) -> None:
        self.offline_only = enabled

    def cancel_except_zoom(self, zoom: int) -> None:
        for reply, (z, x, y, _path) in list(self._pending.items()):
            if z != zoom:
                self._inflight.discard((z, x, y))
                reply.abort()

    def tile_path(self, z: int, x: int, y: int) -> Path:
        return self.cache_dir / str(z) / str(x) / f"{y}.png"

    def request_tile(self, z: int, x: int, y: int) -> None:
        key = (z, x, y)
        if key in self._inflight:
            return
        path = self.tile_path(z, x, y)
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.tile_ready.emit(z, x, y, pixmap)
                return
        if self.offline_only:
            self.tile_failed.emit(z, x, y)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        url = QUrl(OSM_TILE_URL.format(z=z, x=x, y=y))
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, OSM_USER_AGENT)
        reply = self._network.get(request)
        self._pending[reply] = (z, x, y, path)
        self._inflight.add(key)
        reply.finished.connect(lambda r=reply: self._finished(r))

    def _finished(self, reply: QNetworkReply) -> None:
        z, x, y, path = self._pending.pop(reply, (0, 0, 0, Path()))
        self._inflight.discard((z, x, y))
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.tile_failed.emit(z, x, y)
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            path.write_bytes(data)
            self.tile_ready.emit(z, x, y, pixmap)
        else:
            self.tile_failed.emit(z, x, y)
        reply.deleteLater()
