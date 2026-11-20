"""Parse human durations like '1h30m' into seconds."""
import re

_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}
_PART = re.compile(r"(\d+)([hms])")


def parse_duration(text: str) -> int:
    """Return the number of seconds in a duration string such as '2h', '45m', '1h30m10s'."""
    total = 0
    for amount, unit in _PART.findall(text):
        total += int(amount) * _UNIT_SECONDS[unit]
    return total
