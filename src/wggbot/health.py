from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any


class HealthServer:
    """Small dependency-free HTTP health server for the container runtime."""

    def __init__(
        self,
        host: str,
        port: int,
        snapshot: Callable[[], tuple[int, dict[str, Any]]],
    ) -> None:
        self.host = host
        self.port = port
        self.snapshot = snapshot
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.read(4096), timeout=2)
            parts = request.split(b"\r\n", 1)[0].split(b" ")
            path = parts[1] if len(parts) >= 2 else b"/"
            if path not in {b"/", b"/health", b"/ready"}:
                status_code, reason = 404, "Not Found"
                payload: dict[str, Any] = {"status": "not_found"}
            else:
                status_code, payload = self.snapshot()
                reason = "OK" if status_code == 200 else "Service Unavailable"
            body = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
            writer.write(
                (
                    f"HTTP/1.1 {status_code} {reason}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
