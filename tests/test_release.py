from lightworker.release import bump_version_files


def test_bump_version_files_updates_both_anchors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "lightworker"\nversion = "0.5.0"\n', encoding="utf-8"
    )
    pkg = tmp_path / "lightworker"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('__version__ = "0.5.0"\n', encoding="utf-8")

    assert bump_version_files("0.5.1") is True
    assert 'version = "0.5.1"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.5.1"' in (pkg / "__init__.py").read_text(encoding="utf-8")


def test_bump_version_files_fails_on_missing_anchor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    pkg = tmp_path / "lightworker"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    assert bump_version_files("0.5.1") is False
