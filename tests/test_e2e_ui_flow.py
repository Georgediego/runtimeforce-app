"""
End-to-End (E2E) Integration Tests for RuntimeForce IDE Client (runtimeforce-app)
using Playwright and FastAPI Test Server.
"""
import pytest
import asyncio
import threading
import uvicorn
import socket
from playwright.async_api import async_playwright
from app.main import app

def get_free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def test_server_port():
    port = get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    
    import time
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
            
    yield port
    server.should_exit = True
    thread.join(timeout=2.0)

@pytest.mark.asyncio
async def test_e2e_ide_ui_flow(test_server_port):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        base_url = f"http://127.0.0.1:{test_server_port}"
        
        # 1. Load main page & verify title and version badge
        await page.goto(base_url)
        await page.wait_for_selector("header")
        
        title = await page.title()
        assert "RuntimeForce" in title

        # Verify version badge in header
        version_badge = page.locator("header span.font-mono")
        assert await version_badge.is_visible()

        # Dismiss or sync auth overlay if present
        auth_overlay = page.locator("#rf-auth-overlay")
        if await auth_overlay.is_visible():
            sync_btn = page.locator("#rf-auth-sync-btn")
            if await sync_btn.is_visible():
                await sync_btn.click()
            # Also ensure overlay is hidden via evaluate if needed
            await page.evaluate("document.getElementById('rf-auth-overlay').style.display = 'none';")

        # 2. Test chat prompt input & send button interaction
        prompt_input = page.locator("#prompt-input")
        await prompt_input.fill("Hello RuntimeForce, E2E test prompt")
        
        send_btn = page.locator("#send-btn")
        await send_btn.click()
        
        chat_history = page.locator("#chat-history")
        await chat_history.wait_for()

        await browser.close()
