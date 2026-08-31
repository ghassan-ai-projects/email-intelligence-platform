"""Configuration scaffolding behavior."""

from __future__ import annotations

from mailintel.cli_setup import initialize_config


def test_initialize_config_writes_template_and_guidance(tmp_path, capsys) -> None:
    path = tmp_path / "nested" / "config.toml"
    initialize_config(path, tmp_path, "db = '{db_path}'")
    assert path.read_text() == f"db = '{tmp_path / 'mail.db'}'"
    output = capsys.readouterr().out
    assert "Wrote" in output
    assert "Next steps" in output


def test_initialize_config_does_not_overwrite_existing_file(tmp_path, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text("original")
    initialize_config(path, tmp_path, "replacement")
    assert path.read_text() == "original"
    assert "Config already exists" in capsys.readouterr().out

