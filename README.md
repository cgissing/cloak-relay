# Cloak Relay

Cloak Relay gives agents a local browser control layer backed by
CloakBrowser.

It runs a localhost HTTP service and an MCP stdio bridge. Agents can open a
session, navigate, read page snapshots, click, type, scroll, take screenshots,
and keep login state in persistent profiles. When a page needs user input, the
same profile can be reopened in a visible CloakBrowser window and then handed
back to the agent.

## Install On Linux Or WSL

Install with `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install git+https://github.com/cgissing/cloak-relay.git
```

Start the relay:

```bash
cloak-relay start
cloak-relay status
curl http://127.0.0.1:18796/health
```

Stop it:

```bash
cloak-relay stop
```

The service listens on:

```text
http://127.0.0.1:18796
```

Runtime data lives under:

```text
~/.local/share/cloak-relay
```

Profiles are stored under:

```text
~/.local/share/cloak-relay/profiles/<sessionId>
```

## Run At Login

On Linux, or WSL with systemd enabled:

```bash
cloak-relay install-service --start-now
```

This writes a user systemd unit to:

```text
~/.config/systemd/user/cloak-relay.service
```

If `systemctl --user` is not available, use the normal background runner:

```bash
cloak-relay start
```

Remove the service:

```bash
cloak-relay uninstall-service
```

## MCP Setup

Keep the HTTP service running, then point your agent to the MCP command:

```json
{
  "mcpServers": {
    "cloak-relay-mcp": {
      "command": "/home/you/.local/bin/cloak-relay-mcp",
      "env": {
        "CLOAK_RELAY_URL": "http://127.0.0.1:18796"
      }
    }
  }
}
```

Available tools:

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

## Typical Agent Flow

Start a normal headless session:

```bash
curl -s -X POST http://127.0.0.1:18796/api/session/start \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","headless":true,"humanize":true}'
```

Navigate:

```bash
curl -s -X POST http://127.0.0.1:18796/api/navigate \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","url":"https://example.com"}'
```

Read the page:

```bash
curl -s 'http://127.0.0.1:18796/api/snapshot?sessionId=default&format=text'
```

Click and type:

```bash
curl -s -X POST http://127.0.0.1:18796/api/click \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","selector":"button[type=submit]"}'

curl -s -X POST http://127.0.0.1:18796/api/type \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","selector":"input[name=q]","text":"hello","clear":true}'
```

## User Handoff

`headless:true` is the default. Use a visible window only when the task needs
the user, or when a headless run gets stuck.

Reopen the same session visibly:

```bash
curl -s -X POST http://127.0.0.1:18796/api/session/close \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default"}'

curl -s -X POST http://127.0.0.1:18796/api/session/start \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","headless":false,"humanize":true}'
```

After the user finishes in the browser window, the agent continues with the
same `sessionId`.

## Login State

Close the browser and keep login state:

```bash
curl -s -X POST http://127.0.0.1:18796/api/session/close \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default"}'
```

Delete the managed profile:

```bash
curl -s -X POST http://127.0.0.1:18796/api/session/clear \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default"}'
```

## Agent Skill

The repo includes a small Codex skill:

```text
skills/cloak-relay-agent/SKILL.md
```

Install it:

```bash
mkdir -p ~/.codex/skills
cp -r ./skills/cloak-relay-agent ~/.codex/skills/
```

The skill is only an operating guide for agents. It explains the relay URL,
the MCP tools, the default headless session, profile reuse, and the visible
handoff path.

## Development

Clone and run tests:

```bash
git clone https://github.com/cgissing/cloak-relay.git
cd cloak-relay
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m pytest -q
```

Run from source:

```bash
./.venv/bin/python -m cloak_relay.cli start
```

Windows is supported by the CLI, but this README keeps the main path focused
on Linux and WSL.

## License

Cloak Relay is released under the MIT License.

The relay code is open source in this repository. CloakBrowser is an upstream
runtime dependency and its browser binary is downloaded through CloakBrowser's
own distribution channel.

## Acknowledgements

This project recognizes and links to the LINUX DO community:

https://linux.do
