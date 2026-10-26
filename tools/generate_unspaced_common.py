"""Generate the Common characters that the space pause counts as unspaced.

A Common character counts as unspaced when its General Category is a letter, number or symbol (not
punctuation, separator or other) and its Script_Extensions name at least one unspaced script
(decided by the user, 2026-10-25). The Script_Extensions come from Unicode's ScriptExtensions.txt,
the General Category from Unicode's UnicodeData.txt and the Script from
unicodeScripts/script_data.py. ScriptExtensions.txt and script_data.py must be of
--unicode-version; UnicodeData.txt has no version header, so its sha256 pins it. Python's
unicodedata is not used: it is of the Unicode version Python ships, so the tool works for any
Unicode version whatever Python runs it.

Without --source (ScriptExtensions.txt) or --unicode-data (UnicodeData.txt) the tool downloads
that file of --unicode-version into memory from
	https://www.unicode.org/Public/<version>/ucd/ScriptExtensions.txt
	https://www.unicode.org/Public/<version>/ucd/UnicodeData.txt
Either way each file must match its sha256 (--expected-sha256, --unicode-data-sha256); on a
mismatch the tool prints the actual digest, which a maintainer upgrading Unicode can copy after
verifying the file.

Usage:
	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py --unicode-version 16.0.0 \
		--expected-sha256 <ScriptExtensions.txt sha256> --unicode-data-sha256 <UnicodeData.txt sha256>

	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py --unicode-version 16.0.0 \
		--source ScriptExtensions.txt --expected-sha256 <ScriptExtensions.txt sha256> \
		--unicode-data UnicodeData.txt --unicode-data-sha256 <UnicodeData.txt sha256>
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import importlib.util
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DATA = ROOT / "addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py"

# The pipeline's UNSPACED_SCRIPTS, by the ISO 15924 codes ScriptExtensions.txt uses.
UNSPACED_SCRIPT_CODES = {
	"Hani": "Han",
	"Hira": "Hiragana",
	"Kana": "Katakana",
	"Bopo": "Bopomofo",
	"Thai": "Thai",
	"Laoo": "Lao",
	"Khmr": "Khmer",
	"Mymr": "Myanmar",
}
# General Category major classes: L letter, N number, S symbol.
SELECTED_CATEGORY_CLASSES = frozenset("LNS")

CategoryRange = tuple[int, int, str]
DOWNLOAD_TIMEOUT = 60


def ucd_url(unicode_version: str, name: str) -> str:
	return f"https://www.unicode.org/Public/{unicode_version}/ucd/{name}"


def download(url: str, option: str) -> bytes:
	"""The file at url, read into memory; option is the one that names a local copy instead."""
	try:
		with urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
			return response.read()
	except OSError as error:  # URLError, HTTPError and timeouts are all OSErrors.
		name = url.rpartition("/")[2]
		raise SystemExit(
			f"Could not download {url}: {error}\nPass a local copy of {name} with {option} PATH.",
		) from error


def read_local(path: Path, option: str) -> bytes:
	"""The bytes of path, which option gave."""
	try:
		return path.read_bytes()
	except OSError as error:
		raise SystemExit(f"Could not read {path} given with {option}: {error}") from error


def read_source(path: Path | None, url: str, option: str, expected_sha256: str) -> tuple[bytes, str]:
	"""The bytes of path, or of url when no path is given, and their sha256, which must be expected."""
	data = download(url, option) if path is None else read_local(path, option)
	actual_sha256 = hashlib.sha256(data).hexdigest()
	if actual_sha256 != expected_sha256:
		name = url.rpartition("/")[2]
		raise SystemExit(f"{name} checksum mismatch: actual {actual_sha256}, expected {expected_sha256}")
	return data, actual_sha256


def parse_version(lines: Iterable[str]) -> str:
	for line in lines:
		match = re.fullmatch(r"#\s*ScriptExtensions-(\d+\.\d+\.\d+)\.txt\s*", line)
		if match:
			return match.group(1)
	raise ValueError("no ScriptExtensions-<version>.txt header")


def parse_script_extensions(lines: Iterable[str]) -> dict[int, frozenset[str]]:
	extensions: dict[int, frozenset[str]] = {}
	for line_number, raw_line in enumerate(lines, start=1):
		payload = raw_line.partition("#")[0].strip()
		if not payload:
			continue
		fields = [field.strip() for field in payload.split(";")]
		if len(fields) != 2 or not fields[1]:
			raise ValueError(f"line {line_number}: expected code range and Script_Extensions")
		code_range, scripts = fields
		bounds = code_range.split("..", maxsplit=1)
		start = int(bounds[0], 16)
		end = int(bounds[1], 16) if len(bounds) == 2 else start
		if start > end:
			raise ValueError(f"line {line_number}: reversed range")
		value = frozenset(scripts.split())
		for code in range(start, end + 1):
			if code in extensions:
				raise ValueError(f"U+{code:04X} listed twice")
			extensions[code] = value
	return extensions


def parse_categories(lines: Iterable[str]) -> dict[int, str]:
	"""The General Category (field 2) of every code point UnicodeData.txt lists.

	A <..., First> line and the <..., Last> line after it stand for the whole range between them.
	Code points not listed are unassigned (Cn) and have no entry.
	"""
	categories: dict[int, str] = {}

	def assign(start: int, end: int, category: str) -> None:
		for code in range(start, end + 1):
			if code in categories:
				raise ValueError(f"U+{code:04X} listed twice")
			categories[code] = category

	first: tuple[int, str, str] | None = None
	for line_number, raw_line in enumerate(lines, start=1):
		if not raw_line.strip():
			continue
		fields = raw_line.split(";")
		if len(fields) != 15:
			raise ValueError(f"line {line_number}: expected 15 fields")
		code, name, category = int(fields[0], 16), fields[1], fields[2]
		if first is not None:
			first_code, first_name, first_category = first
			if name != f"<{first_name}, Last>" or category != first_category or code < first_code:
				raise ValueError(f"line {line_number}: expected the Last of <{first_name}, First>")
			assign(first_code, code, category)
			first = None
		elif name.endswith(", First>"):
			first = (code, name[1 : -len(", First>")], category)
		elif name.endswith(", Last>"):
			raise ValueError(f"line {line_number}: a Last without its First")
		else:
			assign(code, code, category)
	if first is not None:
		raise ValueError(f"<{first[1]}, First> without its Last")
	return categories


def select_unspaced_common(
	extensions: dict[int, frozenset[str]],
	script_of: Callable[[int], str | None],
	category_of: Callable[[int], str],
) -> list[int]:
	"""The code points whose Script is Common, category L, N or S, and Script_Extensions unspaced."""
	return sorted(
		code
		for code, scripts in extensions.items()
		if script_of(code) == "Common"
		and category_of(code)[0] in SELECTED_CATEGORY_CLASSES
		and not scripts.isdisjoint(UNSPACED_SCRIPT_CODES)
	)


def to_ranges(code_points: list[int], category_of: Callable[[int], str]) -> list[CategoryRange]:
	"""Runs of consecutive code points of one General Category."""
	ranges: list[CategoryRange] = []
	for code in code_points:
		category = category_of(code)
		if ranges and code == ranges[-1][1] + 1 and category == ranges[-1][2]:
			ranges[-1] = (ranges[-1][0], code, category)
		else:
			ranges.append((code, code, category))
	return ranges


def render_module(
	ranges: list[CategoryRange],
	unicode_version: str,
	source_sha256: str,
	unicode_data_sha256: str,
) -> str:
	lines = [
		'"""Generated by tools/generate_unspaced_common.py. Do not edit by hand.',
		"",
		"The Common characters the space pause counts as unspaced: General Category letter, number or",
		"symbol, with an unspaced script in their Script_Extensions.",
		'"""',
		"",
		f'UNICODE_VERSION = "{unicode_version}"',
		f'SOURCE_SHA256 = "{source_sha256}"',
		f'UNICODE_DATA_SHA256 = "{unicode_data_sha256}"',
		"UNSPACED_COMMON_RANGES = (",
	]
	for start, end, category in ranges:
		shown = chr(start) if start == end else f"{chr(start)}..{chr(end)}"
		lines.append(f"\t(0x{start:X}, 0x{end:X}),  # {shown} {category}")
	lines.extend(
		(
			")",
			"UNSPACED_COMMON = frozenset(",
			"\tchr(code) for start, end in UNSPACED_COMMON_RANGES for code in range(start, end + 1)",
			")",
			"",
		)
	)
	return "\n".join(lines)


def check_versions(source: str, *, requested: str, script_data: str) -> None:
	if requested != source:
		raise SystemExit(f"--unicode-version is {requested}, the source {source}")
	if script_data != source:
		raise SystemExit(f"script_data.py has Unicode {script_data}, the source {source}")


def load_script_of(path: Path) -> tuple[str, Callable[[int], str | None]]:
	spec = importlib.util.spec_from_file_location("script_data", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	def script_of(code: int) -> str | None:
		index = bisect.bisect_right(module.SCRIPT_RANGE_STARTS, code) - 1
		if index < 0:
			return None
		_start, end, script = module.SCRIPT_RANGES[index]
		return script if code <= end else None

	return module.UNICODE_VERSION, script_of


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		description="Generate unspaced_common_data.py from Unicode's ScriptExtensions.txt and UnicodeData.txt.",
	)
	parser.add_argument("destination", type=Path, help="the unspaced_common_data.py to write")
	parser.add_argument("--unicode-version", required=True, help="for example 16.0.0")
	parser.add_argument(
		"--source",
		type=Path,
		help="a local ScriptExtensions.txt; without it the tool downloads the one of --unicode-version",
	)
	parser.add_argument("--expected-sha256", required=True, help="the sha256 of ScriptExtensions.txt")
	parser.add_argument(
		"--unicode-data",
		type=Path,
		help="a local UnicodeData.txt; without it the tool downloads the one of --unicode-version",
	)
	parser.add_argument("--unicode-data-sha256", required=True, help="the sha256 of UnicodeData.txt")
	parser.add_argument("--script-data", type=Path, default=SCRIPT_DATA)
	args = parser.parse_args(argv)
	source_bytes, source_sha256 = read_source(
		args.source,
		ucd_url(args.unicode_version, "ScriptExtensions.txt"),
		"--source",
		args.expected_sha256,
	)
	lines = source_bytes.decode("utf-8").splitlines()
	unicode_version = parse_version(lines)
	script_data_version, script_of = load_script_of(args.script_data)
	check_versions(unicode_version, requested=args.unicode_version, script_data=script_data_version)
	unicode_data_bytes, unicode_data_sha256 = read_source(
		args.unicode_data,
		ucd_url(args.unicode_version, "UnicodeData.txt"),
		"--unicode-data",
		args.unicode_data_sha256,
	)
	categories = parse_categories(unicode_data_bytes.decode("utf-8").splitlines())

	def category_of(code: int) -> str:
		return categories.get(code, "Cn")

	code_points = select_unspaced_common(parse_script_extensions(lines), script_of, category_of)
	args.destination.write_text(
		render_module(
			to_ranges(code_points, category_of),
			unicode_version,
			source_sha256,
			unicode_data_sha256,
		),
		encoding="utf-8",
		newline="\n",
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
