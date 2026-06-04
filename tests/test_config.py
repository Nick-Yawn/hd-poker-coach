import os

from holdem_coach.config import _parse, load_dotenv


def test_parse_basics():
    env = _parse(
        "\n".join(
            [
                "# a comment",
                "",
                "ANTHROPIC_API_KEY=sk-ant-123",
                'QUOTED="with spaces"',
                "export EXPORTED=value",
                "no_equals_line_ignored",
            ]
        )
    )
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-123"
    assert env["QUOTED"] == "with spaces"
    assert env["EXPORTED"] == "value"
    assert "no_equals_line_ignored" not in env


def test_load_dotenv_sets_missing_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    loaded = load_dotenv()
    assert loaded == tmp_path / ".env"
    assert os.environ["ANTHROPIC_API_KEY"] == "from-file"


def test_existing_env_var_wins_without_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    load_dotenv()
    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"
    load_dotenv(override=True)
    assert os.environ["ANTHROPIC_API_KEY"] == "from-file"


def test_load_dotenv_tolerates_utf8_bom(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Simulate PowerShell `Set-Content -Encoding utf8` (writes a BOM).
    (tmp_path / ".env").write_bytes(
        b"\xef\xbb\xbfANTHROPIC_API_KEY=bom-key\n"
    )
    load_dotenv()
    assert os.environ["ANTHROPIC_API_KEY"] == "bom-key"


def test_load_dotenv_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_dotenv() is None
