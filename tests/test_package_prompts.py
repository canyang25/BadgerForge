import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_prompt_markdown_is_included_in_the_package():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["setuptools"]["package-data"]["agent.prompts"] == ["*.md"]
