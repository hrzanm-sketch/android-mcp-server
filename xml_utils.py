"""Reusable XML parsing helpers for Android UI dumps."""

import logging
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """Parse bounds string '[x1,y1][x2,y2]' into (x1, y1, x2, y2)."""
    matches = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
    if len(matches) == 2:
        x1, y1 = int(matches[0][0]), int(matches[0][1])
        x2, y2 = int(matches[1][0]), int(matches[1][1])
        return x1, y1, x2, y2
    return None


def calculate_center(bounds_str: str) -> tuple[int, int] | None:
    """Calculate center point from bounds string '[x1,y1][x2,y2]'."""
    parsed = parse_bounds(bounds_str)
    if parsed:
        x1, y1, x2, y2 = parsed
        return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def parse_ui_dump(xml_path: str) -> ET.Element:
    """Parse a UI dump XML file and return root element."""
    tree = ET.parse(xml_path)
    return tree.getroot()


def find_element(
    root: ET.Element,
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
) -> ET.Element | None:
    """Find first UI element matching any of the given criteria.

    Args:
        root: Root XML element from UI dump
        text: Match element text attribute
        resource_id: Match element resource-id attribute
        content_desc: Match element content-desc attribute

    Returns:
        First matching Element or None
    """
    for element in root.iter("node"):
        if text and element.get("text", "") == text:
            return element
        if resource_id and element.get("resource-id", "") == resource_id:
            return element
        if content_desc and element.get("content-desc", "") == content_desc:
            return element
    return None


def find_all_elements(
    root: ET.Element,
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
) -> list[ET.Element]:
    """Find all UI elements matching any of the given criteria.

    Args:
        root: Root XML element from UI dump
        text: Match element text attribute
        resource_id: Match element resource-id attribute
        content_desc: Match element content-desc attribute

    Returns:
        List of matching Elements
    """
    results = []
    for element in root.iter("node"):
        if text and element.get("text", "") == text:
            results.append(element)
        elif resource_id and element.get("resource-id", "") == resource_id:
            results.append(element)
        elif content_desc and element.get("content-desc", "") == content_desc:
            results.append(element)
    return results


def dump_and_pull(device) -> ET.Element:
    """Execute uiautomator dump, pull XML, parse, and clean up.

    Args:
        device: ppadb device object

    Returns:
        Root ET.Element of the UI dump
    """
    device.shell("uiautomator dump")
    device.pull("/sdcard/window_dump.xml", "window_dump.xml")
    device.shell("rm /sdcard/window_dump.xml")
    return parse_ui_dump("window_dump.xml")


def element_to_dict(element: ET.Element) -> dict:
    """Convert a UI element to a dictionary with useful attributes."""
    bounds = element.get("bounds", "")
    center = calculate_center(bounds)
    return {
        "class": element.get("class", ""),
        "text": element.get("text", ""),
        "content_desc": element.get("content-desc", ""),
        "resource_id": element.get("resource-id", ""),
        "bounds": bounds,
        "center": center,
        "clickable": element.get("clickable", "false") == "true",
        "scrollable": element.get("scrollable", "false") == "true",
    }
