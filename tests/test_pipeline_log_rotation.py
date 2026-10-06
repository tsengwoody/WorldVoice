"""The pipeline log keeps one previous file once it grows past its size limit."""

import pytest
from addon_loader import WORLDVOICE, load_source


@pytest.fixture
def pipeline_log(monkeypatch, tmp_path):
	module = load_source(monkeypatch, "worldvoice_log_rotation_under_test", WORLDVOICE / "log.py")
	monkeypatch.setattr(module, "log_dir", tmp_path)
	monkeypatch.setattr(module, "MAX_LOG_SIZE", 200)
	return module.PipelineLog("pipeline.csv")


def rows(path):
	return path.read_text(encoding="utf-8").splitlines()


def write_until_full(pipeline_log, label):
	count = 0
	while not pipeline_log.log_file.exists() or pipeline_log.log_file.stat().st_size < 200:
		pipeline_log.write(f"{label}{count}", label, "before", ["text"])
		count += 1
	return count


def test_a_full_log_moves_aside_before_the_next_write(pipeline_log):
	written = write_until_full(pipeline_log, "first")
	pipeline_log.write("next", "next", "before", ["text"])
	old = pipeline_log.log_file.with_suffix(".old")
	assert len(rows(old)) == written + 1
	assert rows(old)[1].startswith("first0,")
	current = rows(pipeline_log.log_file)
	assert current[0] == ",".join(pipeline_log.FIELDNAMES)
	assert len(current) == 2 and current[1].startswith("next,")


def test_only_the_latest_full_log_is_kept(pipeline_log):
	write_until_full(pipeline_log, "first")
	pipeline_log.write("second", "second", "before", ["text"])
	write_until_full(pipeline_log, "second")
	pipeline_log.write("third", "third", "before", ["text"])
	old = rows(pipeline_log.log_file.with_suffix(".old"))
	assert old[1].startswith("second,")
	assert not any(row.startswith("first") for row in old)
	assert rows(pipeline_log.log_file)[1].startswith("third,")
