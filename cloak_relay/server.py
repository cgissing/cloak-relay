from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from .browser_manager import BrowserManager, BrowserSession
from .models import bool_from_value, get_session_id


Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
MANAGER_KEY = web.AppKey("manager", Any)


def create_app(manager: Any | None = None) -> web.Application:
    app = web.Application(middlewares=[error_middleware])
    app[MANAGER_KEY] = manager or BrowserManager(default_profiles_root())
    app.add_routes(
        [
            web.get("/", handle_health),
            web.get("/health", handle_health),
            web.get("/api/tabs", handle_tabs),
            web.post("/api/session/start", handle_session_start),
            web.post("/api/session/close", handle_session_close),
            web.post("/api/session/clear", handle_session_clear),
            web.post("/api/navigate", handle_navigate),
            web.get("/api/snapshot", handle_snapshot),
            web.post("/api/click", handle_click),
            web.post("/api/type", handle_type),
            web.post("/api/scroll", handle_scroll),
            web.get("/api/screenshot", handle_screenshot),
            web.post("/api/screenshot", handle_screenshot),
            web.post("/api/eval", handle_eval),
        ]
    )
    return app


@web.middleware
async def error_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(await manager(request).health())


async def handle_tabs(request: web.Request) -> web.Response:
    return web.json_response(await manager(request).tabs())


async def handle_session_start(request: web.Request) -> web.Response:
    data = await json_body(request)
    result = await manager(request).start_session(
        get_session_id(data),
        profile=data.get("profile"),
        headless=bool_from_value(data.get("headless"), default=True),
        humanize=bool_from_value(data.get("humanize"), default=True),
        proxy=data.get("proxy"),
        geoip=optional_bool(data.get("geoip")),
        locale=data.get("locale"),
        timezone=data.get("timezone"),
        human_preset=data.get("humanPreset") or data.get("human_preset"),
    )
    return web.json_response(session_result(result))


async def handle_session_close(request: web.Request) -> web.Response:
    data = await json_body(request)
    return web.json_response(await manager(request).close_session(get_session_id(data)))


async def handle_session_clear(request: web.Request) -> web.Response:
    data = await json_body(request)
    return web.json_response(
        await manager(request).clear_session(get_session_id(data), profile_dir=data.get("profileDir"))
    )


async def handle_navigate(request: web.Request) -> web.Response:
    data = await json_body(request)
    url = required(data, "url")
    return web.json_response(await manager(request).navigate(get_session_id(data), url))


async def handle_snapshot(request: web.Request) -> web.Response:
    data = dict(request.query)
    return web.json_response(
        await manager(request).snapshot(get_session_id(data), format=data.get("format", "text"))
    )


async def handle_click(request: web.Request) -> web.Response:
    data = await json_body(request)
    return web.json_response(
        await manager(request).click(
            get_session_id(data),
            required(data, "selector"),
            double_click=bool_from_value(data.get("doubleClick"), default=False),
        )
    )


async def handle_type(request: web.Request) -> web.Response:
    data = await json_body(request)
    return web.json_response(
        await manager(request).type_text(
            get_session_id(data),
            required(data, "selector"),
            str(required(data, "text")),
            clear=bool_from_value(data.get("clear"), default=False),
            submit=bool_from_value(data.get("submit"), default=False),
        )
    )


async def handle_scroll(request: web.Request) -> web.Response:
    data = await json_body(request)
    amount = int(data.get("amount", 600))
    return web.json_response(
        await manager(request).scroll(get_session_id(data), data.get("direction", "down"), amount)
    )


async def handle_screenshot(request: web.Request) -> web.Response:
    data = dict(request.query) if request.method == "GET" else await json_body(request)
    return web.json_response(
        await manager(request).screenshot(
            get_session_id(data),
            full_page=bool_from_value(data.get("fullPage") or data.get("full_page"), default=False),
        )
    )


async def handle_eval(request: web.Request) -> web.Response:
    data = await json_body(request)
    return web.json_response(await manager(request).evaluate(get_session_id(data), required(data, "expression")))


def manager(request: web.Request) -> Any:
    return request.app[MANAGER_KEY]


async def json_body(request: web.Request) -> dict[str, Any]:
    if not request.can_read_body:
        return {}
    data = await request.json()
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def required(data: dict[str, Any], key: str) -> Any:
    value = data.get(key)
    if value is None or value == "":
        raise ValueError(f"{key} is required")
    return value


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool_from_value(value)


def session_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, BrowserSession):
        return {
            "sessionId": result.session_id,
            "profileDir": str(result.profile_dir),
            "url": getattr(result.page, "url", "about:blank"),
        }
    return {"result": str(result)}


def default_data_dir() -> Path:
    return Path.cwd() / "data"


def default_profiles_root() -> Path:
    return default_data_dir() / "profiles"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Cloak Relay HTTP service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18796)
    parser.add_argument("--profiles-root", default=str(default_profiles_root()))
    return parser


def run(host: str = "127.0.0.1", port: int = 18796, profiles_root: str | Path | None = None) -> None:
    app = create_app(BrowserManager(profiles_root or default_profiles_root()))
    web.run_app(app, host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    run(args.host, args.port, args.profiles_root)


if __name__ == "__main__":
    main()
