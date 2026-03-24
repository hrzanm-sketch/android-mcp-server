"""Tests for all new tools added in the upgrade."""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch, call

import pytest

from adbdevicemanager import AdbDeviceManager, KEY_MAP
from exceptions import (
    ADBCommandError,
    DeviceNotFoundError,
    ElementNotFoundError,
)

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_UI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        content-desc="" clickable="false" scrollable="false"
        bounds="[0,0][1080,2400]">
    <node index="0" text="OK" resource-id="android:id/button1"
          class="android.widget.Button" content-desc=""
          clickable="true" scrollable="false"
          bounds="[200,1000][880,1100]">
    </node>
    <node index="1" text="Cancel" resource-id="android:id/button2"
          class="android.widget.Button" content-desc=""
          clickable="true" scrollable="false"
          bounds="[200,1200][880,1300]">
    </node>
    <node index="2" text="" resource-id="com.app:id/logo"
          class="android.widget.ImageView" content-desc="App Logo"
          clickable="false" scrollable="false"
          bounds="[400,200][680,400]">
    </node>
  </node>
</hierarchy>
"""


def _create_mock_manager():
    """Create a mocked AdbDeviceManager for testing methods."""
    with patch('adbdevicemanager.AdbDeviceManager.check_adb_installed', return_value=True), \
         patch('adbdevicemanager.AdbDeviceManager.get_available_devices', return_value=["test_device"]), \
         patch('adbdevicemanager.AdbClient') as mock_client, \
         patch('adbdevicemanager.AdbDeviceManager._disable_animations'):
        mock_device = MagicMock()
        mock_client.return_value.device.return_value = mock_device
        manager = AdbDeviceManager(device_name=None, exit_on_error=False)
    return manager, mock_device


class TestTapElement:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_tap_by_text(self):
        """Test tapping element by text."""
        # Mock _ensure_screen_awake and dump_and_pull
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.tap_element(text="OK")

        assert "OK" in result
        assert "540" in result  # center x of [200,1000][880,1100]
        assert "1050" in result  # center y
        self.mock_device.shell.assert_called()

    def test_tap_by_resource_id(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.tap_element(resource_id="android:id/button2")

        assert "Cancel" in result

    def test_tap_by_content_desc(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.tap_element(content_desc="App Logo")

        assert "App Logo" in result

    def test_tap_element_not_found(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            with pytest.raises(ElementNotFoundError):
                self.manager.tap_element(text="Nonexistent")

    def test_tap_no_params_raises(self):
        with pytest.raises(ValueError):
            self.manager.tap_element()


class TestWaitForElement:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_wait_found_immediately(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.wait_for_element(text="OK", timeout=5)

        assert result["text"] == "OK"
        assert result["clickable"] is True
        assert result["center"] == (540, 1050)

    def test_wait_timeout(self):
        self.manager._ensure_screen_awake = MagicMock()
        empty_root = ET.fromstring('<hierarchy rotation="0"></hierarchy>')

        with patch('adbdevicemanager.dump_and_pull', return_value=empty_root), \
             patch('adbdevicemanager.time.sleep'):
            with pytest.raises(ElementNotFoundError, match="not found within 2s"):
                self.manager.wait_for_element(text="Missing", timeout=2)

    def test_wait_no_params_raises(self):
        with pytest.raises(ValueError):
            self.manager.wait_for_element()


class TestGetScreenState:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_screen_awake_unlocked(self):
        def shell_side_effect(cmd):
            if "dumpsys power" in cmd:
                return "mWakefulness=Awake\nmStayOn=false"
            elif "dumpsys window" in cmd:
                return "mShowingLockscreen=false\nmCurrentFocus=Window{abc com.google.chrome/org.chromium.chrome.browser.ChromeTabbedActivity}"
            elif "dumpsys battery" in cmd:
                return "level: 85\nstatus: 2"
            return ""

        self.mock_device.shell.side_effect = shell_side_effect

        result = self.manager.get_screen_state()

        assert result["screen_on"] is True
        assert result["locked"] is False
        assert "com.google.chrome" in result["foreground_app"]
        assert result["battery_level"] == 85
        assert result["battery_status"] == "charging"

    def test_screen_asleep_locked(self):
        def shell_side_effect(cmd):
            if "dumpsys power" in cmd:
                return "mWakefulness=Asleep"
            elif "dumpsys window" in cmd:
                return "mShowingLockscreen=true"
            elif "dumpsys battery" in cmd:
                return "level: 42\nstatus: 3"
            return ""

        self.mock_device.shell.side_effect = shell_side_effect

        result = self.manager.get_screen_state()

        assert result["screen_on"] is False
        assert result["locked"] is True
        assert result["battery_level"] == 42
        assert result["battery_status"] == "discharging"


class TestLaunchApp:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_launch_success(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = "Events injected: 1"

        result = self.manager.launch_app("com.google.android.chrome")

        assert "Launched" in result
        assert "com.google.android.chrome" in result

    def test_launch_not_found(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = "No activities found to run"

        with pytest.raises(ADBCommandError):
            self.manager.launch_app("com.nonexistent.app")


class TestKillApp:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_kill_success(self):
        self.mock_device.shell.return_value = ""

        result = self.manager.kill_app("com.google.android.chrome")

        assert "Force-stopped" in result


class TestPressKey:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_press_friendly_name(self):
        self.mock_device.shell.return_value = ""

        result = self.manager.press_key("BACK")

        assert "Pressed" in result
        # Verify the correct KEYCODE was sent
        self.mock_device.shell.assert_called_with("input keyevent KEYCODE_BACK")

    def test_press_home(self):
        self.mock_device.shell.return_value = ""

        self.manager.press_key("HOME")

        self.mock_device.shell.assert_called_with("input keyevent KEYCODE_HOME")

    def test_press_raw_keycode(self):
        self.mock_device.shell.return_value = ""

        result = self.manager.press_key("KEYCODE_SPACE")

        assert "Pressed" in result

    def test_press_unknown_key(self):
        with pytest.raises(ValueError, match="Unknown key"):
            self.manager.press_key("NONEXISTENT")

    def test_all_key_mappings_exist(self):
        """Verify all documented friendly names are in KEY_MAP."""
        expected = ["BACK", "HOME", "ENTER", "RECENT", "VOLUME_UP",
                    "VOLUME_DOWN", "TAB", "DELETE", "ESCAPE", "POWER",
                    "WAKEUP", "CAMERA", "SEARCH"]
        for key in expected:
            assert key in KEY_MAP


class TestSwipe:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_swipe_default_duration(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = ""

        result = self.manager.swipe(100, 200, 100, 800)

        assert "Swiped" in result
        self.mock_device.shell.assert_called_with("input swipe 100 200 100 800 300")

    def test_swipe_custom_duration(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = ""

        result = self.manager.swipe(0, 0, 1080, 2400, duration_ms=1000)

        assert "1000ms" in result


class TestTypeText:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_type_simple_text(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = ""

        result = self.manager.type_text("hello")

        assert "Typed" in result
        assert "hello" in result

    def test_type_text_with_spaces(self):
        self.manager._ensure_screen_awake = MagicMock()
        self.mock_device.shell.return_value = ""

        result = self.manager.type_text("hello world")

        assert "Typed" in result
        # Verify spaces were replaced with %s in the shell command
        shell_calls = [str(c) for c in self.mock_device.shell.call_args_list]
        assert any("%s" in c for c in shell_calls)


class TestGetClipboard:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_get_clipboard_success(self):
        self.mock_device.shell.return_value = 'Broadcast completed: result=0, data="hello clipboard"'

        result = self.manager.get_clipboard()

        assert "hello clipboard" in result

    def test_get_clipboard_no_clipper(self):
        self.mock_device.shell.side_effect = Exception("not found")

        result = self.manager.get_clipboard()

        assert "Clipper" in result or "failed" in result


class TestSetClipboard:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_set_clipboard_success(self):
        self.mock_device.shell.return_value = "Broadcast completed: result=0"

        result = self.manager.set_clipboard("test text")

        assert "Clipboard set" in result

    def test_set_clipboard_no_clipper(self):
        self.mock_device.shell.side_effect = Exception("not found")

        result = self.manager.set_clipboard("test")

        assert "Clipper" in result or "failed" in result


class TestGetNotifications:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_get_notifications_with_data(self):
        notif_output = """
NotificationRecord(0x1234 pkg=com.whatsapp user=UserHandle{0} importanceReasonCode=0 key=0|com.whatsapp|123|null|10123):
  pkg=com.whatsapp
  extras={
    android.title=John Doe
    android.text=Hello there! android.subText=null
  }
NotificationRecord(0x5678 pkg=com.google.android.gm user=UserHandle{0}):
  pkg=com.google.android.gm
  extras={
    android.title=New email
    android.text=Meeting tomorrow android.bigText=details
  }
"""
        self.mock_device.shell.return_value = notif_output

        result = self.manager.get_notifications()

        assert "com.whatsapp" in result
        assert "John Doe" in result
        assert "Hello there!" in result
        assert "com.google.android.gm" in result

    def test_get_notifications_empty(self):
        self.mock_device.shell.return_value = ""

        result = self.manager.get_notifications()

        assert "No notifications" in result


class TestGetUilayoutUpgraded:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_default_returns_all_with_text(self):
        """Default mode returns all elements with text or content-desc."""
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.get_uilayout()

        assert "OK" in result
        assert "Cancel" in result
        assert "App Logo" in result  # content-desc element

    def test_clickable_only(self):
        """clickable_only=True returns legacy behavior."""
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.get_uilayout(clickable_only=True)

        assert "OK" in result
        assert "Cancel" in result
        # The FrameLayout has no text and the ImageView has content-desc but is NOT clickable
        # Actually the ImageView IS not clickable, so it should be filtered out
        # But "App Logo" is content-desc on a non-clickable element
        assert "App Logo" not in result

    def test_filter_text(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.get_uilayout(filter_text="OK")

        assert "OK" in result
        assert "Cancel" not in result

    def test_filter_resource_id(self):
        self.manager._ensure_screen_awake = MagicMock()
        root = ET.fromstring(SAMPLE_UI_XML)

        with patch('adbdevicemanager.dump_and_pull', return_value=root):
            result = self.manager.get_uilayout(filter_resource_id="button1")

        assert "OK" in result
        assert "Cancel" not in result


class TestEnsureScreenAwake:
    def setup_method(self):
        self.manager, self.mock_device = _create_mock_manager()

    def test_screen_awake_no_action(self):
        self.mock_device.shell.return_value = "mWakefulness=Awake"

        self.manager._ensure_screen_awake()

        # Should only call dumpsys power, not WAKEUP
        calls = [str(c) for c in self.mock_device.shell.call_args_list]
        assert not any("WAKEUP" in c for c in calls)

    def test_screen_asleep_sends_wakeup(self):
        self.mock_device.shell.return_value = "mWakefulness=Asleep"

        with patch('adbdevicemanager.time.sleep'):
            self.manager._ensure_screen_awake()

        calls = [str(c) for c in self.mock_device.shell.call_args_list]
        assert any("WAKEUP" in c for c in calls)


class TestDisableAnimations:
    def test_disables_all_three_scales(self):
        """Verify all 3 animation scales are set to 0."""
        with patch('adbdevicemanager.AdbDeviceManager.check_adb_installed', return_value=True), \
             patch('adbdevicemanager.AdbDeviceManager.get_available_devices', return_value=["test"]), \
             patch('adbdevicemanager.AdbClient') as mock_client:
            mock_device = MagicMock()
            mock_device.shell.return_value = ""
            mock_client.return_value.device.return_value = mock_device

            manager = AdbDeviceManager(device_name=None, exit_on_error=False)

            shell_calls = [str(c) for c in mock_device.shell.call_args_list]
            assert any("window_animation_scale" in c for c in shell_calls)
            assert any("transition_animation_scale" in c for c in shell_calls)
            assert any("animator_duration_scale" in c for c in shell_calls)


class TestRetryDecorator:
    """Test the retry module."""

    def test_retry_succeeds_first_try(self):
        from retry import retry

        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retry_succeeds_after_failures(self):
        from retry import retry

        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return "ok"

        assert fail_then_succeed() == "ok"
        assert call_count == 3

    def test_retry_exhausted(self):
        from retry import retry

        @retry(max_attempts=2, base_delay=0.01)
        def always_fail():
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError, match="permanent"):
            always_fail()

    def test_retry_specific_exceptions(self):
        from retry import retry

        @retry(max_attempts=3, base_delay=0.01, exceptions=(ValueError,))
        def raise_type_error():
            raise TypeError("wrong type")

        # TypeError is not in exceptions tuple, should not retry
        with pytest.raises(TypeError):
            raise_type_error()
