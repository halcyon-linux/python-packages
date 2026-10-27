"""End to end with a stub `claude` and a throwaway git repository."""

import json
import os
import stat
import subprocess
import sys

import pytest

from commitpickle import cli

# A plain string (not str.format) so the stub's own braces need no escaping.
STUB = """\
#!PYTHON
import json, os, sys
stdin = sys.stdin.read()
if os.environ.get("STUB_LOG"):
    with open(os.environ["STUB_LOG"], "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd()}, fh)
mode = os.environ.get("STUB_MODE", "")
if mode == "auth":
    print(json.dumps({"is_error": True, "result": "Not logged in - please run /login"}))
    sys.exit(1)
if mode == "crash":
    sys.stderr.write("boom\\n")
    sys.exit(2)
reply = open(os.environ["STUB_REPLY"], encoding="utf-8").read()
print(json.dumps({"type": "result", "is_error": False, "result": reply}))
"""

GOOD = "feat(auth): add token refresh\nfix(auth): handle expired sessions\nrefactor: split login\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(STUB.replace("PYTHON", sys.executable, 1), encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    reply = tmp_path / "reply.txt"
    reply.write_text(GOOD, encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.delenv("COMMITPICKLE_MODEL", raising=False)
    monkeypatch.delenv("STUB_MODE", raising=False)
    monkeypatch.delenv("STUB_LOG", raising=False)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_REPLY", str(reply))
    for key, val in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e.x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e.x",
    }.items():
        monkeypatch.setenv(key, val)

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q"], check=True)
    (repo / "a.txt").write_text("one\n")
    return repo, reply


def stage(repo):
    (repo / "a.txt").write_text("one\ntwo\n")
    subprocess.run(["git", "add", "a.txt"], check=True)


def git_out(*args):
    done = subprocess.run(["git", *args], check=False, capture_output=True, text=True)
    return done.stdout


def feed(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


def test_print_lists_suggestions(env, capsys):
    repo, _ = env
    stage(repo)
    assert cli.main(["--print"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "feat(auth): add token refresh",
        "fix(auth): handle expired sessions",
        "refactor: split login",
    ]


def test_output_json(env, capsys):
    repo, _ = env
    stage(repo)
    assert cli.main(["-o", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["messages"][0] == "feat(auth): add token refresh"


def test_claude_called_with_haiku_low_no_tools_in_neutral_dir(env, monkeypatch, tmp_path, capsys):
    repo, _ = env
    stage(repo)
    log = tmp_path / "log.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print", "because"]) == 0
    seen = json.loads(log.read_text())
    argv = seen["argv"]
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--effort") + 1] == "low"
    assert argv[argv.index("--tools") + 1] == ""
    assert "+two" in seen["stdin"] and "because" in seen["stdin"]
    assert str(repo) not in seen["cwd"]
    assert "+two" not in " ".join(argv)  # the diff travels on stdin only


def test_model_effort_and_count_flags(env, monkeypatch, tmp_path, capsys):
    repo, _ = env
    stage(repo)
    log = tmp_path / "log.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print", "-m", "sonnet", "--effort", "high", "-g", "2"]) == 0
    seen = json.loads(log.read_text())
    assert seen["argv"][seen["argv"].index("--model") + 1] == "sonnet"
    assert seen["argv"][seen["argv"].index("--effort") + 1] == "high"
    assert "Write 2 different" in seen["stdin"]
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_yes_commits_first_suggestion(env):
    repo, _ = env
    stage(repo)
    assert cli.main(["--yes"]) == 0
    assert git_out("log", "-1", "--pretty=%B").strip() == "feat(auth): add token refresh"


def test_interactive_pick_second(env, monkeypatch):
    repo, _ = env
    stage(repo)
    feed(monkeypatch, "2")
    assert cli.main([]) == 0
    assert git_out("log", "-1", "--pretty=%s").strip() == "fix(auth): handle expired sessions"


def test_interactive_enter_picks_first_and_quit_aborts(env, monkeypatch):
    repo, _ = env
    stage(repo)
    feed(monkeypatch, "q")
    assert cli.main([]) == 0
    assert git_out("log", "--oneline") == ""
    feed(monkeypatch, "")
    assert cli.main([]) == 0
    assert git_out("log", "-1", "--pretty=%s").strip() == "feat(auth): add token refresh"


def test_regenerate_then_pick(env, monkeypatch, tmp_path):
    repo, reply = env
    stage(repo)
    log = tmp_path / "log.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    feed(monkeypatch, "r", "3")
    assert cli.main([]) == 0
    assert git_out("log", "-1", "--pretty=%s").strip() == "refactor: split login"


def test_extra_git_args_after_double_dash(env):
    repo, _ = env
    stage(repo)
    assert cli.main(["--yes", "--", "--no-verify"]) == 0
    assert git_out("log", "-1", "--pretty=%s").strip().startswith("feat")


def test_no_valid_subjects_is_an_error(env, capsys):
    repo, reply = env
    stage(repo)
    reply.write_text("Sorry, I cannot help with that.\n")
    assert cli.main(["--print"]) == 1


def test_auth_error_hints_at_login(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "auth")
    assert cli.main(["--print"]) == 1
    assert "log in" in caplog.text or "/login" in caplog.text


def test_crash_is_a_clean_error(env, monkeypatch):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "crash")
    assert cli.main(["--print"]) == 1


def test_nothing_staged(env):
    assert cli.main(["--print"]) == 1


def test_not_a_terminal_requires_flag(env, monkeypatch):
    repo, _ = env
    stage(repo)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.main([]) == 1


def test_secret_files_are_left_out_of_the_prompt(env, monkeypatch, tmp_path):
    repo, _ = env
    stage(repo)
    (repo / ".env").write_text("TOKEN=hunter2\n")
    subprocess.run(["git", "add", ".env"], check=True)
    log = tmp_path / "log.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print"]) == 0
    assert "hunter2" not in json.loads(log.read_text())["stdin"]


def test_init_writes_config_and_prints_lazygit_snippet(env, capsys):
    assert cli.main(["init"]) == 0
    assert 'model = "haiku"' in cli.config_path().read_text()
    assert "commitpickle --pause" in capsys.readouterr().out


def test_config_set_and_show(env, capsys):
    assert cli.main(["config", "set", "count", "3"]) == 0
    assert cli.main(["config"]) == 0
    assert "count = 3" in capsys.readouterr().out
