from pathlib import Path
import pytest
from migrate import discover_migrations


def test_orders_by_numeric_version(tmp_path):
    for name in ["1000_future.sql", "999_previous.sql", "005_next.sql"]:
        (tmp_path / name).write_text("SELECT 1;")
    assert [p.name for p in discover_migrations(tmp_path)] == ["005_next.sql", "999_previous.sql", "1000_future.sql"]


def test_rejects_duplicate_version(tmp_path):
    for name in ["005_first.sql", "005_second.sql"]:
        (tmp_path / name).write_text("SELECT 1;")
    with pytest.raises(RuntimeError, match="repetido"):
        discover_migrations(tmp_path)


def test_rejects_misnamed_sql(tmp_path):
    (tmp_path / "forgot_version.sql").write_text("SELECT 1;")
    with pytest.raises(RuntimeError):
        discover_migrations(tmp_path)
