# Python Terminal MUD Client

Async Telnet MUD client for Python 3.11+ using `telnetlib3` and `prompt_toolkit`.

## Installation

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Run

```bash
python -m mudclient --host example.com --port 4000
```

Arguments:
- `--host`
- `--port`
- `--profile`
- `--encoding`

If host/port are omitted, the app prompts interactively.

## Profiles

Profiles are saved as JSON in the user config directory (`AppData/Local/mudclient` on Windows).
Each profile includes name, host, port, encoding, notes, and optional auto-login command list.

## Slash Commands

- `/help`
- `/connect host port`
- `/disconnect`
- `/reconnect`
- `/quit`
- `/clear`
- `/profiles`
- `/saveprofile name`
- `/loadprofile name`
- `/deleteprofile name`
- `/set key value`
- `/log start`
- `/log stop`

Normal commands are sent to the MUD unchanged unless they begin with a recognized slash command.

## ANSI and Output Safety

- ANSI colors from servers are preserved in terminal output where supported.
- Session logs strip ANSI by default.
- Basic control-character sanitization is applied to reduce obvious terminal escape abuse.

## Compatibility

- Python 3.11+
- Works as a local terminal client on Windows, Linux, and macOS.

## Troubleshooting

- Connection errors: verify host/port and firewall settings.
- Garbled text: try `/set encoding cp1252` (or server-specific encoding).
- If disconnected, use `/reconnect`.

## Trigger Safety Note

Triggers can automatically send commands. Some MUDs treat automation as botting; configure and use cautiously.
