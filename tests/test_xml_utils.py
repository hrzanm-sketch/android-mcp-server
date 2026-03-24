"""Tests for xml_utils module."""

import os
import tempfile
import xml.etree.ElementTree as ET

import pytest

from xml_utils import (
    calculate_center,
    element_to_dict,
    find_all_elements,
    find_element,
    parse_bounds,
    parse_ui_dump,
)

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        content-desc="" clickable="false" scrollable="false"
        bounds="[0,0][1080,2400]">
    <node index="0" text="Settings" resource-id="com.android.settings:id/title"
          class="android.widget.TextView" content-desc=""
          clickable="true" scrollable="false"
          bounds="[0,100][540,200]">
    </node>
    <node index="1" text="" resource-id="com.android.settings:id/icon"
          class="android.widget.ImageView" content-desc="Settings icon"
          clickable="true" scrollable="false"
          bounds="[540,100][1080,200]">
    </node>
    <node index="2" text="Search" resource-id="com.android.settings:id/search"
          class="android.widget.EditText" content-desc=""
          clickable="true" scrollable="false"
          bounds="[100,300][980,400]">
    </node>
    <node index="3" text="" resource-id="" class="android.widget.ScrollView"
          content-desc="" clickable="false" scrollable="true"
          bounds="[0,400][1080,2400]">
      <node index="0" text="Wi-Fi" resource-id="com.android.settings:id/wifi"
            class="android.widget.TextView" content-desc=""
            clickable="true" scrollable="false"
            bounds="[0,400][1080,500]">
      </node>
    </node>
  </node>
</hierarchy>
"""


@pytest.fixture
def sample_root():
    """Parse sample XML and return root element."""
    return ET.fromstring(SAMPLE_XML)


@pytest.fixture
def sample_xml_file():
    """Write sample XML to temp file, yield path, clean up."""
    fd, path = tempfile.mkstemp(suffix=".xml")
    with os.fdopen(fd, "w") as f:
        f.write(SAMPLE_XML)
    yield path
    os.unlink(path)


class TestParseBounds:
    def test_valid_bounds(self):
        assert parse_bounds("[0,100][540,200]") == (0, 100, 540, 200)

    def test_large_bounds(self):
        assert parse_bounds("[0,0][1080,2400]") == (0, 0, 1080, 2400)

    def test_invalid_bounds(self):
        assert parse_bounds("invalid") is None

    def test_empty_string(self):
        assert parse_bounds("") is None

    def test_single_bracket(self):
        assert parse_bounds("[0,100]") is None


class TestCalculateCenter:
    def test_valid_center(self):
        assert calculate_center("[0,100][540,200]") == (270, 150)

    def test_full_screen(self):
        assert calculate_center("[0,0][1080,2400]") == (540, 1200)

    def test_invalid_bounds(self):
        assert calculate_center("invalid") is None


class TestParseUiDump:
    def test_parse_valid_file(self, sample_xml_file):
        root = parse_ui_dump(sample_xml_file)
        assert root.tag == "hierarchy"
        assert root.get("rotation") == "0"

    def test_parse_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            parse_ui_dump("/nonexistent/path.xml")


class TestFindElement:
    def test_find_by_text(self, sample_root):
        element = find_element(sample_root, text="Settings")
        assert element is not None
        assert element.get("text") == "Settings"

    def test_find_by_resource_id(self, sample_root):
        element = find_element(sample_root, resource_id="com.android.settings:id/search")
        assert element is not None
        assert element.get("text") == "Search"

    def test_find_by_content_desc(self, sample_root):
        element = find_element(sample_root, content_desc="Settings icon")
        assert element is not None
        assert element.get("class") == "android.widget.ImageView"

    def test_not_found(self, sample_root):
        element = find_element(sample_root, text="Nonexistent")
        assert element is None

    def test_no_criteria(self, sample_root):
        element = find_element(sample_root)
        assert element is None

    def test_find_nested_element(self, sample_root):
        element = find_element(sample_root, text="Wi-Fi")
        assert element is not None
        assert element.get("resource-id") == "com.android.settings:id/wifi"


class TestFindAllElements:
    def test_find_multiple_by_text(self, sample_root):
        # Only one "Settings" text element
        elements = find_all_elements(sample_root, text="Settings")
        assert len(elements) == 1

    def test_find_by_resource_id(self, sample_root):
        elements = find_all_elements(sample_root, resource_id="com.android.settings:id/title")
        assert len(elements) == 1

    def test_empty_results(self, sample_root):
        elements = find_all_elements(sample_root, text="Nonexistent")
        assert elements == []


class TestElementToDict:
    def test_clickable_element(self, sample_root):
        element = find_element(sample_root, text="Settings")
        result = element_to_dict(element)
        assert result["text"] == "Settings"
        assert result["clickable"] is True
        assert result["scrollable"] is False
        assert result["center"] == (270, 150)
        assert result["class"] == "android.widget.TextView"
        assert result["resource_id"] == "com.android.settings:id/title"

    def test_scrollable_element(self, sample_root):
        # Find the ScrollView
        for node in sample_root.iter("node"):
            if node.get("class") == "android.widget.ScrollView":
                result = element_to_dict(node)
                assert result["scrollable"] is True
                assert result["clickable"] is False
                break
