import yaml

from cmt_mcp.register import main, register_hermes


def test_creates_config_with_entry(tmp_path):
    p = tmp_path / ".hermes" / "config.yaml"
    register_hermes(p, "a@example.com", "pw")
    e = yaml.safe_load(p.read_text())["mcp_servers"]["cmt"]
    assert e["command"] == "uv" and e["args"][-2:] == ["run", "cmt-mcp"]
    assert e["env"] == {"CMT_EMAIL": "a@example.com", "CMT_PASSWORD": "pw"}
    assert oct(p.stat().st_mode)[-3:] == "600"


def test_preserves_other_servers_and_backs_up(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("model: x\nmcp_servers:\n  other:\n    command: foo\n")
    register_hermes(p, "a@example.com", "pw")
    cfg = yaml.safe_load(p.read_text())
    assert cfg["model"] == "x" and cfg["mcp_servers"]["other"] == {"command": "foo"} and "cmt" in cfg["mcp_servers"]
    assert (tmp_path / "config.yaml.bak").exists()


def test_idempotent(tmp_path):
    p = tmp_path / "config.yaml"
    register_hermes(p, "a@example.com", "pw")
    register_hermes(p, "b@example.com", "pw2")
    assert yaml.safe_load(p.read_text())["mcp_servers"]["cmt"]["env"]["CMT_EMAIL"] == "b@example.com"


def test_dry_run_writes_nothing_and_masks(tmp_path, monkeypatch, capsys):
    p = tmp_path / "config.yaml"
    monkeypatch.setenv("CMT_EMAIL", "a@example.com")
    monkeypatch.setenv("CMT_PASSWORD", "s3cret")
    main(["hermes", "--config", str(p), "--dry-run"])
    assert not p.exists()
    out = capsys.readouterr().out
    assert "s3cret" not in out and "***" in out


def test_prompts_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("CMT_EMAIL", raising=False)
    monkeypatch.delenv("CMT_PASSWORD", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "me@example.com")
    monkeypatch.setattr("getpass.getpass", lambda _: "typed-pw")
    p = tmp_path / "config.yaml"
    main(["hermes", "--config", str(p)])
    assert yaml.safe_load(p.read_text())["mcp_servers"]["cmt"]["env"] == {"CMT_EMAIL": "me@example.com", "CMT_PASSWORD": "typed-pw"}
