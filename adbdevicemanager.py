import logging
import os
import re
import subprocess
import sys
import time

from PIL import Image as PILImage
from ppadb.client import Client as AdbClient

from exceptions import (
    ADBCommandError,
    ADBError,
    ADBTimeoutError,
    DeviceNotFoundError,
    ElementNotFoundError,
)
from retry import retry
from xml_utils import (
    calculate_center,
    dump_and_pull,
    element_to_dict,
    find_element,
)

logger = logging.getLogger(__name__)

# Friendly key name -> KEYCODE mapping
KEY_MAP = {
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "ENTER": "KEYCODE_ENTER",
    "RECENT": "KEYCODE_APP_SWITCH",
    "VOLUME_UP": "KEYCODE_VOLUME_UP",
    "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN",
    "TAB": "KEYCODE_TAB",
    "DELETE": "KEYCODE_DEL",
    "ESCAPE": "KEYCODE_ESCAPE",
    "POWER": "KEYCODE_POWER",
    "WAKEUP": "KEYCODE_WAKEUP",
    "CAMERA": "KEYCODE_CAMERA",
    "SEARCH": "KEYCODE_SEARCH",
}


class AdbDeviceManager:
    def __init__(self, device_name: str | None = None, exit_on_error: bool = True) -> None:
        """
        Initialize the ADB Device Manager

        Args:
            device_name: Optional name/serial of the device to manage.
                         If None, attempts to auto-select if only one device is available.
            exit_on_error: Whether to exit the program if device initialization fails
        """
        if not self.check_adb_installed():
            error_msg = "adb is not installed or not in PATH. Please install adb and ensure it is in your PATH."
            if exit_on_error:
                logger.error(error_msg)
                sys.exit(1)
            else:
                raise DeviceNotFoundError(error_msg)

        available_devices = self.get_available_devices()
        if not available_devices:
            error_msg = "No devices connected. Please connect a device and try again."
            if exit_on_error:
                logger.error(error_msg)
                sys.exit(1)
            else:
                raise DeviceNotFoundError(error_msg)

        selected_device_name: str | None = None

        if device_name:
            if device_name not in available_devices:
                error_msg = f"Device {device_name} not found. Available devices: {available_devices}"
                if exit_on_error:
                    logger.error(error_msg)
                    sys.exit(1)
                else:
                    raise DeviceNotFoundError(error_msg)
            selected_device_name = device_name
        else:  # No device_name provided, try auto-selection
            if len(available_devices) == 1:
                selected_device_name = available_devices[0]
                logger.info("No device specified, automatically selected: %s", selected_device_name)
            elif len(available_devices) > 1:
                error_msg = f"Multiple devices connected: {available_devices}. Please specify a device in config.yaml or connect only one device."
                if exit_on_error:
                    logger.error(error_msg)
                    sys.exit(1)
                else:
                    raise DeviceNotFoundError(error_msg)

        # Initialize the device
        self.device = AdbClient().device(selected_device_name)

        # Disable animations for reliable UI automation
        self._disable_animations()

    def _disable_animations(self) -> None:
        """Disable all animations on the device for reliable UI automation."""
        try:
            for setting in [
                "window_animation_scale",
                "transition_animation_scale",
                "animator_duration_scale",
            ]:
                self._shell(f"settings put global {setting} 0")
            logger.info("Animations disabled on device")
        except Exception as e:
            logger.warning("Failed to disable animations: %s", e)

    @retry(max_attempts=3, base_delay=0.5, exceptions=(Exception,))
    def _shell(self, command: str) -> str:
        """Execute ADB shell command with retry logic.

        Args:
            command: Shell command to execute

        Returns:
            Command output as string
        """
        result = self.device.shell(command)
        return result if result else ""

    def _ensure_screen_awake(self) -> None:
        """Check if screen is awake, send WAKEUP if asleep."""
        try:
            output = self._shell("dumpsys power")
            if "mWakefulness=Asleep" in output or "mWakefulness=Dozing" in output:
                self._shell("input keyevent KEYCODE_WAKEUP")
                time.sleep(0.5)
                logger.info("Screen was asleep, sent WAKEUP")
        except Exception as e:
            logger.warning("Failed to check/wake screen: %s", e)

    @staticmethod
    def check_adb_installed() -> bool:
        """Check if ADB is installed on the system."""
        try:
            subprocess.run(["adb", "version"], check=True,
                           stdout=subprocess.PIPE)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def get_available_devices() -> list[str]:
        """Get a list of available devices."""
        return [device.serial for device in AdbClient().devices()]

    # ── Existing tools ──────────────────────────────────────────────

    def get_packages(self) -> str:
        command = "pm list packages"
        packages = self._shell(command).strip().split("\n")
        result = [package[8:] for package in packages if package.startswith("package:")]
        output = "\n".join(result)
        return output

    def get_package_action_intents(self, package_name: str) -> list[str]:
        command = f"dumpsys package {package_name}"
        output = self._shell(command)

        resolver_table_start = output.find("Activity Resolver Table:")
        if resolver_table_start == -1:
            return []
        resolver_section = output[resolver_table_start:]

        non_data_start = resolver_section.find("\n  Non-Data Actions:")
        if non_data_start == -1:
            return []

        section_end = resolver_section[non_data_start:].find("\n\n")
        if section_end == -1:
            non_data_section = resolver_section[non_data_start:]
        else:
            non_data_section = resolver_section[
                non_data_start: non_data_start + section_end
            ]

        actions = []
        for line in non_data_section.split("\n"):
            line = line.strip()
            if line.startswith("android.") or line.startswith("com."):
                actions.append(line)

        return actions

    def execute_adb_shell_command(self, command: str) -> str:
        """Executes an ADB command and returns the output."""
        if command.startswith("adb shell "):
            command = command[10:]
        elif command.startswith("adb "):
            command = command[4:]
        result = self._shell(command)
        return result

    def take_screenshot(self, format: str = "png", quality: int = 85) -> str:
        """Take a screenshot, resize, and save.

        Args:
            format: Output format - 'png' or 'jpeg'
            quality: JPEG quality (1-100), ignored for PNG

        Returns:
            Path to the saved screenshot file
        """
        self._shell("screencap -p /sdcard/screenshot.png")
        self.device.pull("/sdcard/screenshot.png", "screenshot.png")
        self._shell("rm /sdcard/screenshot.png")

        output_format = format.upper()
        if output_format == "JPEG":
            output_format = "JPEG"
            output_file = "compressed_screenshot.jpg"
        else:
            output_format = "PNG"
            output_file = "compressed_screenshot.png"

        with PILImage.open("screenshot.png") as img:
            # Strip EXIF metadata by copying pixel data only
            clean_img = PILImage.new(img.mode, img.size)
            clean_img.putdata(list(img.getdata()))

            width, height = clean_img.size
            max_dim = 1600
            if max(width, height) > max_dim:
                scale = max_dim / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
            else:
                new_width = width
                new_height = height

            resized_img = clean_img.resize(
                (new_width, new_height), PILImage.Resampling.LANCZOS
            )

            if output_format == "JPEG":
                resized_img.save(output_file, "JPEG", quality=quality, optimize=True)
            else:
                resized_img.save(output_file, "PNG", optimize=True)

        # Clean up temp file
        if os.path.exists("screenshot.png"):
            os.remove("screenshot.png")

        return output_file

    def get_uilayout(
        self,
        clickable_only: bool = False,
        filter_text: str | None = None,
        filter_resource_id: str | None = None,
        include_hierarchy: bool = False,
    ) -> str:
        """Get UI layout information.

        Args:
            clickable_only: If True, return only clickable elements (legacy behavior)
            filter_text: Filter elements containing this text
            filter_resource_id: Filter elements with this resource-id
            include_hierarchy: If True, include parent class hierarchy info

        Returns:
            Formatted string of UI elements
        """
        self._ensure_screen_awake()
        root = dump_and_pull(self.device)

        elements = []
        for node in root.iter("node"):
            text = node.get("text", "")
            content_desc = node.get("content-desc", "")
            resource_id = node.get("resource-id", "")
            clickable = node.get("clickable", "false") == "true"
            scrollable = node.get("scrollable", "false") == "true"
            bounds = node.get("bounds", "")
            cls = node.get("class", "")

            # Filter: clickable_only
            if clickable_only and not clickable:
                continue

            # Default: only elements with text or content-desc
            if not clickable_only and not text and not content_desc:
                continue

            # Filter by text
            if filter_text and filter_text.lower() not in text.lower() and filter_text.lower() not in content_desc.lower():
                continue

            # Filter by resource-id
            if filter_resource_id and filter_resource_id not in resource_id:
                continue

            center = calculate_center(bounds)
            info = ""
            if clickable:
                info += "Clickable element:"
            else:
                info += "Element:"

            info += f"\n  Class: {cls}"
            if text:
                info += f"\n  Text: {text}"
            if content_desc:
                info += f"\n  Description: {content_desc}"
            if resource_id:
                info += f"\n  Resource ID: {resource_id}"
            info += f"\n  Bounds: {bounds}"
            if center:
                info += f"\n  Center: ({center[0]}, {center[1]})"
            info += f"\n  Clickable: {clickable}"
            info += f"\n  Scrollable: {scrollable}"

            if include_hierarchy:
                # Build parent path
                parent = node
                path_parts = []
                # Walk up to find parent classes (limited by XML structure)
                path_parts.append(cls)
                info += f"\n  Hierarchy: {' > '.join(path_parts)}"

            elements.append(info)

        if not elements:
            return "No elements found matching criteria"
        return "\n\n".join(elements)

    # ── Phase 2: Core interaction tools ─────────────────────────────

    def tap_element(
        self,
        text: str | None = None,
        resource_id: str | None = None,
        content_desc: str | None = None,
    ) -> str:
        """Find a UI element and tap on its center.

        Args:
            text: Element text to search for
            resource_id: Element resource-id to search for
            content_desc: Element content-desc to search for

        Returns:
            Description of what was tapped

        Raises:
            ElementNotFoundError: If no matching element is found
            ValueError: If no search parameter provided
        """
        if not any([text, resource_id, content_desc]):
            raise ValueError("At least one of text, resource_id, or content_desc must be provided")

        self._ensure_screen_awake()
        root = dump_and_pull(self.device)
        element = find_element(root, text=text, resource_id=resource_id, content_desc=content_desc)

        if element is None:
            criteria = []
            if text:
                criteria.append(f"text='{text}'")
            if resource_id:
                criteria.append(f"resource_id='{resource_id}'")
            if content_desc:
                criteria.append(f"content_desc='{content_desc}'")
            raise ElementNotFoundError(f"Element not found: {', '.join(criteria)}")

        bounds = element.get("bounds", "")
        center = calculate_center(bounds)
        if not center:
            raise ElementNotFoundError(f"Could not calculate center for element bounds: {bounds}")

        self._shell(f"input tap {center[0]} {center[1]}")

        elem_text = element.get("text", "") or element.get("content-desc", "") or element.get("resource-id", "")
        logger.info("Tapped element '%s' at (%d, %d)", elem_text, center[0], center[1])
        return f"Tapped '{elem_text}' at ({center[0]}, {center[1]})"

    def wait_for_element(
        self,
        text: str | None = None,
        resource_id: str | None = None,
        content_desc: str | None = None,
        timeout: int = 10,
    ) -> dict:
        """Wait for a UI element to appear on screen.

        Args:
            text: Element text to search for
            resource_id: Element resource-id to search for
            content_desc: Element content-desc to search for
            timeout: Maximum seconds to wait

        Returns:
            Dict with element info (class, text, bounds, center, etc.)

        Raises:
            ElementNotFoundError: If element not found within timeout
            ValueError: If no search parameter provided
        """
        if not any([text, resource_id, content_desc]):
            raise ValueError("At least one of text, resource_id, or content_desc must be provided")

        self._ensure_screen_awake()
        start = time.time()

        while time.time() - start < timeout:
            try:
                root = dump_and_pull(self.device)
                element = find_element(root, text=text, resource_id=resource_id, content_desc=content_desc)
                if element is not None:
                    return element_to_dict(element)
            except Exception as e:
                logger.debug("Error during wait_for_element poll: %s", e)
            time.sleep(1)

        criteria = []
        if text:
            criteria.append(f"text='{text}'")
        if resource_id:
            criteria.append(f"resource_id='{resource_id}'")
        if content_desc:
            criteria.append(f"content_desc='{content_desc}'")
        raise ElementNotFoundError(
            f"Element not found within {timeout}s: {', '.join(criteria)}"
        )

    def get_screen_state(self) -> dict:
        """Get current screen and device state.

        Returns:
            Dict with: screen_on, locked, foreground_app, battery_level, battery_status
        """
        result = {
            "screen_on": False,
            "locked": False,
            "foreground_app": "",
            "battery_level": -1,
            "battery_status": "",
        }

        # Screen state
        try:
            power_output = self._shell("dumpsys power")
            result["screen_on"] = "mWakefulness=Awake" in power_output
        except Exception as e:
            logger.warning("Failed to get power state: %s", e)

        # Lock state
        try:
            keyguard_output = self._shell("dumpsys window")
            # mDreamingLockscreen or isShown for keyguard
            result["locked"] = "mShowingLockscreen=true" in keyguard_output or "mDreamingLockscreen=true" in keyguard_output
        except Exception as e:
            logger.warning("Failed to get lock state: %s", e)

        # Foreground app
        try:
            window_output = self._shell("dumpsys window")
            # Try mCurrentFocus first
            match = re.search(r"mCurrentFocus=Window\{[^}]+ ([^\s/}]+)", window_output)
            if match:
                result["foreground_app"] = match.group(1)
            else:
                # Try mFocusedApp
                match = re.search(r"mFocusedApp=.*?([a-zA-Z][a-zA-Z0-9_.]+/[a-zA-Z][a-zA-Z0-9_.]+)", window_output)
                if match:
                    result["foreground_app"] = match.group(1)
        except Exception as e:
            logger.warning("Failed to get foreground app: %s", e)

        # Battery
        try:
            battery_output = self._shell("dumpsys battery")
            level_match = re.search(r"level:\s*(\d+)", battery_output)
            if level_match:
                result["battery_level"] = int(level_match.group(1))
            status_match = re.search(r"status:\s*(\d+)", battery_output)
            if status_match:
                status_code = int(status_match.group(1))
                status_map = {1: "unknown", 2: "charging", 3: "discharging", 4: "not_charging", 5: "full"}
                result["battery_status"] = status_map.get(status_code, f"unknown({status_code})")
        except Exception as e:
            logger.warning("Failed to get battery state: %s", e)

        return result

    def launch_app(self, package_name: str) -> str:
        """Launch an app by package name.

        Args:
            package_name: Android package name (e.g. 'com.google.android.chrome')

        Returns:
            Launch result message
        """
        self._ensure_screen_awake()
        output = self._shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        if "No activities found" in output:
            raise ADBCommandError(f"No launchable activity found for package: {package_name}")
        logger.info("Launched app: %s", package_name)
        return f"Launched {package_name}"

    def kill_app(self, package_name: str) -> str:
        """Force-stop an app by package name.

        Args:
            package_name: Android package name

        Returns:
            Kill result message
        """
        self._shell(f"am force-stop {package_name}")
        logger.info("Killed app: %s", package_name)
        return f"Force-stopped {package_name}"

    def press_key(self, keycode: str) -> str:
        """Send a key event to the device.

        Args:
            keycode: Friendly key name (BACK, HOME, ENTER, RECENT, VOLUME_UP,
                     VOLUME_DOWN, TAB, DELETE, ESCAPE, POWER, WAKEUP, CAMERA, SEARCH)
                     or a raw KEYCODE_* constant

        Returns:
            Key press result message
        """
        key_upper = keycode.upper()
        resolved = KEY_MAP.get(key_upper, None)
        if resolved is None:
            # Allow raw KEYCODE_* values
            if key_upper.startswith("KEYCODE_"):
                resolved = key_upper
            else:
                available = ", ".join(sorted(KEY_MAP.keys()))
                raise ValueError(f"Unknown key '{keycode}'. Available keys: {available}")

        self._shell(f"input keyevent {resolved}")
        logger.info("Pressed key: %s (%s)", keycode, resolved)
        return f"Pressed {keycode}"

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
        """Perform a swipe gesture.

        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds

        Returns:
            Swipe result message
        """
        self._ensure_screen_awake()
        self._shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
        logger.info("Swiped from (%d,%d) to (%d,%d) in %dms", x1, y1, x2, y2, duration_ms)
        return f"Swiped from ({x1},{y1}) to ({x2},{y2}) in {duration_ms}ms"

    # ── Phase 3: Text and data tools ────────────────────────────────

    def type_text(self, text: str) -> str:
        """Type text on the device.

        Handles spaces (replaced with %s) and escapes special shell characters.

        Args:
            text: Text to type

        Returns:
            Confirmation message
        """
        self._ensure_screen_awake()
        # Replace spaces with %s for ADB input text
        escaped = text.replace(" ", "%s")
        # Escape shell special characters
        for char in ["'", '"', "\\", "(", ")", "&", "|", ";", "<", ">", "`", "$", "!", "~"]:
            escaped = escaped.replace(char, f"\\{char}")

        self._shell(f'input text "{escaped}"')
        logger.info("Typed text: %s", text[:50])
        return f"Typed: {text}"

    def get_clipboard(self) -> str:
        """Get clipboard content using Clipper app.

        Returns:
            Clipboard content or instructions to install Clipper
        """
        try:
            output = self._shell("am broadcast -a clipper.get")
            if "result=0" in output or "Broadcast completed" in output:
                # Extract data from broadcast result
                match = re.search(r"data=\"(.*)\"", output)
                if match:
                    return match.group(1)
                return output.strip()
            return "Clipboard access requires Clipper app. Install from: https://github.com/nicnacnic/Clipper"
        except Exception as e:
            return f"Clipboard access failed: {e}. Install Clipper app for clipboard support."

    def set_clipboard(self, text: str) -> str:
        """Set clipboard content using Clipper app.

        Args:
            text: Text to set in clipboard

        Returns:
            Confirmation or instructions to install Clipper
        """
        try:
            escaped = text.replace('"', '\\"')
            output = self._shell(f'am broadcast -a clipper.set -e text "{escaped}"')
            if "result=0" in output or "Broadcast completed" in output:
                logger.info("Clipboard set: %s", text[:50])
                return f"Clipboard set to: {text}"
            return "Clipboard access requires Clipper app. Install from: https://github.com/nicnacnic/Clipper"
        except Exception as e:
            return f"Clipboard access failed: {e}. Install Clipper app for clipboard support."

    def get_notifications(self) -> str:
        """Get recent notifications from the device.

        Returns:
            Formatted string of last 20 notifications
        """
        output = self._shell("dumpsys notification --noredact")

        notifications = []
        # Parse notification entries
        current = {}
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("pkg="):
                if current:
                    notifications.append(current)
                current = {"package": line.split("=", 1)[1]}
            elif "android.title=" in line:
                match = re.search(r"android\.title=(.*?)(?:\s+android\.|$)", line)
                if match:
                    current["title"] = match.group(1).strip()
            elif "android.text=" in line:
                match = re.search(r"android\.text=(.*?)(?:\s+android\.|$)", line)
                if match:
                    current["text"] = match.group(1).strip()
            elif line.startswith("tickerText=") and line != "tickerText=null":
                current["ticker"] = line.split("=", 1)[1]

        if current:
            notifications.append(current)

        # Return last 20
        notifications = notifications[-20:]

        if not notifications:
            return "No notifications found"

        result = []
        for i, notif in enumerate(notifications, 1):
            entry = f"[{i}] {notif.get('package', 'unknown')}"
            if "title" in notif:
                entry += f"\n    Title: {notif['title']}"
            if "text" in notif:
                entry += f"\n    Text: {notif['text']}"
            if "ticker" in notif:
                entry += f"\n    Ticker: {notif['ticker']}"
            result.append(entry)

        return "\n\n".join(result)
