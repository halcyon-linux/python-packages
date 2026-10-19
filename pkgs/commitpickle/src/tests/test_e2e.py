"""End to end with a stub `opencode` and a throwaway git repository."""

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
args = sys.argv[1:]
if args and args[0] == "--version":
    print(os.environ.get("STUB_VERSION", "opencode v2.0.32"))
    sys.exit(0)
if args and args[0] == "models":
    if os.environ.get("STUB_LOG"):
        with open(os.environ["STUB_LOG"], "w", encoding="utf-8") as fh:
            json.dump({"argv": args}, fh)
    print("opencode/ok-free")
    print("opencode/big-pickle")
    print("opencode/gpt-5")
    sys.exit(0)
model = args[args.index("--model") + 1]
if "broken" in model:
    sys.stderr.write("boom\\n")
    sys.exit(1)
stdin = sys.stdin.read()
if os.environ.get("STUB_LOG"):
    with open(os.environ["STUB_LOG"], "w", encoding="utf-8") as fh:
        json.dump({"argv": args, "stdin": stdin, "cwd": os.getcwd()}, fh)
mode = os.environ.get("STUB_MODE", "")
if mode == "fallback":
    print('! agent "commitpickle" not found. Falling back to default agent')
tool = {"type": "tool_use", "part": {"type": "tool", "tool": "bash", "state": {"status": "%s"}}}
if mode == "tool-ran":
    tool["part"]["state"]["status"] = "completed"
    print(json.dumps(tool))
if mode == "tool-denied":
    tool["part"]["state"]["status"] = "error"
    print(json.dumps(tool))
if mode == "api-error":
    err = {"name": "APIError", "data": {"message": "Rate limit reached for this free model"}}
    print(json.dumps({"type": "error", "error": err}))
    sys.exit(1)
if mode == "v2-api-error":
    err = {"type": "provider.no-route", "message": "Model unavailable: opencode/ok-free"}
    print(json.dumps({"type": "error", "error": err}))
    sys.exit(1)
if mode == "agent-missing":
    err = {"type": "unknown", "message": 'Agent not found: "commitpickle"'}
    print(json.dumps({"type": "error", "error": err}))
    sys.exit(1)
reply = open(os.environ["STUB_REPLY"], encoding="utf-8").read()
print("WARNING: banner")
print(json.dumps({"type": "text", "part": {"text": reply}}))
"""

GOOD = (
    "```\nfeat(auth): add token refresh.\n\nRefresh tokens before expiry so sessions survive.\n```"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "opencode"
    stub.write_text(STUB.replace("PYTHON", sys.executable, 1), encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    reply = tmp_path / "reply.txt"
    reply.write_text(GOOD, encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("COMMITPICKLE_MODEL", raising=False)
    monkeypatch.delenv("STUB_MODE", raising=False)
    monkeypatch.delenv("STUB_LOG", raising=False)
    monkeypatch.delenv("STUB_VERSION", raising=False)
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


# --------------------------------------------------------------------------- basic flows


def test_print_falls_back_past_broken_model_and_cleans(env, capsys):
    repo, _ = env
    stage(repo)
    rc = cli.main(["--print", "-m", "opencode/broken-free,opencode/ok-free"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == (
        "feat(auth): add token refresh\n\nRefresh tokens before expiry so sessions survive.\n"
    )
    assert (cli.opencode_agent_path()).exists()  # agent auto-created


def test_yes_commits(env):
    repo, _ = env
    stage(repo)
    assert cli.main(["--yes", "-m", "opencode/ok-free"]) == 0
    log = git_out("log", "-1", "--format=%s%n%b")
    assert log.startswith("feat(auth): add token refresh")
    assert "sessions survive" in log


def test_yes_refuses_invalid_message(env):
    repo, reply = env
    reply.write_text("Updated some stuff", encoding="utf-8")
    stage(repo)
    assert cli.main(["--yes", "-m", "opencode/ok-free"]) == 1
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], check=False, capture_output=True
    )
    assert head.returncode != 0  # nothing committed


def test_nothing_staged_and_not_a_repo(env, tmp_path, monkeypatch, caplog):
    assert cli.main(["--print"]) == 1
    assert "nothing staged" in caplog.text
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--print"]) == 1
    assert "not inside a git repository" in caplog.text


def test_git_failure_is_not_mistaken_for_staged_changes(env, caplog):
    repo, _ = env
    stage(repo)
    (repo / ".git" / "index").write_bytes(b"not an index")
    assert cli.main(["--print"]) == 1
    assert "git diff --cached failed" in caplog.text


def test_all_models_fail(env, caplog):
    repo, _ = env
    stage(repo)
    assert cli.main(["--print", "-m", "opencode/broken-free"]) == 1
    assert "all models failed" in caplog.text


def test_interactive_commit_edit_regenerate_quit(env, monkeypatch, capsys):
    repo, _ = env
    stage(repo)
    answers = iter(["r", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["-m", "opencode/ok-free"]) == 0
    assert "Aborted." in capsys.readouterr().out

    monkeypatch.setattr("builtins.input", lambda _prompt="": "")  # Enter = commit
    assert cli.main(["-m", "opencode/ok-free", "--", "--no-verify"]) == 0
    assert git_out("log", "-1", "--format=%s").strip() == "feat(auth): add token refresh"


def test_non_interactive_without_flags_is_rejected(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.main([]) == 1
    assert "not running in a terminal" in caplog.text


def test_init_and_config_commands(env, capsys):
    assert cli.main(["init"]) == 0
    out = capsys.readouterr().out
    assert "commitpickle --pause" in out and cli.config_path().exists()
    assert cli.main(["config", "set", "models", "opencode/a,opencode/b"]) == 0
    assert cli.main(["config"]) == 0
    shown = capsys.readouterr().out
    assert json.dumps(["opencode/a", "opencode/b"]) in shown
    assert cli.main(["config", "set", "bogus", "1"]) == 1
    assert not list(cli.config_path().parent.glob("*.tmp"))  # atomic write left no debris


def test_config_error_names_the_file(env, caplog):
    cli.config_path().parent.mkdir(parents=True)
    cli.config_path().write_text("timeout = 0\n", encoding="utf-8")
    assert cli.main(["--print"]) == 1
    assert str(cli.config_path()) in caplog.text


# --------------------------------------------------------------------------- privacy


def test_prompt_goes_on_stdin_and_runs_outside_the_repo(env, monkeypatch):
    repo, _ = env
    stage(repo)
    log = repo.parent / "stub.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print", "-m", "opencode/ok-free", "the why"]) == 0
    seen = json.loads(log.read_text(encoding="utf-8"))
    assert "+two" in seen["stdin"] and "the why" in seen["stdin"]
    assert "two" not in " ".join(seen["argv"])  # nothing sensitive in `ps`
    assert seen["argv"][-1] == cli.PROMPT_ARG
    assert "--dir" not in seen["argv"]
    workdir = cli.neutral_workdir()
    assert workdir is not None and os.path.samefile(seen["cwd"], workdir)
    assert not os.path.samefile(seen["cwd"], repo)
    assert stat.S_IMODE(workdir.stat().st_mode) & 0o077 == 0  # private


def test_attach_mode_uses_server_and_repo_cwd_on_v2(env, monkeypatch):
    repo, _ = env
    stage(repo)
    cli.save_config_value("attach", "http://127.0.0.1:4096")
    log = repo.parent / "stub.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 0
    seen = json.loads(log.read_text(encoding="utf-8"))
    assert seen["argv"][seen["argv"].index("--server") + 1] == "http://127.0.0.1:4096"
    assert "--attach" not in seen["argv"] and "--dir" not in seen["argv"]
    assert os.path.samefile(seen["cwd"], repo)


def test_attach_mode_keeps_v1_flags_on_opencode_v1(env, monkeypatch):
    repo, _ = env
    stage(repo)
    cli.save_config_value("attach", "http://127.0.0.1:4096")
    monkeypatch.setenv("STUB_VERSION", "opencode 1.18.18")
    log = repo.parent / "stub.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 0
    seen = json.loads(log.read_text(encoding="utf-8"))
    assert seen["argv"][seen["argv"].index("--attach") + 1] == "http://127.0.0.1:4096"
    assert os.path.samefile(seen["argv"][seen["argv"].index("--dir") + 1], repo)


def test_lock_files_and_secrets_stay_out_of_the_diff_but_in_the_file_list(env):
    repo, _ = env
    files = {
        "web/package-lock.json": "{}",
        "svc/go.sum": "h1:x",
        "yarn.lock": "x",
        ".env": "TOKEN=hunter2",
        "config/.env.local": "TOKEN=hunter2",
        "deploy/server.pem": "-----BEGIN PRIVATE KEY-----",
        "web/app.js": "console.log('kept')",
    }
    for name, content in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content + "\n")
    subprocess.run(["git", "add", "-A"], check=True)
    changes = cli.collect_staged(cli.DEFAULT_MAX_DIFF)
    assert "console.log('kept')" in changes.diff
    for leaked in ("hunter2", "PRIVATE KEY", "h1:x"):
        assert leaked not in changes.diff
    assert "diff --git a/web/package-lock.json" not in changes.diff
    for name in files:
        assert name.split("/")[-1] in changes.stat  # still listed for context


def test_only_excluded_files_changed_says_so(env):
    repo, _ = env
    (repo / ".env").write_text("TOKEN=hunter2\n")
    subprocess.run(["git", "add", ".env"], check=True)
    changes = cli.collect_staged(cli.DEFAULT_MAX_DIFF)
    assert "diff omitted" in changes.diff and "hunter2" not in changes.diff


# --------------------------------------------------------------------------- containment


def test_agent_denies_everything_by_default(env):
    assert cli.WILDCARD_DENY_RE.search(cli.AGENT_FILE_CONTENT)
    assert not cli.WILDCARD_DENY_RE.search(cli._LEGACY_AGENT_V1)
    assert cli.AGENT_FILE_CONTENT.startswith("---\n")  # frontmatter must open the file


def test_legacy_agent_file_is_upgraded_in_place(env):
    path = cli.opencode_agent_path()
    path.parent.mkdir(parents=True)
    path.write_text(cli._LEGACY_AGENT_V1, encoding="utf-8")
    assert cli.ensure_agent() == path
    assert path.read_text(encoding="utf-8") == cli.AGENT_FILE_CONTENT


def test_hand_edited_agent_is_kept_and_unsafe_ones_are_flagged(env, caplog):
    path = cli.opencode_agent_path()
    path.parent.mkdir(parents=True)
    unsafe = "---\nmode: primary\npermission:\n  bash: deny\n---\nmine\n"
    path.write_text(unsafe, encoding="utf-8")
    assert cli.ensure_agent() == path
    assert path.read_text(encoding="utf-8") == unsafe  # never clobbered
    assert "edited by hand" in caplog.text

    caplog.clear()
    safe = '---\nmode: primary\npermission:\n  "*": deny\n---\nmine\n'
    path.write_text(safe, encoding="utf-8")
    assert cli.ensure_agent() == path
    assert path.read_text(encoding="utf-8") == safe
    assert "edited by hand" not in caplog.text


def test_init_force_resets_a_hand_edited_agent(env):
    path = cli.opencode_agent_path()
    path.parent.mkdir(parents=True)
    path.write_text("mine\n", encoding="utf-8")
    assert cli.main(["init", "--force"]) == 0
    assert path.read_text(encoding="utf-8") == cli.AGENT_FILE_CONTENT


def test_unwritable_agent_is_fatal_not_a_warning(env, tmp_path, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so mkdir beneath it fails")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(blocker / "sub"))
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 1
    assert "tool-less" in caplog.text
    assert cli.main(["init"]) == 1


def test_fallback_to_default_agent_is_fatal(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "fallback")
    assert cli.main(["--print", "-m", "opencode/ok-free,opencode/ok2-free"]) == 1
    assert "fell back to its default agent" in caplog.text


def test_a_tool_that_actually_ran_is_fatal_but_a_denied_one_is_not(
    env, monkeypatch, caplog, capsys
):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "tool-ran")
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 1
    assert "ran tool(s) bash" in caplog.text

    monkeypatch.setenv("STUB_MODE", "tool-denied")
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 0
    assert capsys.readouterr().out.startswith("feat(auth)")


# --------------------------------------------------------------------------- commit behaviour


def test_hash_lines_survive_commit_cleanup_config(env):
    repo, reply = env
    subprocess.run(["git", "config", "commit.cleanup", "strip"], check=True)
    reply.write_text("fix(db): close pool\n\n#412 is the tracking issue\nBody.\n", encoding="utf-8")
    stage(repo)
    assert cli.main(["--yes", "-m", "opencode/ok-free"]) == 0
    assert "#412 is the tracking issue" in git_out("log", "-1", "--format=%B")


@pytest.mark.parametrize(
    ("reply_text", "expect_edit"),
    [(GOOD, False), ("Updated some stuff", True)],
)
def test_enter_commits_valid_drafts_but_edits_invalid_ones(
    env, monkeypatch, capsys, reply_text, expect_edit
):
    repo, reply = env
    reply.write_text(reply_text, encoding="utf-8")
    stage(repo)
    calls = []
    monkeypatch.setattr(cli, "git_commit", lambda _msg, *, edit, extra: calls.append(edit) or 0)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["-m", "opencode/ok-free"]) == 0
    assert calls == [expect_edit]
    assert ("[E]dit" in prompts[0]) is expect_edit
    assert ("[C]ommit" in prompts[0]) is not expect_edit
    capsys.readouterr()


# --------------------------------------------------------------------------- subcommands


def test_models_lists_free_models_only(env, capsys, monkeypatch):
    log = env[0].parent / "models.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    assert cli.main(["models"]) == 0
    out = capsys.readouterr().out
    assert "opencode/ok-free" in out and "gpt-5" not in out
    # opencode v2 rejects a provider positional: the argv must be just `models`
    assert json.loads(log.read_text(encoding="utf-8"))["argv"] == ["models"]


def test_models_timeout_and_missing_binary_are_clean_errors(env, monkeypatch, caplog):
    def hang(*_a, **_k):
        raise subprocess.TimeoutExpired("opencode", 60)

    monkeypatch.setattr(cli.subprocess, "run", hang)
    assert cli.main(["models"]) == 1
    assert "timed out" in caplog.text


def test_subcommands_reject_unknown_arguments(env):
    with pytest.raises(SystemExit):
        cli.main(["init", "--forcee"])
    with pytest.raises(SystemExit):
        cli.main(["models", "--bogus"])


def test_provider_error_message_is_shown_instead_of_raw_json(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "api-error")
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 1
    assert "Rate limit reached for this free model" in caplog.text
    assert '{"type"' not in caplog.text


def test_v2_provider_error_message_is_shown_instead_of_raw_json(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "v2-api-error")
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 1
    assert "Model unavailable: opencode/ok-free" in caplog.text
    assert '{"type"' not in caplog.text


def test_v2_agent_not_found_is_fatal_with_a_clear_message(env, monkeypatch, caplog):
    repo, _ = env
    stage(repo)
    monkeypatch.setenv("STUB_MODE", "agent-missing")
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 1
    assert "could not find the 'commitpickle' agent" in caplog.text


def test_a_reply_that_quotes_the_fallback_warning_is_not_mistaken_for_it(env, monkeypatch, capsys):
    repo, reply = env
    reply.write_text(
        "fix(agent): abort on fallback\n\nAbort when OpenCode prints "
        "'Falling back to default agent'.\n",
        encoding="utf-8",
    )
    stage(repo)
    assert cli.main(["--print", "-m", "opencode/ok-free"]) == 0
    assert "Falling back to default agent" in capsys.readouterr().out
