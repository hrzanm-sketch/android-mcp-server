"""
Tests for AdbDeviceManager
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from adbdevicemanager import AdbDeviceManager
from exceptions import DeviceNotFoundError

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAdbDeviceManager:
    """Test AdbDeviceManager functionality"""

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    @patch('adbdevicemanager.AdbClient')
    def test_single_device_auto_selection(self, mock_adb_client, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test auto-selection when only one device is connected"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = ["device123"]
        mock_device = MagicMock()
        mock_adb_client.return_value.device.return_value = mock_device

        manager = AdbDeviceManager(device_name=None, exit_on_error=False)

        mock_adb_client.return_value.device.assert_called_once_with("device123")
        assert manager.device == mock_device

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    def test_multiple_devices_no_selection_error(self, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test error when multiple devices are connected but none specified"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = ["device123", "device456"]

        with pytest.raises(DeviceNotFoundError) as exc_info:
            AdbDeviceManager(device_name=None, exit_on_error=False)

        assert "Multiple devices connected" in str(exc_info.value)
        assert "device123" in str(exc_info.value)
        assert "device456" in str(exc_info.value)

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    @patch('adbdevicemanager.AdbClient')
    def test_specific_device_selection(self, mock_adb_client, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test selecting a specific device"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = ["device123", "device456"]
        mock_device = MagicMock()
        mock_adb_client.return_value.device.return_value = mock_device

        manager = AdbDeviceManager(device_name="device456", exit_on_error=False)

        mock_adb_client.return_value.device.assert_called_once_with("device456")
        assert manager.device == mock_device

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    def test_device_not_found_error(self, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test error when specified device is not found"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = ["device123", "device456"]

        with pytest.raises(DeviceNotFoundError) as exc_info:
            AdbDeviceManager(device_name="non-existent-device", exit_on_error=False)

        assert "Device non-existent-device not found" in str(exc_info.value)
        assert "Available devices" in str(exc_info.value)

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    def test_no_devices_connected_error(self, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test error when no devices are connected"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = []

        with pytest.raises(DeviceNotFoundError) as exc_info:
            AdbDeviceManager(device_name=None, exit_on_error=False)

        assert "No devices connected" in str(exc_info.value)

    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    def test_adb_not_installed_error(self, mock_check_adb):
        """Test error when ADB is not installed"""
        mock_check_adb.return_value = False

        with pytest.raises(DeviceNotFoundError) as exc_info:
            AdbDeviceManager(device_name=None, exit_on_error=False)

        assert "adb is not installed" in str(exc_info.value)

    @patch('subprocess.run')
    def test_check_adb_installed_success(self, mock_run):
        """Test successful ADB installation check"""
        mock_run.return_value = MagicMock()

        result = AdbDeviceManager.check_adb_installed()

        assert result is True
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_check_adb_installed_failure(self, mock_run):
        """Test failed ADB installation check"""
        mock_run.side_effect = FileNotFoundError()

        result = AdbDeviceManager.check_adb_installed()

        assert result is False

    @patch('adbdevicemanager.AdbClient')
    def test_get_available_devices(self, mock_adb_client):
        """Test getting available devices"""
        mock_device1 = MagicMock()
        mock_device1.serial = "device123"
        mock_device2 = MagicMock()
        mock_device2.serial = "device456"

        mock_adb_client.return_value.devices.return_value = [mock_device1, mock_device2]

        devices = AdbDeviceManager.get_available_devices()

        assert devices == ["device123", "device456"]

    @patch('adbdevicemanager.AdbDeviceManager._disable_animations')
    @patch('adbdevicemanager.AdbDeviceManager.check_adb_installed')
    @patch('adbdevicemanager.AdbDeviceManager.get_available_devices')
    @patch('adbdevicemanager.AdbClient')
    def test_exit_on_error_true(self, mock_adb_client, mock_get_devices, mock_check_adb, mock_disable_anim):
        """Test that exit_on_error=True calls sys.exit"""
        mock_check_adb.return_value = True
        mock_get_devices.return_value = []

        with patch('sys.exit') as mock_exit:
            AdbDeviceManager(device_name=None, exit_on_error=True)

        mock_exit.assert_called_once_with(1)
