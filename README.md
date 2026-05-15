# Cloak Relay

Cloak Relay is a local Browser Relay-like service for agents. It exposes an HTTP API and an MCP stdio bridge, but the actual browser is launched through CloakBrowser persistent contexts instead of a Chrome extension.

This is an independent relay service. It depends on CloakBrowser at runtime but does not redistribute the CloakBrowser Chromium binary.

The intended flow is:

1. Start the local HTTP service in the background.
2. Register the MCP bridge with an agent.
3. Let the agent navigate, click, type, scroll, and inspect pages through the MCP tools.
4. When login, 2FA, or human verification is needed, reopen the same session in a visible CloakBrowser window, let the user complete the step, then let the agent continue.

This project does not automate verification bypass.

## Install

From this directory:

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev,cloak]"
```

Linux or WSL:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev,cloak]"
```

CloakBrowser downloads its own Chromium binary. You do not need `playwright install chromium`.

To pre-download the CloakBrowser binary:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloakbrowser install
```

Linux or WSL:

```bash
./.venv/bin/python -m cloakbrowser install
```

## Run In Foreground

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli serve
```

Linux or WSL:

```bash
./.venv/bin/python -m cloak_relay.cli serve
```

Default URL:

```text
http://127.0.0.1:18796
```

Health check:

Windows PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/health
```

Linux or WSL:

```bash
curl http://127.0.0.1:18796/health
```

## Run In Background

Start:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli start
```

Linux or WSL:

```bash
./.venv/bin/python -m cloak_relay.cli start
```

Status:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli status
```

Linux or WSL:

```bash
./.venv/bin/python -m cloak_relay.cli status
```

Stop:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli stop
```

Linux or WSL:

```bash
./.venv/bin/python -m cloak_relay.cli stop
```

Logs:

```text
~/.local/share/cloak-relay/logs/cloak-relay.log
```

PID file:

```text
~/.local/share/cloak-relay/cloak-relay.pid
```

## Install Background Startup

On Windows, install a user-level Task Scheduler entry that starts Cloak Relay at logon:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli install-service --start-now
```

On Linux, install a user-level systemd service:

```bash
./.venv/bin/python -m cloak_relay.cli install-service --start-now
```

On WSL, the same command works when WSL systemd is enabled. If `systemctl --user` is not available, use the PID-based background runner:

```bash
./.venv/bin/python -m cloak_relay.cli start
```

The Linux/WSL systemd unit is written to:

```text
~/.config/systemd/user/cloak-relay.service
```

Aliases:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli enable --start-now
.\.venv\Scripts\python -m cloak_relay.cli disable
```

Linux or WSL with systemd:

```bash
./.venv/bin/python -m cloak_relay.cli enable --start-now
./.venv/bin/python -m cloak_relay.cli disable
```

Uninstall:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m cloak_relay.cli uninstall-service
```

Linux or WSL with systemd:

```bash
./.venv/bin/python -m cloak_relay.cli uninstall-service
```

The service uses the current Python executable, so create it from the `.venv` you want agents to use.

## HTTP API

Start or reuse a normal headless humanized session:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/session/start `
  -Method Post `
  -ContentType application/json `
  -Body '{"sessionId":"default","headless":true,"humanize":true}'
```

CloakBrowser itself defaults to `headless=true`. Cloak Relay also defaults to `headless=true`. Use `headless=false` only when the task clearly needs user involvement from the start, or when a headless run gets blocked by login, 2FA, or verification.

Reopen the same profile in a visible window for user handoff:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/session/close `
  -Method Post `
  -ContentType application/json `
  -Body '{"sessionId":"default"}'

Invoke-RestMethod http://127.0.0.1:18796/api/session/start `
  -Method Post `
  -ContentType application/json `
  -Body '{"sessionId":"default","headless":false,"humanize":true}'
```

Navigate:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/navigate `
  -Method Post `
  -ContentType application/json `
  -Body '{"url":"https://example.com"}'
```

Snapshot:

```powershell
Invoke-RestMethod "http://127.0.0.1:18796/api/snapshot?format=text"
```

Click:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/click `
  -Method Post `
  -ContentType application/json `
  -Body '{"selector":"button[type=submit]"}'
```

Type:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/type `
  -Method Post `
  -ContentType application/json `
  -Body '{"selector":"input[name=q]","text":"hello","clear":true,"submit":true}'
```

Clear login state for the default session:

```powershell
Invoke-RestMethod http://127.0.0.1:18796/api/session/clear `
  -Method Post `
  -ContentType application/json `
  -Body '{"sessionId":"default"}'
```

## MCP Registration

The MCP process is not the browser service. Keep the HTTP service running in the background, then point the agent to the stdio bridge.

Example MCP config shape:

Windows:

```json
{
  "mcpServers": {
    "cloak-relay-mcp": {
      "command": "C:\\path\\to\\cloak-relay\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "cloak_relay.mcp_server"
      ],
      "env": {
        "CLOAK_RELAY_URL": "http://127.0.0.1:18796"
      }
    }
  }
}
```

Linux or WSL:

```json
{
  "mcpServers": {
    "cloak-relay-mcp": {
      "command": "/home/you/path/to/cloak-relay/.venv/bin/python",
      "args": [
        "-m",
        "cloak_relay.mcp_server"
      ],
      "env": {
        "CLOAK_RELAY_URL": "http://127.0.0.1:18796"
      }
    }
  }
}
```

Available MCP tools:

- `browser_health`
- `browser_tabs`
- `browser_start_session`
- `browser_close_session`
- `browser_clear_session`
- `browser_navigate`
- `browser_snapshot`
- `browser_click`
- `browser_type`
- `browser_scroll`
- `browser_screenshot`
- `browser_eval`

## Agent Skill

This repo includes a lightweight agent skill:

```text
skills/cloak-relay-agent/SKILL.md
```

Use it when an agent needs a short operating guide for Cloak Relay: check health, start a headless session, navigate, snapshot, click, type, scroll, screenshot, and reopen the same session visibly only when user handoff is needed.

Install it into a Codex skills directory by copying the folder:

Windows PowerShell:

```powershell
Copy-Item -Recurse -Force `
  .\skills\cloak-relay-agent `
  "$env:USERPROFILE\.codex\skills\cloak-relay-agent"
```

Linux or WSL:

```bash
mkdir -p ~/.codex/skills
cp -r ./skills/cloak-relay-agent ~/.codex/skills/
```

The skill is intentionally small. It does not add a large policy layer; it mainly tells the agent how to use the relay and when to reopen a visible browser window for user help.

## Profiles And Login State

Profiles live under:

```text
~/.local/share/cloak-relay/profiles/<sessionId>
```

The default session stores cookies, localStorage, cache, and other persistent browser state in:

```text
~/.local/share/cloak-relay/profiles/default
```

Use `browser_close_session` or `/api/session/close` to close the browser while keeping login state. Use `browser_clear_session` or `/api/session/clear` to delete the managed profile.

## Development

Run unit tests:

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m pytest -v
```

Linux or WSL:

```bash
./.venv/bin/python -m pytest -v
```

The default test suite does not launch or download CloakBrowser. Real browser smoke tests should be gated behind an explicit environment variable before being added.

## License

This project is released under the MIT License. CloakBrowser wrapper code is MIT licensed, but the compiled CloakBrowser Chromium binary is governed by CloakHQ's separate binary license and is downloaded from official CloakBrowser distribution channels at runtime.
