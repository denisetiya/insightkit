from __future__ import annotations

import pytest
from pydantic import ValidationError

from insightkit.config import Config


def test_config_from_yaml(demo_config: dict, tmp_path) -> None:
    import yaml

    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(yaml.safe_dump(demo_config))
    cfg = Config.from_yaml(cfg_path)
    assert cfg.database.url == demo_config["database"]["url"]
    assert cfg.security.row_limit == 1000
    assert cfg.insight.language == "en"


def test_config_invalid_dsn_missing() -> None:
    with pytest.raises(ValidationError):
        Config()  # database.url required


def test_config_env_override(demo_config: dict, tmp_path, monkeypatch) -> None:
    import yaml

    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(yaml.safe_dump(demo_config))
    monkeypatch.setenv("INSIGHTKIT_SECURITY__ROW_LIMIT", "500")
    cfg = Config.from_yaml(cfg_path)
    assert cfg.security.row_limit == 500


def test_config_bad_language(demo_config: dict) -> None:
    demo_config["insight"] = {"language": "fr"}
    with pytest.raises(ValidationError):
        Config(**demo_config)


def test_config_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        Config.from_yaml(tmp_path / "nope.yml")
