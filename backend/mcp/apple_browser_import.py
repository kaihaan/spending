"""
Apple App Store Browser Import Module

Uses Playwright to automate browser-based import from Apple's Report a Problem page.
User logs in manually, then the app captures and parses the HTML.
"""

import asyncio
import threading
import queue
import re
from typing import Optional, Any, Set


def extract_order_ids_from_html(html: str) -> Set[str]:
    """Quick extraction of order IDs from HTML without full parsing.

    Apple order IDs are 10-15 character alphanumeric strings like MM62VW915F.
    """
    # Pattern from apple_parser.py: [A-Z0-9]{10,15}
    pattern = r'([A-Z0-9]{10,15})'
    matches = re.findall(pattern, html)
    return set(matches)


class AppleBrowserSession:
    """Manages a Playwright browser session for Apple import.

    Uses a dedicated background thread with its own event loop to handle
    all Playwright operations. This ensures browser objects are always
    accessed from the same thread/event loop context.
    """

    _instance: Optional['AppleBrowserSession'] = None
    _playwright = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _command_queue: Optional[queue.Queue] = None
    _result_queue: Optional[queue.Queue] = None

    def __init__(self):
        self.browser = None
        self.page = None
        self.status = 'idle'  # idle, launching, ready, capturing, closed, error
        self.error: Optional[str] = None

    @classmethod
    def _run_browser_thread(cls):
        """Run the browser event loop in a dedicated thread."""
        cls._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls._loop)
        print(f"Browser thread started with event loop {id(cls._loop)}")

        while True:
            try:
                # Wait for commands from the main thread
                command, args = cls._command_queue.get(timeout=1.0)

                if command == 'shutdown':
                    print("Browser thread shutting down")
                    break

                if command == 'start':
                    result = cls._loop.run_until_complete(cls._async_start_session())
                elif command == 'capture':
                    result = cls._loop.run_until_complete(cls._async_capture_and_close())
                elif command == 'scroll_capture':
                    known_order_ids = args[0] if args else set()
                    result = cls._loop.run_until_complete(cls._async_scroll_and_capture(known_order_ids))
                elif command == 'cancel':
                    result = cls._loop.run_until_complete(cls._async_cancel_session())
                else:
                    result = Exception(f"Unknown command: {command}")

                cls._result_queue.put(result)

            except queue.Empty:
                # No command, continue waiting
                continue
            except Exception as e:
                print(f"Browser thread error: {e}")
                cls._result_queue.put(e)

        # Cleanup
        cls._loop.close()
        cls._loop = None
        print("Browser thread exited")

    @classmethod
    def _ensure_thread_running(cls):
        """Ensure the browser thread is running."""
        if cls._thread is None or not cls._thread.is_alive():
            cls._command_queue = queue.Queue()
            cls._result_queue = queue.Queue()
            cls._thread = threading.Thread(target=cls._run_browser_thread, daemon=True)
            cls._thread.start()
            print("Started browser thread")

    @classmethod
    def _send_command(cls, command: str, *args, timeout: float = 60.0) -> Any:
        """Send a command to the browser thread and wait for result."""
        cls._ensure_thread_running()
        cls._command_queue.put((command, args))

        try:
            result = cls._result_queue.get(timeout=timeout)
            if isinstance(result, Exception):
                raise result
            return result
        except queue.Empty:
            raise Exception(f"Browser operation timed out after {timeout}s")

    @classmethod
    async def _async_start_session(cls) -> 'AppleBrowserSession':
        """Launch browser - runs in the browser thread."""
        # Check for existing active session
        if cls._instance and cls._instance.status in ('launching', 'ready', 'capturing'):
            raise Exception('Browser session already active. Close it first or capture transactions.')

        # Create new instance
        cls._instance = cls()
        cls._instance.status = 'launching'

        try:
            from playwright.async_api import async_playwright

            # Start Playwright
            print("Starting Playwright...")
            cls._playwright = await async_playwright().start()

            # Launch visible browser (user needs to see it to log in)
            print("Launching browser...")
            cls._instance.browser = await cls._playwright.chromium.launch(
                headless=False,
                args=['--start-maximized']
            )

            # Create new page with reasonable viewport
            print("Creating page...")
            cls._instance.page = await cls._instance.browser.new_page(
                viewport={'width': 1280, 'height': 800}
            )

            # Navigate to Apple's Report a Problem page
            print("Navigating to Apple...")
            await cls._instance.page.goto('https://reportaproblem.apple.com/')

            cls._instance.status = 'ready'
            print("Browser session started successfully")
            return cls._instance

        except Exception as e:
            cls._instance.status = 'error'
            cls._instance.error = str(e)
            print(f"Error starting browser session: {e}")
            raise

    @classmethod
    async def _async_capture_and_close(cls) -> str:
        """Capture page HTML - runs in the browser thread."""
        if not cls._instance:
            raise Exception('No browser session active')

        if cls._instance.status != 'ready':
            raise Exception(f'Browser session not ready (status: {cls._instance.status})')

        try:
            cls._instance.status = 'capturing'
            print("Capturing page HTML...")

            # Get the full page HTML with timeout
            try:
                html_content = await asyncio.wait_for(
                    cls._instance.page.content(),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                raise Exception('Timeout while capturing page content (30s). Please try again.')

            print(f"Captured {len(html_content)} bytes of HTML")

            # Close browser
            print("Closing browser...")
            try:
                await asyncio.wait_for(cls._instance.browser.close(), timeout=10.0)
            except asyncio.TimeoutError:
                print("Browser close timed out, forcing cleanup")

            if cls._playwright:
                try:
                    await asyncio.wait_for(cls._playwright.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("Playwright stop timed out")
                cls._playwright = None

            cls._instance.status = 'closed'
            print("Browser closed successfully")

            return html_content

        except Exception as e:
            cls._instance.status = 'error'
            cls._instance.error = str(e)
            print(f"Error capturing page: {e}")
            # Try to cleanup even on error
            try:
                if cls._instance.browser:
                    await cls._instance.browser.close()
                if cls._playwright:
                    await cls._playwright.stop()
                    cls._playwright = None
            except:
                pass
            raise

    @classmethod
    async def _async_scroll_and_capture(cls, known_order_ids: Set[str]) -> str:
        """Scroll page to load all transactions, then capture HTML.

        Scrolls until encountering a known order_id or reaching end of content.

        Args:
            known_order_ids: Set of Apple order IDs already in database

        Returns:
            Full page HTML content
        """
        if not cls._instance:
            raise Exception('No browser session active')

        if cls._instance.status != 'ready':
            raise Exception(f'Browser session not ready (status: {cls._instance.status})')

        try:
            cls._instance.status = 'capturing'
            page = cls._instance.page
            max_scrolls = 100  # Safety limit
            scroll_count = 0

            print(f"[Apple Import] Starting auto-scroll. Known order_ids: {len(known_order_ids)}")

            while scroll_count < max_scrolls:
                # Get current scroll height
                prev_height = await page.evaluate('document.body.scrollHeight')

                # Scroll to bottom
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')

                # Wait for lazy-loaded content
                await asyncio.sleep(1.0)

                # Check if new content loaded
                new_height = await page.evaluate('document.body.scrollHeight')

                if new_height == prev_height:
                    # No new content - reached end of list
                    print(f"[Apple Import] Reached end of content after {scroll_count} scrolls")
                    break

                scroll_count += 1
                print(f"[Apple Import] Scroll {scroll_count}: page height {prev_height} -> {new_height}")

                # Check if we've reached a known transaction
                if known_order_ids:
                    html = await page.content()
                    visible_order_ids = extract_order_ids_from_html(html)
                    overlap = visible_order_ids & known_order_ids
                    if overlap:
                        print(f"[Apple Import] Found {len(overlap)} known order_id(s) - stopping scroll")
                        break

            # Capture full page HTML
            print("Capturing final page HTML...")
            try:
                html_content = await asyncio.wait_for(
                    page.content(),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                raise Exception('Timeout while capturing page content (30s).')

            print(f"Captured {len(html_content)} bytes of HTML after {scroll_count} scrolls")

            # Close browser
            print("Closing browser...")
            try:
                await asyncio.wait_for(cls._instance.browser.close(), timeout=10.0)
            except asyncio.TimeoutError:
                print("Browser close timed out, forcing cleanup")

            if cls._playwright:
                try:
                    await asyncio.wait_for(cls._playwright.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("Playwright stop timed out")
                cls._playwright = None

            cls._instance.status = 'closed'
            print("Browser closed successfully")

            return html_content

        except Exception as e:
            cls._instance.status = 'error'
            cls._instance.error = str(e)
            print(f"Error in scroll_and_capture: {e}")
            # Try to cleanup even on error
            try:
                if cls._instance.browser:
                    await cls._instance.browser.close()
                if cls._playwright:
                    await cls._playwright.stop()
                    cls._playwright = None
            except:
                pass
            raise

    @classmethod
    async def _async_cancel_session(cls) -> None:
        """Cancel session - runs in the browser thread."""
        if not cls._instance:
            return

        try:
            if cls._instance.browser:
                try:
                    await asyncio.wait_for(cls._instance.browser.close(), timeout=10.0)
                except asyncio.TimeoutError:
                    print("Browser close timed out during cancel")
            if cls._playwright:
                try:
                    await asyncio.wait_for(cls._playwright.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("Playwright stop timed out during cancel")
                cls._playwright = None
        except Exception as e:
            print(f"Error closing browser: {e}")
        finally:
            cls._instance.status = 'closed'
            cls._instance = None

    @classmethod
    def start_session(cls) -> 'AppleBrowserSession':
        """Start a browser session (called from Flask routes)."""
        return cls._send_command('start', timeout=60.0)

    @classmethod
    def capture_and_close(cls) -> str:
        """Capture HTML and close browser (called from Flask routes)."""
        return cls._send_command('capture', timeout=60.0)

    @classmethod
    def scroll_and_capture(cls, known_order_ids: Set[str] = None) -> str:
        """Scroll page to load all transactions, then capture HTML.

        Args:
            known_order_ids: Set of Apple order IDs already in database.
                           Scrolling stops when a known order_id is found.

        Returns:
            Full page HTML content
        """
        if known_order_ids is None:
            known_order_ids = set()
        # Longer timeout for scrolling - could take a while for long history
        return cls._send_command('scroll_capture', known_order_ids, timeout=300.0)

    @classmethod
    def cancel_session(cls) -> None:
        """Cancel the session (called from Flask routes)."""
        cls._send_command('cancel', timeout=30.0)

    @classmethod
    def get_status(cls) -> dict:
        """Get current session status.

        Returns:
            Dictionary with status and error (if any)
        """
        if not cls._instance:
            return {'status': 'idle', 'error': None}

        return {
            'status': cls._instance.status,
            'error': cls._instance.error
        }

    @classmethod
    def is_active(cls) -> bool:
        """Check if there's an active browser session."""
        return cls._instance is not None and cls._instance.status in ('launching', 'ready', 'capturing')
