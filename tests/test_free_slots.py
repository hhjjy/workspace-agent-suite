"""Unit tests for find_free_slots — offline, no network/LLM needed.

Run:  python tests/test_free_slots.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendar_agent import (
    _compute_free_slots as f,
    find_free_slots,
    EXTRA_TOOLS,
    WORKSPACE_MCP_CONFIG,
)

# 1: no busy -> whole working day free
assert f("2026-06-02", []) == [("09:00", "18:00")], "1"

# 2: meeting 13:00-14:00 Taipei = 05:00-06:00Z
assert f("2026-06-02", ["2026-06-02T05:00:00Z to 2026-06-02T06:00:00Z"]) == [
    ("09:00", "13:00"), ("14:00", "18:00")], "2"

# 3: two overlapping busy -> merged (01:30-02:30Z, 02:00-03:00Z = 09:30-11:00 TPE)
assert f("2026-06-02", ["2026-06-02T01:30:00Z to 2026-06-02T02:30:00Z",
                        "2026-06-02T02:00:00Z to 2026-06-02T03:00:00Z"]) == [
    ("09:00", "09:30"), ("11:00", "18:00")], "3"

# 4: busy outside working hours (21:00-22:00 TPE = 13:00-14:00Z) -> fully free
assert f("2026-06-02", ["2026-06-02T13:00:00Z to 2026-06-02T14:00:00Z"]) == [
    ("09:00", "18:00")], "4"

# 5: busy spanning past work_end (17:00-19:00 TPE = 09:00-11:00Z) -> clipped to 17:00
assert f("2026-06-02", ["2026-06-02T09:00:00Z to 2026-06-02T11:00:00Z"]) == [
    ("09:00", "17:00")], "5"

# 6: '/' separator also parses
assert f("2026-06-02", ["2026-06-02T05:00:00Z/2026-06-02T06:00:00Z"]) == [
    ("09:00", "13:00"), ("14:00", "18:00")], "6"

# 7: custom working hours
assert f("2026-06-02", [], work_start="10:00", work_end="12:00") == [
    ("10:00", "12:00")], "7"

# 8: garbage input -> ignored (treated as no busy)
assert f("2026-06-02", ["no timestamps here"]) == [("09:00", "18:00")], "8"

# wiring: tool registered + tier is extended
names = [t.name for t in EXTRA_TOOLS]
assert "find_free_slots" in names, names
assert WORKSPACE_MCP_CONFIG["workspace"]["args"][3] == "extended", \
    WORKSPACE_MCP_CONFIG["workspace"]["args"]

# @tool invoke path
out = find_free_slots.invoke({"date": "2026-06-02",
                              "busy_intervals": ["2026-06-02T05:00:00Z to 2026-06-02T06:00:00Z"]})
assert "09:00 to 13:00" in out and "14:00 to 18:00" in out, out

print("ALL PASS - find_free_slots")
