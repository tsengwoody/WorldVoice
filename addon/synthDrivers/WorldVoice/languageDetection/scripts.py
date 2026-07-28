from bisect import bisect_right

from .script_data import SCRIPT_RANGES, SCRIPT_RANGE_STARTS


def get_script(codepoint: int) -> str | None:
	index = bisect_right(SCRIPT_RANGE_STARTS, codepoint) - 1
	if index < 0:
		return None
	_start, end, script = SCRIPT_RANGES[index]
	if codepoint > end:
		return None
	return script
