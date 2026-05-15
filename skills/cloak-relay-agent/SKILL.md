---
name: cloak-relay-agent
description: Use when an agent needs to control a local Cloak Relay browser service backed by CloakBrowser, including navigation, page snapshots, clicking, typing, scrolling, screenshots, persistent login sessions, and human handoff in a visible browser window.
---

# Cloak Relay Agent

Use Cloak Relay as the browser control layer when the task needs a real local browser session with CloakBrowser fingerprints, persistent profiles, and humanized Playwright actions.

## Preferred Path

1. Check the relay is alive:
   - MCP: `browser_health`
   - HTTP: `GET http://127.0.0.1:18796/health`
2. Start or reuse a normal headless session:
   - MCP: `browser_start_session`
   - Default arguments: `{"sessionId":"default","headless":true,"humanize":true}`
3. Navigate:
   - MCP: `browser_navigate`
4. Inspect before acting:
   - MCP: `browser_snapshot`
   - Use `browser_screenshot` when layout or visual state matters.
5. Act through relay tools:
   - Click: `browser_click`
   - Type: `browser_type`
   - Scroll: `browser_scroll`

Prefer MCP tools when available. Use the HTTP API only when MCP is unavailable.

## Session Defaults

Use `sessionId: "default"` unless the user or task needs isolation.

Use `headless: true` by default so the agent can complete predictable tasks without opening a user-visible window.

Use `headless: false` only when the task obviously requires user involvement from the start, or after the headless session hits a wall and the user needs to help in a visible browser window.

Use `humanize: true` by default. Cloak Relay routes click, type, and scroll through CloakBrowser/Playwright high-level actions, so avoid replacing those actions with raw JavaScript or CDP events.

## Common MCP Calls

Start a normal headless session:

```json
{
  "sessionId": "default",
  "headless": true,
  "humanize": true
}
```

Reopen the same profile in a visible window for user handoff:

```json
{
  "sessionId": "default",
  "headless": false,
  "humanize": true
}
```

Navigate:

```json
{
  "sessionId": "default",
  "url": "https://example.com"
}
```

Click:

```json
{
  "sessionId": "default",
  "selector": "button[type=submit]"
}
```

Type:

```json
{
  "sessionId": "default",
  "selector": "input[name=q]",
  "text": "search text",
  "clear": true,
  "submit": false
}
```

Snapshot:

```json
{
  "sessionId": "default",
  "format": "text"
}
```

## Human Handoff

When the page needs login, 2FA, payment confirmation, or human verification, first stop browser actions. If the current session is headless, call `browser_close_session`, then call `browser_start_session` with the same `sessionId` and `headless:false`. Tell the user to complete the step in the visible CloakBrowser window. After the user says it is done, continue with the same `sessionId`.

Do not clear the profile after handoff unless the user explicitly asks.

## Profile Control

Close the browser while keeping login state:

```json
{
  "sessionId": "default"
}
```

Clear login state only when requested:

```json
{
  "sessionId": "default"
}
```

Use `browser_close_session` for close-with-state and `browser_clear_session` for deleting the managed profile.

## If Relay Is Not Running

If you can run local shell commands in the project, start it:

Windows:

```powershell
.\.venv\Scripts\cloak-relay.exe start
```

Linux or WSL:

```bash
./.venv/bin/python -m cloak_relay.cli start
```

Then retry `browser_health`.

## HTTP Fallback

Health:

```bash
curl http://127.0.0.1:18796/health
```

Navigate:

```bash
curl -s -X POST http://127.0.0.1:18796/api/navigate \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"default","url":"https://example.com"}'
```

Snapshot:

```bash
curl -s 'http://127.0.0.1:18796/api/snapshot?sessionId=default&format=text'
```

## Practical Loop

For most browsing tasks:

1. `browser_health`
2. `browser_start_session` with `headless:true`
3. `browser_navigate`
4. `browser_snapshot`
5. `browser_click` / `browser_type` / `browser_scroll`
6. `browser_snapshot` or `browser_screenshot`
7. Repeat until done.

When the task clearly needs user participation, start with `headless:false`. When a headless task gets blocked by login, 2FA, or verification, close and reopen the same `sessionId` with `headless:false`.
