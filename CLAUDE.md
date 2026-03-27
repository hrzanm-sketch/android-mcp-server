# Android MCP Server

MCP server for programmatic control of Android devices via ADB. Used by Lotar to control Pixel 10a.

## Structure
- `server.py` — main MCP server entry point
- `adbdevicemanager.py` — ADB device management
- `xml_utils.py` — UI layout XML parsing
- `config.yaml.example` — device configuration template

## Stack
- Python, MCP protocol, ADB
- Tests in `tests/`

## Commands
- `uv run server.py` — start server
