from __future__ import annotations

import base64
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable


Launcher = Callable[..., Awaitable[Any]]


@dataclass
class BrowserSession:
    session_id: str
    profile_dir: Path
    context: Any
    page: Any


async def default_cloak_launcher(profile_dir: str | Path, **kwargs: Any) -> Any:
    from cloakbrowser import launch_persistent_context_async

    return await launch_persistent_context_async(str(profile_dir), **kwargs)


class BrowserManager:
    def __init__(
        self,
        profiles_root: str | Path,
        *,
        launcher: Launcher | None = None,
    ) -> None:
        self.profiles_root = Path(profiles_root).resolve()
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self.launcher = launcher or default_cloak_launcher
        self.sessions: dict[str, BrowserSession] = {}

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "sessions": sorted(self.sessions)}

    async def tabs(self) -> dict[str, Any]:
        tabs = []
        for session in self.sessions.values():
            tabs.append(
                {
                    "sessionId": session.session_id,
                    "url": getattr(session.page, "url", "about:blank"),
                    "profileDir": str(session.profile_dir),
                }
            )
        return {"tabs": tabs}

    async def start_session(
        self,
        session_id: str = "default",
        *,
        profile: str | Path | None = None,
        headless: bool = True,
        humanize: bool = True,
        proxy: str | None = None,
        geoip: bool | None = None,
        locale: str | None = None,
        timezone: str | None = None,
        human_preset: str | None = None,
    ) -> BrowserSession:
        if session_id in self.sessions:
            return self.sessions[session_id]

        profile_dir = self.profile_dir_for(session_id, profile=profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        launch_kwargs: dict[str, Any] = {
            "headless": headless,
            "humanize": humanize,
        }
        if proxy:
            launch_kwargs["proxy"] = proxy
        if geoip is not None:
            launch_kwargs["geoip"] = geoip
        if locale:
            launch_kwargs["locale"] = locale
        if timezone:
            launch_kwargs["timezone_id"] = timezone
        if human_preset:
            launch_kwargs["human_preset"] = human_preset

        context = await self.launcher(profile_dir, **launch_kwargs)
        page = await self._first_page(context)
        session = BrowserSession(session_id, profile_dir, context, page)
        self.sessions[session_id] = session
        return session

    async def close_session(self, session_id: str = "default") -> dict[str, Any]:
        session = self.sessions.pop(session_id, None)
        if not session:
            return {"sessionId": session_id, "closed": False}
        close = getattr(session.context, "close", None)
        if close:
            await close()
        return {"sessionId": session_id, "closed": True}

    async def clear_session(
        self,
        session_id: str = "default",
        *,
        profile_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        target = Path(profile_dir).resolve() if profile_dir else self.profile_dir_for(session_id)
        self._assert_safe_profile_dir(target)
        await self.close_session(session_id)
        if target.exists():
            shutil.rmtree(target)
        return {"sessionId": session_id, "cleared": True, "profileDir": str(target)}

    async def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        await session.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return {"sessionId": session_id, "url": getattr(session.page, "url", url)}

    async def snapshot(self, session_id: str, *, format: str = "text") -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        if format == "html":
            content = await session.page.evaluate("() => document.documentElement.outerHTML")
        else:
            content = await session.page.evaluate("() => document.body ? document.body.innerText : ''")
        return {"sessionId": session_id, "format": format, "content": content}

    async def click(
        self,
        session_id: str,
        selector: str,
        *,
        double_click: bool = False,
    ) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        await session.page.locator(selector).click(click_count=2 if double_click else 1)
        return {"sessionId": session_id, "selector": selector, "clicked": True}

    async def type_text(
        self,
        session_id: str,
        selector: str,
        text: str,
        *,
        clear: bool = False,
        submit: bool = False,
    ) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        locator = session.page.locator(selector)
        if clear:
            await locator.fill("")
        await locator.type(text)
        if submit:
            await session.page.keyboard.press("Enter")
        return {"sessionId": session_id, "selector": selector, "typed": True}

    async def scroll(
        self,
        session_id: str,
        direction: str = "down",
        amount: int = 600,
    ) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        sign = -1 if direction in {"up", "left"} else 1
        if direction in {"left", "right"}:
            await session.page.mouse.wheel(sign * abs(amount), 0)
        else:
            await session.page.mouse.wheel(0, sign * abs(amount))
        return {"sessionId": session_id, "direction": direction, "amount": amount, "scrolled": True}

    async def screenshot(self, session_id: str, *, full_page: bool = False) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        data = await session.page.screenshot(full_page=full_page)
        return {
            "sessionId": session_id,
            "mimeType": "image/png",
            "data": base64.b64encode(data).decode("ascii"),
        }

    async def evaluate(self, session_id: str, expression: str) -> dict[str, Any]:
        session = await self.ensure_session(session_id)
        result = await session.page.evaluate(expression)
        return {"sessionId": session_id, "result": result}

    async def ensure_session(self, session_id: str = "default") -> BrowserSession:
        if session_id not in self.sessions:
            return await self.start_session(session_id)
        return self.sessions[session_id]

    def profile_dir_for(self, session_id: str, *, profile: str | Path | None = None) -> Path:
        if profile:
            raw = Path(profile)
            target = raw if raw.is_absolute() else self.profiles_root / raw
        else:
            target = self.profiles_root / session_id
        target = target.resolve()
        self._assert_safe_profile_dir(target)
        return target

    def _assert_safe_profile_dir(self, target: Path) -> None:
        root = self.profiles_root.resolve()
        resolved = target.resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError(f"profile path must be inside profiles root: {resolved}")

    async def _first_page(self, context: Any) -> Any:
        pages = getattr(context, "pages", [])
        if pages:
            return pages[0]
        new_page = getattr(context, "new_page")
        return await new_page()
