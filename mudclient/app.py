from __future__ import annotations

import argparse
import asyncio
from enum import Enum

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import D

from .ansi import sanitize_for_terminal
from .commands import parse_local_command, validate_host, validate_port
from .config import ClientConfig, ConfigStore
from .logging_utils import SessionLogger
from .profiles import Profile, ProfileStore
from .telnet_connection import ConnectionParams, TelnetConnection
from .gui import run_gui


class ConnState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MudClient:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config_store = ConfigStore()
        self.profile_store = ProfileStore()
        self.config: ClientConfig = self.config_store.load()
        self.connection = TelnetConnection()
        self.logger = SessionLogger(keep_ansi=self.config.log_raw_ansi)
        self.state = ConnState.DISCONNECTED
        self.output_lines: list[str] = []
        self.status = "disconnected"

        self.output_control = FormattedTextControl(text=self._render_output)
        self.output_window = Window(content=self.output_control, wrap_lines=True, always_hide_cursor=True)
        self.input_buffer = Buffer(accept_handler=self._on_enter, history=InMemoryHistory())
        self.input_window = Window(content=BufferControl(self.input_buffer), height=D.exact(1))
        self.status_control = FormattedTextControl(text=lambda: self.status)
        self.app = Application(layout=Layout(HSplit([self.output_window, self.input_window, Window(content=self.status_control, height=1)])), key_bindings=self._bindings(), full_screen=True)

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _quit(_: object) -> None:
            self.app.exit(result="quit")

        return kb

    def _render_output(self) -> ANSI:
        return ANSI("\n".join(self.output_lines[-5000:]))

    def _append_output(self, text: str) -> None:
        self.output_lines.extend(text.splitlines() or [text])
        self.app.invalidate()

    async def _handle_server_data(self, chunk: str) -> None:
        safe = sanitize_for_terminal(chunk)
        for line in safe.splitlines() or [safe]:
            self.logger.write_line(line)
            self._append_output(line)
            await self._check_triggers(line)

    async def _check_triggers(self, line: str) -> None:
        for trig in self.config.triggers:
            if trig.enabled and trig.pattern in line and trig.response:
                await self.connection.send_line(trig.response)

    async def _on_disconnect(self) -> None:
        self.state = ConnState.DISCONNECTED
        self.status = "disconnected"
        self._append_output("[Disconnected]")

    def _on_enter(self, buffer: Buffer) -> bool:
        text = buffer.text
        buffer.document = Document(text="")
        asyncio.create_task(self._handle_input(text))
        return True

    async def _handle_input(self, text: str) -> None:
        cmd = parse_local_command(text)
        if cmd:
            await self._run_local_command(cmd.name, cmd.args)
            return
        if self.state != ConnState.CONNECTED:
            self._append_output("[Not connected]")
            return
        await self.connection.send_line(text)

    async def _run_local_command(self, name: str, args: list[str]) -> None:
        if name == "help":
            self._append_output("/connect host port | /disconnect | /reconnect | /quit | /clear | /profiles | /saveprofile name | /loadprofile name | /deleteprofile name | /set key value | /log start|stop")
        elif name == "connect" and len(args) >= 2:
            await self.connect(args[0], int(args[1]))
        elif name == "disconnect":
            await self.disconnect()
        elif name == "reconnect":
            if self.connection.params:
                await self.connect(self.connection.params.host, self.connection.params.port)
        elif name == "quit":
            await self.disconnect()
            self.app.exit(result="quit")
        elif name == "clear":
            self.output_lines.clear()
        elif name == "profiles":
            for p in self.profile_store.list_profiles():
                self._append_output(f"{p.name}: {p.host}:{p.port} ({p.encoding})")
        elif name == "saveprofile" and args:
            if not self.connection.params:
                self._append_output("[No active connection]")
                return
            p = Profile(name=args[0], host=self.connection.params.host, port=self.connection.params.port, encoding=self.connection.params.encoding)
            self.profile_store.save_profile(p)
            self._append_output(f"[Saved profile {args[0]}]")
        elif name == "loadprofile" and args:
            p = self.profile_store.get(args[0])
            if not p:
                self._append_output("[Profile not found]")
                return
            await self.connect(p.host, p.port, p.encoding)
        elif name == "deleteprofile" and args:
            ok = self.profile_store.delete_profile(args[0])
            self._append_output("[Deleted]" if ok else "[Profile not found]")
        elif name == "set" and len(args) >= 2:
            key, value = args[0], " ".join(args[1:])
            if key == "encoding":
                self.config.encoding = value
                self.config_store.save(self.config)
                self._append_output("[encoding updated]")
        elif name == "log" and args:
            if args[0] == "start":
                path = self.logger.start()
                self._append_output(f"[Logging to {path}]")
            elif args[0] == "stop":
                self.logger.stop()
                self._append_output("[Logging stopped]")

    async def connect(self, host: str, port: int, encoding: str | None = None) -> None:
        if not validate_host(host) or not validate_port(port):
            self._append_output("[Invalid host or port]")
            return
        await self.disconnect()
        self.state = ConnState.CONNECTING
        self.status = "connecting"
        try:
            await self.connection.connect(ConnectionParams(host=host, port=port, encoding=encoding or self.config.encoding), self._handle_server_data, self._on_disconnect)
            self.state = ConnState.CONNECTED
            self.status = f"connected {host}:{port}"
            self._append_output(f"[Connected to {host}:{port}]")
        except Exception as exc:
            self.state = ConnState.ERROR
            self.status = f"error: {exc}"
            self._append_output(f"[Connection error: {exc}]")

    async def disconnect(self) -> None:
        await self.connection.disconnect()
        self.state = ConnState.DISCONNECTED
        self.status = "disconnected"

    async def run(self) -> None:
        host = self.args.host
        port = self.args.port
        if self.args.profile:
            prof = self.profile_store.get(self.args.profile)
            if prof:
                host, port = prof.host, prof.port
        if not host:
            host = input("Host: ").strip()
        if not port:
            port = int(input("Port: ").strip())
        if host and port:
            await self.connect(host, int(port), self.args.encoding)
        await self.app.run_async()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Terminal MUD client")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--profile")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--terminal", action="store_true", help="Use terminal UI instead of GUI window")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if not args.terminal:
        run_gui(host=args.host, port=args.port, profile=args.profile, encoding=args.encoding)
        return
    try:
        client = MudClient(args)
        asyncio.run(client.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
