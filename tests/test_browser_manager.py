from pathlib import Path

import pytest

from cloak_relay.browser_manager import BrowserManager


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.actions.append(("press", key))


class FakeMouse:
    def __init__(self, page):
        self.page = page

    async def wheel(self, dx, dy):
        self.page.actions.append(("wheel", dx, dy))


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    async def click(self, click_count=1):
        self.page.actions.append(("click", self.selector, click_count))

    async def fill(self, text):
        self.page.actions.append(("fill", self.selector, text))

    async def type(self, text):
        self.page.actions.append(("type", self.selector, text))


class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.actions = []
        self.keyboard = FakeKeyboard(self)
        self.mouse = FakeMouse(self)

    async def goto(self, url, wait_until="domcontentloaded", timeout=60000):
        self.url = url
        self.actions.append(("goto", url, wait_until, timeout))

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def evaluate(self, expression):
        self.actions.append(("evaluate", expression))
        if "document.body.innerText" in expression:
            return "Example text"
        if "document.documentElement.outerHTML" in expression:
            return "<html></html>"
        return {"ok": True}

    async def screenshot(self, full_page=False):
        self.actions.append(("screenshot", full_page))
        return b"png"


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.closed = False

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


async def fake_launcher(profile_dir, **kwargs):
    context = FakeContext()
    context.profile_dir = Path(profile_dir)
    context.launch_kwargs = kwargs
    return context


@pytest.mark.asyncio
async def test_start_session_uses_profile_under_profiles_root(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    session = await manager.start_session("alpha")
    assert session.profile_dir == tmp_path / "alpha"
    assert session.context.pages[0].url == "about:blank"
    assert session.context.launch_kwargs["humanize"] is True
    assert session.context.launch_kwargs["headless"] is True


@pytest.mark.asyncio
async def test_start_session_can_open_headed_for_human_handoff(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    session = await manager.start_session("alpha", headless=False)
    assert session.context.launch_kwargs["headless"] is False


@pytest.mark.asyncio
async def test_navigate_reuses_started_session_page(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    await manager.start_session("alpha")
    result = await manager.navigate("alpha", "https://example.com")
    assert result == {"sessionId": "alpha", "url": "https://example.com"}
    assert manager.sessions["alpha"].page.actions[-1][0] == "goto"


@pytest.mark.asyncio
async def test_clear_session_deletes_only_safe_profile(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    session = await manager.start_session("alpha")
    marker = session.profile_dir / "cookie"
    marker.write_text("state", encoding="utf-8")
    result = await manager.clear_session("alpha")
    assert result["cleared"] is True
    assert not session.profile_dir.exists()


@pytest.mark.asyncio
async def test_clear_session_rejects_profile_outside_root(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    with pytest.raises(ValueError):
        await manager.clear_session("bad", profile_dir=tmp_path.parent)


@pytest.mark.asyncio
async def test_click_type_scroll_use_page_level_actions(tmp_path):
    manager = BrowserManager(tmp_path, launcher=fake_launcher)
    await manager.start_session("alpha")
    await manager.click("alpha", "#go", double_click=True)
    await manager.type_text("alpha", "#q", "hello", clear=True, submit=True)
    await manager.scroll("alpha", "down", 300)
    actions = manager.sessions["alpha"].page.actions
    assert ("click", "#go", 2) in actions
    assert ("fill", "#q", "") in actions
    assert ("type", "#q", "hello") in actions
    assert ("press", "Enter") in actions
    assert ("wheel", 0, 300) in actions
