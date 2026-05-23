from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import telnetlib3
from telnetlib3.telopt import GMCP


@dataclass
class ConnectionParams:
    host: str
    port: int
    encoding: str = "utf-8"


class TelnetConnection:
    def __init__(self) -> None:
        self.reader: telnetlib3.TelnetReaderUnicode | None = None
        self.writer: telnetlib3.TelnetWriterUnicode | None = None
        self.read_task: asyncio.Task[None] | None = None
        self.params: ConnectionParams | None = None

    async def connect(
        self,
        params: ConnectionParams,
        on_data: Callable[[str], Awaitable[None]],
        on_disconnect: Callable[[], Awaitable[None]],
        on_gmcp: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> None:
        self.params = params
        self.reader, self.writer = await telnetlib3.open_connection(
            host=params.host,
            port=params.port,
            encoding=params.encoding,
            connect_minwait=0.05,
            shell=None,
        )
        if self.writer and on_gmcp:
            def gmcp_callback(package: str, data: Any) -> None:
                asyncio.create_task(on_gmcp(package, data))

            self.writer.set_ext_callback(GMCP, gmcp_callback)

        self.read_task = asyncio.create_task(self._read_loop(on_data, on_disconnect))

    async def _read_loop(self, on_data: Callable[[str], Awaitable[None]], on_disconnect: Callable[[], Awaitable[None]]) -> None:
        assert self.reader is not None
        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                await on_data(chunk)
        except Exception:
            pass
        finally:
            await on_disconnect()

    async def send_line(self, line: str) -> None:
        if not self.writer:
            raise RuntimeError("Not connected")
        self.writer.write(line + "\r\n")
        await self.writer.drain()

    async def disconnect(self) -> None:
        if self.writer:
            self.writer.close()
        if self.read_task:
            self.read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.read_task
        self.reader = None
        self.writer = None
        self.read_task = None
