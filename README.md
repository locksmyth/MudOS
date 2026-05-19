# Python MUD Client (GUI + Terminal)

Async Telnet MUD client for Python 3.11+ using `telnetlib3`.

## Installation

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Run

### GUI window (default)
```bash
python -m mudclient --host example.com --port 4000
```

### Terminal UI mode
```bash
python -m mudclient --terminal --host example.com --port 4000
```

Arguments:
- `--host`
- `--port`
- `--profile`
- `--encoding`
- `--terminal` (force prompt_toolkit terminal mode)

If host/port are omitted, the client prompts (terminal mode) or lets you enter fields (GUI mode).

## Profiles

Profiles are stored in JSON under user config dir (`AppData/Local/mudclient` on Windows).

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

## ANSI and compatibility

- Incoming ANSI colors are preserved in live output where supported.
- Logs strip ANSI by default.
- Python 3.11+

## Troubleshooting

- Connection failures: verify host/port/firewall.
- Garbled text: try `/set encoding cp1252` or server-specific encoding.
- Trigger automation may violate some MUD rules; use cautiously.
