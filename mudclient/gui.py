from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

from .ansi import sanitize_for_terminal
from .commands import parse_local_command, validate_host, validate_port
from .config import ConfigStore
from .logging_utils import SessionLogger
from .profiles import Profile, ProfileStore
from .telnet_connection import ConnectionParams, TelnetConnection


class MudGui:
    def __init__(self, host: str | None = None, port: int | None = None, profile: str | None = None, encoding: str = "utf-8") -> None:
        self.root = tk.Tk()
        self.root.title("MudClient")
        self.root.geometry("1000x700")

        self.config_store = ConfigStore()
        self.profile_store = ProfileStore()
        self.config = self.config_store.load()
        self.encoding = encoding or self.config.encoding
        self.logger = SessionLogger(keep_ansi=self.config.log_raw_ansi)

        self.host_var = tk.StringVar(value=host or "")
        self.port_var = tk.StringVar(value=str(port or ""))
        self.profile_var = tk.StringVar(value=profile or "")
        self.status_var = tk.StringVar(value="disconnected")

        self.loop = asyncio.new_event_loop()
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.conn = TelnetConnection()

        self._build_ui()
        self._start_loop_thread()
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.root.after(50, self._process_queue)

        if profile:
            p = self.profile_store.get(profile)
            if p:
                self.host_var.set(p.host)
                self.port_var.set(str(p.port))
                self.encoding = p.encoding
        if self.host_var.get() and self.port_var.get():
            self._submit(self.connect())

    def _build_ui(self) -> None:
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=8)
        for lbl, var, w in (("Host", self.host_var, 28), ("Port", self.port_var, 8), ("Profile", self.profile_var, 16)):
            tk.Label(top, text=lbl).pack(side=tk.LEFT)
            tk.Entry(top, textvariable=var, width=w).pack(side=tk.LEFT, padx=4)

        tk.Button(top, text="Connect", command=lambda: self._submit(self.connect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Disconnect", command=lambda: self._submit(self.disconnect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Reconnect", command=lambda: self._submit(self.reconnect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Profiles", command=self.show_profiles).pack(side=tk.LEFT, padx=3)

        self.output = tk.Text(self.root, wrap=tk.WORD, undo=False)
        self.output.pack(fill=tk.BOTH, expand=True, padx=8)

        bottom = tk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=8, pady=8)
        self.input = tk.Entry(bottom)
        self.input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input.bind("<Return>", lambda _e: self.on_enter())
        tk.Button(bottom, text="Send", command=self.on_enter).pack(side=tk.LEFT, padx=5)

        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill=tk.X, padx=8, pady=(0, 8))

    def _start_loop_thread(self) -> None:
        def run_loop() -> None:
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

    def _submit(self, coro: asyncio.Future | asyncio.coroutines) -> None:
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _process_queue(self) -> None:
        try:
            while True:
                kind, text = self.queue.get_nowait()
                if kind == "out":
                    self.output.insert(tk.END, text + "\n")
                    self.output.see(tk.END)
                elif kind == "status":
                    self.status_var.set(text)
        except queue.Empty:
            pass
        self.root.after(50, self._process_queue)

    async def _on_data(self, chunk: str) -> None:
        safe = sanitize_for_terminal(chunk)
        for line in (safe.splitlines() or [safe]):
            self.logger.write_line(line)
            self.queue.put(("out", line))
            for trig in self.config.triggers:
                if trig.enabled and trig.pattern in line and trig.response:
                    await self.conn.send_line(trig.response)

    async def _on_disconnect(self) -> None:
        self.queue.put(("status", "disconnected"))
        self.queue.put(("out", "[Disconnected]"))

    async def connect(self) -> None:
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            self.queue.put(("out", "[Invalid port]"))
            return
        if not validate_host(host) or not validate_port(port):
            self.queue.put(("out", "[Invalid host or port]"))
            return

        await self.disconnect()
        self.queue.put(("status", "connecting"))
        try:
            await self.conn.connect(ConnectionParams(host=host, port=port, encoding=self.encoding), self._on_data, self._on_disconnect)
            self.queue.put(("status", f"connected {host}:{port}"))
            self.queue.put(("out", f"[Connected to {host}:{port}]"))
        except Exception as exc:
            self.queue.put(("status", f"error: {exc}"))
            self.queue.put(("out", f"[Connection error: {exc}]"))

    async def disconnect(self) -> None:
        await self.conn.disconnect()
        self.queue.put(("status", "disconnected"))

    async def reconnect(self) -> None:
        await self.connect()

    def on_enter(self) -> None:
        text = self.input.get()
        self.input.delete(0, tk.END)
        self._submit(self.handle_input(text))

    async def handle_input(self, text: str) -> None:
        cmd = parse_local_command(text)
        if cmd:
            await self.run_command(cmd.name, cmd.args)
            return
        try:
            await self.conn.send_line(text)
        except Exception:
            self.queue.put(("out", "[Not connected]"))

    async def run_command(self, name: str, args: list[str]) -> None:
        if name == "quit":
            self.on_quit()
        elif name == "disconnect":
            await self.disconnect()
        elif name == "reconnect":
            await self.reconnect()
        elif name == "connect" and len(args) >= 2:
            self.host_var.set(args[0]); self.port_var.set(args[1]); await self.connect()
        elif name == "clear":
            self.queue.put(("out", "[Cleared]"))
            self.root.after(0, lambda: self.output.delete("1.0", tk.END))
        elif name == "profiles":
            for p in self.profile_store.list_profiles():
                self.queue.put(("out", f"{p.name}: {p.host}:{p.port} ({p.encoding})"))
        elif name == "saveprofile" and args:
            try:
                port = int(self.port_var.get())
            except ValueError:
                self.queue.put(("out", "[Invalid port]")); return
            self.profile_store.save_profile(Profile(name=args[0], host=self.host_var.get(), port=port, encoding=self.encoding))
            self.queue.put(("out", f"[Saved profile {args[0]}]"))
        elif name == "loadprofile" and args:
            p = self.profile_store.get(args[0])
            if not p:
                self.queue.put(("out", "[Profile not found]")); return
            self.host_var.set(p.host); self.port_var.set(str(p.port)); self.encoding = p.encoding
            await self.connect()
        elif name == "deleteprofile" and args:
            self.queue.put(("out", "[Deleted]" if self.profile_store.delete_profile(args[0]) else "[Profile not found]"))
        elif name == "set" and len(args) >= 2:
            if args[0] == "encoding":
                self.encoding = " ".join(args[1:])
                self.config.encoding = self.encoding
                self.config_store.save(self.config)
                self.queue.put(("out", "[encoding updated]"))
        elif name == "log" and args:
            if args[0] == "start":
                self.queue.put(("out", f"[Logging to {self.logger.start()}]"))
            elif args[0] == "stop":
                self.logger.stop(); self.queue.put(("out", "[Logging stopped]"))
        else:
            self.queue.put(("out", "[Unknown local command, try /help]"))

    def show_profiles(self) -> None:
        profiles = self.profile_store.list_profiles()
        if not profiles:
            messagebox.showinfo("Profiles", "No profiles saved")
            return
        messagebox.showinfo("Profiles", "\n".join(f"{p.name}: {p.host}:{p.port}" for p in profiles))

    def on_quit(self) -> None:
        self._submit(self.disconnect())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_gui(host: str | None = None, port: int | None = None, profile: str | None = None, encoding: str = "utf-8") -> None:
    MudGui(host=host, port=port, profile=profile, encoding=encoding).run()
