from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

ScriptRange = tuple[int, int, str]


def parse_scripts(lines: Iterable[str]) -> list[ScriptRange]:
	ranges: list[ScriptRange] = []
	for line_number, raw_line in enumerate(lines, start=1):
		payload = raw_line.partition("#")[0].strip()
		if not payload:
			continue
		fields = [field.strip() for field in payload.split(";")]
		if len(fields) != 2:
			raise ValueError(f"line {line_number}: expected code range and Script")
		code_range, script = fields
		bounds = code_range.split("..", maxsplit=1)
		start = int(bounds[0], 16)
		end = int(bounds[1], 16) if len(bounds) == 2 else start
		if start > end:
			raise ValueError(f"line {line_number}: reversed range")
		ranges.append((start, end, script))

	ranges.sort(key=lambda item: item[0])
	merged: list[ScriptRange] = []
	for start, end, script in ranges:
		if merged and start <= merged[-1][1]:
			raise ValueError(f"range overlap at U+{start:04X}")
		if merged and start == merged[-1][1] + 1 and script == merged[-1][2]:
			previous_start, _previous_end, _previous_script = merged[-1]
			merged[-1] = (previous_start, end, script)
		else:
			merged.append((start, end, script))
	return merged


def render_module(
		ranges: list[ScriptRange],
		unicode_version: str,
		source_sha256: str,
) -> str:
	lines = [
		'"""Generated Unicode Script ranges. Do not edit by hand."""',
		"",
		f'UNICODE_VERSION = "{unicode_version}"',
		f'SOURCE_SHA256 = "{source_sha256}"',
		"SCRIPT_RANGES = (",
	]
	lines.extend(
		f'\t(0x{start:x}, 0x{end:x}, "{script}"),'
		for start, end, script in ranges
	)
	lines.extend((
		")",
		"SCRIPT_RANGE_STARTS = tuple(start for start, _end, _script in SCRIPT_RANGES)",
		"",
	))
	return "\n".join(lines)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("source", type=Path)
	parser.add_argument("destination", type=Path)
	parser.add_argument("--unicode-version", required=True)
	parser.add_argument("--expected-sha256", required=True)
	args = parser.parse_args()
	source_bytes = args.source.read_bytes()
	actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
	if actual_sha256 != args.expected_sha256:
		raise SystemExit(
			f"Scripts.txt checksum mismatch: {actual_sha256} != {args.expected_sha256}"
		)
	ranges = parse_scripts(source_bytes.decode("utf-8").splitlines())
	args.destination.write_text(
		render_module(ranges, args.unicode_version, actual_sha256),
		encoding="utf-8",
		newline="\n",
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
