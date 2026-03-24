import logging
import os
import sys

import yaml
from mcp.server.fastmcp import FastMCP, Image

from adbdevicemanager import AdbDeviceManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("android-mcp")

CONFIG_FILE = "config.yaml"
CONFIG_FILE_EXAMPLE = "config.yaml.example"

# Load config (make config file optional)
config = {}
device_name = None

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE) as f:
            config = yaml.safe_load(f.read()) or {}
        device_config = config.get("device", {})
        configured_device_name = device_config.get(
            "name") if device_config else None

        # Support multiple ways to specify auto-selection:
        # 1. name: null (None in Python)
        # 2. name: "" (empty string)
        # 3. name field completely missing
        if configured_device_name and configured_device_name.strip():
            device_name = configured_device_name.strip()
            logger.info("Loaded config from %s", CONFIG_FILE)
            logger.info("Configured device: %s", device_name)
        else:
            logger.info("Loaded config from %s", CONFIG_FILE)
            logger.info(
                "No device specified in config, will auto-select if only one device connected")
    except Exception as e:
        logger.error("Error loading config file %s: %s", CONFIG_FILE, e)
        logger.error(
            "Please check the format of your config file or recreate it from %s", CONFIG_FILE_EXAMPLE)
        sys.exit(1)
else:
    logger.info(
        "Config file %s not found, using auto-selection for device", CONFIG_FILE)

# Initialize MCP and device manager
# AdbDeviceManager will handle auto-selection if device_name is None
mcp = FastMCP("android")
deviceManager = AdbDeviceManager(device_name)


# ── Existing tools (backward compatible) ────────────────────────────


@mcp.tool()
def get_packages() -> str:
    """
    Get all installed packages on the device
    Returns:
        str: A list of all installed packages on the device as a string
    """
    result = deviceManager.get_packages()
    return result


@mcp.tool()
def execute_adb_shell_command(command: str) -> str:
    """Executes an ADB command and returns the output or an error.
    Args:
        command (str): The ADB shell command to execute
    Returns:
        str: The output of the ADB command
    """
    result = deviceManager.execute_adb_shell_command(command)
    return result


@mcp.tool()
def get_uilayout(
    clickable_only: bool = False,
    filter_text: str | None = None,
    filter_resource_id: str | None = None,
    include_hierarchy: bool = False,
) -> str:
    """
    Retrieves information about UI elements on the current screen.

    By default returns ALL elements with text or content-desc.
    Use clickable_only=True for legacy behavior (only clickable elements).
    Use filter_text or filter_resource_id to narrow results.

    Args:
        clickable_only: If True, return only clickable elements
        filter_text: Filter elements containing this text (case-insensitive)
        filter_resource_id: Filter elements with this resource-id
        include_hierarchy: If True, include element class hierarchy

    Returns:
        str: A formatted list of UI elements with their properties
    """
    result = deviceManager.get_uilayout(
        clickable_only=clickable_only,
        filter_text=filter_text,
        filter_resource_id=filter_resource_id,
        include_hierarchy=include_hierarchy,
    )
    return result


@mcp.tool()
def get_screenshot(format: str = "png", quality: int = 85) -> Image:
    """Takes a screenshot of the device and returns it.

    Args:
        format: Output format - 'png' or 'jpeg'. JPEG is smaller.
        quality: JPEG quality (1-100), ignored for PNG.

    Returns:
        Image: the screenshot
    """
    output_file = deviceManager.take_screenshot(format=format, quality=quality)
    return Image(path=output_file)


@mcp.tool()
def get_package_action_intents(package_name: str) -> list[str]:
    """
    Get all non-data actions from Activity Resolver Table for a package
    Args:
        package_name (str): The name of the package to get actions for
    Returns:
        list[str]: A list of all non-data actions from the Activity Resolver Table for the package
    """
    result = deviceManager.get_package_action_intents(package_name)
    return result


# ── Phase 2: Core interaction tools ─────────────────────────────────


@mcp.tool()
def tap_element(
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
) -> str:
    """Find a UI element on screen and tap on it.

    Searches the current UI for an element matching the given criteria,
    calculates its center point, and performs a tap.

    At least one parameter must be provided.

    Args:
        text: Element text to search for (exact match)
        resource_id: Element resource-id to search for
        content_desc: Element content-desc to search for

    Returns:
        str: Description of what was tapped and coordinates
    """
    return deviceManager.tap_element(text=text, resource_id=resource_id, content_desc=content_desc)


@mcp.tool()
def wait_for_element(
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
    timeout: int = 10,
) -> dict:
    """Wait for a UI element to appear on screen.

    Polls every 1 second until the element is found or timeout is reached.
    Much better than using sleep() — intelligently waits for the right moment.

    At least one search parameter must be provided.

    Args:
        text: Element text to search for
        resource_id: Element resource-id to search for
        content_desc: Element content-desc to search for
        timeout: Maximum seconds to wait (default 10)

    Returns:
        dict: Element info with class, text, bounds, center, clickable, scrollable
    """
    return deviceManager.wait_for_element(
        text=text, resource_id=resource_id, content_desc=content_desc, timeout=timeout
    )


@mcp.tool()
def get_screen_state() -> dict:
    """Get current device screen and battery state.

    Returns:
        dict: screen_on (bool), locked (bool), foreground_app (str),
              battery_level (int 0-100), battery_status (str)
    """
    return deviceManager.get_screen_state()


@mcp.tool()
def launch_app(package_name: str) -> str:
    """Launch an app by its package name.

    Args:
        package_name: Android package name (e.g. 'com.google.android.chrome')

    Returns:
        str: Launch confirmation
    """
    return deviceManager.launch_app(package_name)


@mcp.tool()
def kill_app(package_name: str) -> str:
    """Force-stop an app by its package name.

    Args:
        package_name: Android package name (e.g. 'com.google.android.chrome')

    Returns:
        str: Kill confirmation
    """
    return deviceManager.kill_app(package_name)


@mcp.tool()
def press_key(keycode: str) -> str:
    """Send a key event to the device.

    Supported friendly names: BACK, HOME, ENTER, RECENT, VOLUME_UP,
    VOLUME_DOWN, TAB, DELETE, ESCAPE, POWER, WAKEUP, CAMERA, SEARCH.

    Also accepts raw KEYCODE_* constants (e.g. KEYCODE_BACK).

    Args:
        keycode: Key name or KEYCODE_* constant

    Returns:
        str: Key press confirmation
    """
    return deviceManager.press_key(keycode)


@mcp.tool()
def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """Perform a swipe gesture on the screen.

    Args:
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
        duration_ms: Swipe duration in milliseconds (default 300)

    Returns:
        str: Swipe confirmation with coordinates
    """
    return deviceManager.swipe(x1, y1, x2, y2, duration_ms)


# ── Phase 3: Text and data tools ────────────────────────────────────


@mcp.tool()
def type_text(text: str) -> str:
    """Type text on the device (into the currently focused input field).

    Handles spaces and special characters. Focus an input field first
    (e.g. by tapping on it with tap_element).

    Args:
        text: Text to type

    Returns:
        str: Confirmation of typed text
    """
    return deviceManager.type_text(text)


@mcp.tool()
def get_clipboard() -> str:
    """Get the current clipboard content.

    Requires Clipper app to be installed on the device.

    Returns:
        str: Clipboard content or installation instructions
    """
    return deviceManager.get_clipboard()


@mcp.tool()
def set_clipboard(text: str) -> str:
    """Set the clipboard content.

    Requires Clipper app to be installed on the device.

    Args:
        text: Text to copy to clipboard

    Returns:
        str: Confirmation or installation instructions
    """
    return deviceManager.set_clipboard(text)


@mcp.tool()
def get_notifications() -> str:
    """Get recent notifications from the device.

    Returns the last 20 notifications with package name, title, and text.

    Returns:
        str: Formatted list of recent notifications
    """
    return deviceManager.get_notifications()


if __name__ == "__main__":
    mcp.run(transport="stdio")
