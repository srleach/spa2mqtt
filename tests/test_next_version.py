"""Tests for tools/release/next_version.py (the release version calculator)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("next_version", ROOT / "tools" / "release" / "next_version.py")
assert _spec and _spec.loader
nv = importlib.util.module_from_spec(_spec)
sys.modules["next_version"] = nv
_spec.loader.exec_module(nv)

C = nv.Commit


def run(prev: str | None, *commits: object, head: str | None = None, fallback: str = "2.0.0") -> str | None:
    cs = [c if isinstance(c, nv.Commit) else C(str(c)) for c in commits]
    if head is None:
        head = cs[0].subject + "\n\n" + cs[0].body if cs else ""
    result: str | None = nv.next_version(prev, cs, head, fallback)
    return result


# ------------------------------------------------------------------ first release


def test_no_previous_tag_uses_fallback_without_bump() -> None:
    assert run(None, "feat: something", "fix: other") == "2.0.0"


def test_no_previous_tag_ignores_breaking_changes() -> None:
    assert run(None, "feat!: big") == "2.0.0"


def test_no_previous_tag_and_no_commits_still_releases_fallback() -> None:
    assert nv.next_version(None, [], "", "2.0.0") == "2.0.0"


def test_custom_fallback() -> None:
    assert run(None, "chore: x", fallback="3.1.4") == "3.1.4"


def test_bad_fallback_raises() -> None:
    with pytest.raises(ValueError):
        run(None, "fix: x", fallback="2.0")


# ------------------------------------------------------------------ bump levels


@pytest.mark.parametrize(
    "subject",
    ["fix: a bug", "chore: deps", "docs: typo", "refactor(ha): tidy", "plain message", "ci: x", "featured thing"],
)
def test_patch(subject: str) -> None:
    assert run("v2.0.0", subject) == "2.0.1"


@pytest.mark.parametrize("subject", ["feat: new", "feat(esphome): native component", "FEAT: shout", "feat:"])
def test_minor(subject: str) -> None:
    assert run("v2.3.4", subject) == "2.4.0"


@pytest.mark.parametrize("subject", ["feat!: drop v1 config", "fix(protocol)!: change frame", "refactor!: x"])
def test_major_from_bang(subject: str) -> None:
    assert run("v2.3.4", subject) == "3.0.0"


@pytest.mark.parametrize(
    "body",
    [
        "BREAKING CHANGE: config keys renamed",
        "Some text.\n\nBREAKING CHANGE: removed X",
        "BREAKING-CHANGE: hyphen form",
    ],
)
def test_major_from_footer(body: str) -> None:
    assert run("v2.3.4", C("fix: x", body)) == "3.0.0"


def test_breaking_change_mid_sentence_is_not_a_footer() -> None:
    assert run("v2.3.4", C("fix: x", "This is no BREAKING CHANGE at all.")) == "2.3.5"


def test_highest_level_wins() -> None:
    assert run("v1.2.3", "fix: a", "feat: b", "docs: c") == "1.3.0"
    assert run("v1.2.3", "fix: a", "feat: b", "chore!: c") == "2.0.0"


def test_no_commits_since_tag_means_no_release() -> None:
    assert nv.next_version("v2.0.0", [], "whatever", "2.0.0") is None


# ------------------------------------------------------------------ merge commits


def test_merge_subject_is_ignored_but_merged_commits_count() -> None:
    merge = C("Merge pull request #27 from srleach/feature-x", "chore: tidy things")
    assert run("v2.0.0", merge, "feat: new thing", "fix: old thing") == "2.1.0"


def test_merge_subject_alone_is_patch() -> None:
    assert run("v2.0.0", C("Merge branch 'main' into x")) == "2.0.1"


def test_merge_subject_with_feat_word_does_not_count() -> None:
    assert run("v2.0.0", C("Merge pull request #1 from srleach/feat: weird-branch")) == "2.0.1"


def test_merge_body_pr_title_is_classified() -> None:
    merge = C("Merge pull request #28 from srleach/x", "feat(esphome): new component\n\nMore text")
    assert run("v2.0.0", merge, "fix: a") == "2.1.0"


def test_merge_body_breaking_footer_counts() -> None:
    merge = C("Merge pull request #28 from srleach/x", "Title\n\nBREAKING CHANGE: yes")
    assert run("v2.0.0", merge) == "3.0.0"


# ------------------------------------------------------------------ skip marker


def test_skip_release_in_head_subject() -> None:
    assert run("v2.0.0", "feat: x [skip release]") is None


def test_skip_release_in_head_body_of_merge() -> None:
    head = "Merge pull request #3 from a/b\n\ndocs: tweak [skip release]"
    assert run("v2.0.0", C("Merge pull request #3 from a/b", "docs: tweak [skip release]"), head=head) is None


def test_skip_release_case_insensitive() -> None:
    assert run("v2.0.0", "fix: x", head="fix: x [Skip Release]") is None


def test_skip_release_also_blocks_first_release() -> None:
    assert run(None, "fix: x", head="fix: x [skip release]") is None


def test_skip_only_checks_head_message() -> None:
    # An older commit with the marker does not block a later release.
    assert run("v2.0.0", "fix: new", "fix: old [skip release]", head="fix: new") == "2.0.1"


# ------------------------------------------------------------------ tags


def test_latest_tag_picks_highest_strict_semver() -> None:
    tags = ["legacy-v0", "v2.0.0", "v2.10.0", "v2.9.9", "v3.0.0-rc1", "v01.0.0", "x1.0.0"]
    assert nv.latest_tag(tags) == "v2.10.0"


def test_latest_tag_none() -> None:
    assert nv.latest_tag(["legacy-v0", "release"]) is None
    assert nv.latest_tag([]) is None


def test_bad_previous_tag_raises() -> None:
    with pytest.raises(ValueError):
        nv.next_version("legacy-v0", [C("fix: x")], "fix: x")


def test_read_fallback_from_repo_pyproject() -> None:
    assert nv.read_fallback(ROOT / "pyproject.toml") == "2.0.0"


def test_cli_without_git(capsys: pytest.CaptureFixture[str]) -> None:
    assert nv.main(["--previous-tag", "v2.0.0", "--subject", "feat: x", "--fallback", "2.0.0"]) == 0
    assert capsys.readouterr().out.strip() == "2.1.0"
    assert nv.main(["--previous-tag", "v2.0.0", "--subject", "fix: x [skip release]"]) == 0
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ real git


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_against_temporary_git_repo(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def commit(msg: str) -> None:
        git("commit", "--allow-empty", "-q", "-m", msg)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")

    commit("chore: initial")
    git("tag", "legacy-v0")
    assert nv.main(["--git", "--repo", str(tmp_path), "--fallback", "2.0.0"]) == 0
    prev, commits, _ = nv.read_git(tmp_path)
    assert prev is None and len(commits) == 1
    assert nv.next_version(prev, commits, "", "2.0.0") == "2.0.0"

    git("tag", "-a", "v2.0.0", "-m", "v2.0.0")
    prev, commits, head = nv.read_git(tmp_path)
    assert prev == "v2.0.0" and commits == []
    assert nv.next_version(prev, commits, head) is None

    # A feature branch merged with a merge commit.
    git("checkout", "-q", "-b", "feature")
    commit("feat(esphome): add thing\n\nDetails here.")
    commit("fix: small")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #1 from x/feature\n\nAdd thing")
    prev, commits, head = nv.read_git(tmp_path)
    assert prev == "v2.0.0"
    assert {c.subject for c in commits} == {
        "feat(esphome): add thing",
        "fix: small",
        "Merge pull request #1 from x/feature",
    }
    assert nv.next_version(prev, commits, head) == "2.1.0"

    git("tag", "-a", "v2.1.0", "-m", "v2.1.0")
    commit("fix: tidy\n\nBREAKING CHANGE: renamed config key")
    prev, commits, head = nv.read_git(tmp_path)
    assert nv.next_version(prev, commits, head) == "3.0.0"

    commit("docs: notes [skip release]")
    prev, commits, head = nv.read_git(tmp_path)
    assert nv.next_version(prev, commits, head) is None
