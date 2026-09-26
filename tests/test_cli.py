from pathlib import Path

import pytest

from hailer.cli import main
from hailer.poll import CheckReport


ROOT = Path(__file__).resolve().parents[1]


def test_workflow_matches_the_ci_contract():
    text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in text
    assert 'pip install -e ".[dev]"' in text
    assert "python -m pytest" in text
    assert "push:" in text
    assert "pull_request:" in text
    assert "main" in text


def test_readme_documents_classifier_and_consent_cap():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for domain in ("greenhouse.io", "lever.co", "linkedin.com", "indeed.com", "ashbyhq.com", "myworkday.com"):
        assert domain in readme
    for word in ("recruiter", "opportunity", "interview", "hiring"):
        assert word in readme
    assert "Auto-Submitted" in readme
    assert "100" in readme
    assert "gmail.readonly" in readme
    assert "gmail.send" in readme


def test_gitignore_keeps_secrets_out():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "client_secret.json" in text
    assert "hailer.toml" in text


def test_list_and_missing_config(capsys):
    token_dir = Path(__import__("os").environ["HAILER_TOKEN_DIR"])
    token_dir.mkdir()
    (token_dir / "b@example.com.json").write_text("{}", encoding="utf-8")
    (token_dir / "a@example.com.json").write_text("{}", encoding="utf-8")
    (token_dir / "notes.json").write_text("{}", encoding="utf-8")
    assert main(["auth", "list"]) == 0
    assert capsys.readouterr().out.splitlines() == ["a@example.com", "b@example.com"]

    assert main(["check", "--dry-run"]) == 2
    assert "config file not found" in capsys.readouterr().err


def test_check_with_no_accounts(tmp_path, capsys):
    (tmp_path / "hailer.toml").write_text(
        'notify_to = "sam@example.com"\nnotify_from = "sam.watch@gmail.com"\n',
        encoding="utf-8",
    )
    assert main(["check"]) == 0
    assert "No connected accounts" in capsys.readouterr().err


def test_check_passes_concurrency(monkeypatch, tmp_path, capsys):
    (tmp_path / "hailer.toml").write_text(
        "\n".join(
            [
                'notify_to = "sam@example.com"',
                'notify_from = "watch@example.com"',
                "concurrency = 4",
            ]
        ),
        encoding="utf-8",
    )
    token_dir = Path(__import__("os").environ["HAILER_TOKEN_DIR"])
    token_dir.mkdir()
    (token_dir / "watch@example.com.json").write_text("{}", encoding="utf-8")
    seen = {}

    def fake_run(accounts, client, store, **kwargs):
        seen["accounts"] = accounts
        seen["concurrency"] = kwargs["concurrency"]
        seen["dry_run"] = kwargs["dry_run"]
        seen["notify_from"] = kwargs["notify_from"]
        return CheckReport()

    monkeypatch.setattr("hailer.cli.run_check", fake_run)
    assert main(["check", "--dry-run"]) == 0
    assert seen == {
        "accounts": ["watch@example.com"],
        "concurrency": 4,
        "dry_run": True,
        "notify_from": "watch@example.com",
    }
    assert main(["check", "--concurrency", "3"]) == 0
    assert seen["concurrency"] == 3
    assert seen["dry_run"] is False
    assert capsys.readouterr().err == ""


def test_concurrency_flag_rejects_zero():
    with pytest.raises(SystemExit) as caught:
        main(["check", "--concurrency", "0"])
    assert caught.value.code == 2
