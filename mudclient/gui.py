from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from typing import Any
from tkinter import messagebox, simpledialog

from .ansi import sanitize_for_terminal, split_ansi_segments
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
        self.gmcp_connected = False

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
        for lbl, var, w in (("Host", self.host_var, 28), ("Port", self.port_var, 8)):
            tk.Label(top, text=lbl).pack(side=tk.LEFT)
            tk.Entry(top, textvariable=var, width=w).pack(side=tk.LEFT, padx=4)

        tk.Button(top, text="Connect", command=lambda: self._submit(self.connect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Disconnect", command=lambda: self._submit(self.disconnect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Reconnect", command=lambda: self._submit(self.reconnect())).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Profiles", command=self.open_profiles_dialog).pack(side=tk.LEFT, padx=3)
        tk.Button(top, text="Dark Mode", command=self.toggle_dark_mode).pack(side=tk.LEFT, padx=3)

        self.output = tk.Text(self.root, wrap=tk.WORD, undo=False)
        self.dark_mode = True
        self._configure_ansi_tags()
        self.output.pack(fill=tk.BOTH, expand=True, padx=8)

        self.room_label = tk.Label(self.root, text="Room", anchor="w")
        self.room_label.pack(fill=tk.X, padx=8, pady=(6, 0))
        self.room_output = tk.Text(self.root, wrap=tk.WORD, height=6, undo=False)
        self.room_output.pack(fill=tk.X, padx=8)
        self._update_room_description("No room data yet")

        bottom = tk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=8, pady=8)
        self.input = tk.Entry(bottom)
        self.input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input.bind("<Return>", lambda _e: self.on_enter())
        tk.Button(bottom, text="Send", command=self.on_enter).pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill=tk.X, padx=8, pady=(0, 8))

        gmcp_row = tk.Frame(self.root)
        gmcp_row.pack(fill=tk.X, padx=8, pady=(0, 8), anchor="w")
        tk.Label(gmcp_row, text="GMCP").pack(side=tk.LEFT)
        self.gmcp_indicator = tk.Canvas(gmcp_row, width=14, height=14, highlightthickness=0, bd=0)
        self.gmcp_indicator.pack(side=tk.LEFT, padx=(6, 0))
        self.gmcp_light = self.gmcp_indicator.create_oval(2, 2, 12, 12, fill="#6b6b6b", outline="#4f4f4f")

        self._apply_theme()


    def _configure_ansi_tags(self) -> None:
        colors = {
            "30": "#000000", "31": "#ff5f5f", "32": "#5fff5f", "33": "#ffd75f",
            "34": "#5f87ff", "35": "#d787ff", "36": "#5fffff", "37": "#e4e4e4",
            "90": "#808080", "91": "#ff8080", "92": "#80ff80", "93": "#ffe680",
            "94": "#80aaff", "95": "#e0a0ff", "96": "#80ffff", "97": "#ffffff",
        }
        for code, color in colors.items():
            self.output.tag_configure(f"ansi_{code}", foreground=color)

    def _apply_theme(self) -> None:
        if self.dark_mode:
            bg, fg = "#111111", "#f0f0f0"
            input_bg, input_fg = "#1b1b1b", "#f0f0f0"
        else:
            bg, fg = "#ffffff", "#111111"
            input_bg, input_fg = "#ffffff", "#111111"
        self.root.configure(bg=bg)
        self.output.configure(bg=bg, fg=fg, insertbackground=fg)
        self.room_label.configure(bg=bg, fg=fg)
        self.room_output.configure(bg=input_bg, fg=input_fg, insertbackground=input_fg)
        self.input.configure(bg=input_bg, fg=input_fg, insertbackground=input_fg)
        self.status_label.configure(bg=bg, fg=fg)
        self.gmcp_indicator.configure(bg=bg)
        self._set_gmcp_indicator(self.gmcp_connected)

    def _set_gmcp_indicator(self, connected: bool) -> None:
        self.gmcp_connected = connected
        if connected:
            fill, outline = "#2ecc71", "#1e8449"
        else:
            fill, outline = "#6b6b6b", "#4f4f4f"
        self.gmcp_indicator.itemconfig(self.gmcp_light, fill=fill, outline=outline)

    def toggle_dark_mode(self) -> None:
        self.dark_mode = not self.dark_mode
        self._apply_theme()

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
                    for segment, style in split_ansi_segments(text):
                        if style:
                            self.output.insert(tk.END, segment, style)
                        else:
                            self.output.insert(tk.END, segment)
                    self.output.insert(tk.END, "\n")
                    self.output.see(tk.END)
                elif kind == "status":
                    self.status_var.set(text)
                elif kind == "room":
                    self._update_room_description(text)
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

    def _update_room_description(self, text: str) -> None:
        self.room_output.configure(state=tk.NORMAL)
        self.room_output.delete("1.0", tk.END)
        self.room_output.insert(tk.END, text)
        self.room_output.configure(state=tk.DISABLED)

    def _format_room_info(self, data: Any) -> str | None:
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or "").strip()
        area = str(data.get("area") or "").strip()
        desc = str(data.get("description") or data.get("desc") or "").strip()
        lines: list[str] = []
        if name:
            lines.append(name)
        if area:
            lines.append(f"Area: {area}")
        if desc:
            lines.extend(["", desc])
        return "\n".join(lines) if lines else None

    async def _on_gmcp(self, package: str, data: Any) -> None:
        if not self.gmcp_connected:
            self.root.after(0, lambda: self._set_gmcp_indicator(True))
        if package.lower() != "room.info":
            return
        room_text = self._format_room_info(data)
        if room_text:
            self.queue.put(("room", room_text))

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
        self.root.after(0, lambda: self._set_gmcp_indicator(False))
        self.queue.put(("status", "connecting"))
        try:
            await self.conn.connect(ConnectionParams(host=host, port=port, encoding=self.encoding), self._on_data, self._on_disconnect, self._on_gmcp)
            self.queue.put(("status", f"connected {host}:{port}"))
            self.queue.put(("out", f"[Connected to {host}:{port}]"))
        except Exception as exc:
            self.queue.put(("status", f"error: {exc}"))
            self.queue.put(("out", f"[Connection error: {exc}]"))

    async def disconnect(self) -> None:
        await self.conn.disconnect()
        self.root.after(0, lambda: self._set_gmcp_indicator(False))
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


    def open_profiles_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Profiles")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("520x320")

        main = tk.Frame(dialog)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        list_frame = tk.Frame(main)
        list_frame.pack(fill=tk.BOTH, expand=True)
        profile_list = tk.Listbox(list_frame)
        profile_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=profile_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        profile_list.configure(yscrollcommand=scrollbar.set)

        details_var = tk.StringVar(value="Select a profile")
        tk.Label(main, textvariable=details_var, anchor="w").pack(fill=tk.X, pady=(8, 8))

        button_bar = tk.Frame(main)
        button_bar.pack(fill=tk.X)

        def refresh(selected_name: str | None = None) -> None:
            profiles = self.profile_store.list_profiles()
            profile_list.delete(0, tk.END)
            for p in profiles:
                profile_list.insert(tk.END, p.name)
            if selected_name:
                names = [p.name for p in profiles]
                if selected_name in names:
                    idx = names.index(selected_name)
                    profile_list.selection_set(idx)
                    profile_list.activate(idx)
                    profile_list.see(idx)
                    update_details()

        def selected_profile() -> Profile | None:
            selected = profile_list.curselection()
            if not selected:
                return None
            name = profile_list.get(selected[0])
            return self.profile_store.get(name)

        def update_details(_event: object | None = None) -> None:
            p = selected_profile()
            if not p:
                details_var.set("Select a profile")
                return
            details_var.set(f"{p.name}: {p.host}:{p.port} ({p.encoding})")

        def save_current() -> None:
            host = self.host_var.get().strip()
            try:
                port = int(self.port_var.get().strip())
            except ValueError:
                messagebox.showerror("Save Profile", "Port must be a number", parent=dialog)
                return
            if not validate_host(host) or not validate_port(port):
                messagebox.showerror("Save Profile", "Host or port is invalid", parent=dialog)
                return

            default_name = ""
            current = selected_profile()
            if current:
                default_name = current.name
            name = simpledialog.askstring("Save Profile", "Profile name:", initialvalue=default_name, parent=dialog)
            if not name:
                return
            name = name.strip()
            if not name:
                messagebox.showerror("Save Profile", "Profile name cannot be empty", parent=dialog)
                return
            self.profile_store.save_profile(Profile(name=name, host=host, port=port, encoding=self.encoding))
            self.queue.put(("out", f"[Saved profile {name}]"))
            refresh(name)

        def load_selected() -> None:
            p = selected_profile()
            if not p:
                messagebox.showerror("Load Profile", "Select a profile first", parent=dialog)
                return
            self.host_var.set(p.host)
            self.port_var.set(str(p.port))
            self.encoding = p.encoding
            self.queue.put(("out", f"[Loaded profile {p.name}]"))

        def connect_selected() -> None:
            load_selected()
            self._submit(self.connect())

        def delete_selected() -> None:
            p = selected_profile()
            if not p:
                messagebox.showerror("Delete Profile", "Select a profile first", parent=dialog)
                return
            if not messagebox.askyesno("Delete Profile", f"Delete profile '{p.name}'?", parent=dialog):
                return
            self.profile_store.delete_profile(p.name)
            self.queue.put(("out", f"[Deleted profile {p.name}]"))
            refresh()

        tk.Button(button_bar, text="Save Current", command=save_current).pack(side=tk.LEFT, padx=3)
        tk.Button(button_bar, text="Load", command=load_selected).pack(side=tk.LEFT, padx=3)
        tk.Button(button_bar, text="Load + Connect", command=connect_selected).pack(side=tk.LEFT, padx=3)
        tk.Button(button_bar, text="Delete", command=delete_selected).pack(side=tk.LEFT, padx=3)
        tk.Button(button_bar, text="Close", command=dialog.destroy).pack(side=tk.RIGHT, padx=3)

        profile_list.bind("<<ListboxSelect>>", update_details)
        profile_list.bind("<Double-1>", lambda _e: load_selected())

        refresh()


    def on_quit(self) -> None:
        self._submit(self.disconnect())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_gui(host: str | None = None, port: int | None = None, profile: str | None = None, encoding: str = "utf-8") -> None:
    MudGui(host=host, port=port, profile=profile, encoding=encoding).run()
