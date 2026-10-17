"""Negative/positive validation battery for the GITHUB_RELEASES Pydantic v2 models.

These tests encode the security conditions 1-5 and 8 of MADR-0016 (issue #323)
at the model validation layer:

- Condition 1: no ``owner`` input exists on any tool model (owner is
  hard-pinned in the client).
- Condition 3: ``tag_name``/``target_commitish`` must be git-ref-safe.
- Condition 4: ``repo`` must match ``^[A-Za-z0-9._-]{1,100}$`` sans ``..``
  and sans leading ``.``.
- Condition 5: ``body`` <= 125000 with control chars rejected except ``\n``
  and ``\t``; ``name`` <= 256 with control chars rejected; ``make_latest``
  enum.
- Condition 8/patch semantics: update inputs carry only provided fields
  (``None`` vs not-provided distinction via ``model_fields_set``), and extra
  fields are always rejected (``extra="forbid"``).
"""
from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from github_releases_mcp.models import CreateReleaseInput, UpdateReleaseInput

REPO_POSITIVE = [
    "coach",
    "opencode-home-config",
    "my_repo",
    "r.x-y",
    "x" * 100,
]
REPO_NEGATIVE = [
    "",
    "x" * 101,
    "has space",
    "re/po",
    ".lead",
    "..",
    "a..b",
    "repo$",
    "café",
    "a\tb",
]

REF_NEGATIVE = [
    "",
    "with space",
    "v1.2.3~rc1",
    "head^1",
    "take:this",
    "what?",
    "ask*ew",
    "bra[ket]",
    "back\\slash",
    "v1\x01x",
    "v1\x7f",
    "a..b",
    "a@{b",
    "/lead",
    "trail/",
    ".lead",
    "trail.",
    "v1.2.3.lock",
]

REF_POSITIVE = [
    "v1.2.3",
    "v1.2.3-rc.1",
    "a-b_c.d",
    "release/v1",
    "user@host-tag",
]


def _invalid(model: type[Any] | Any, **fields: Any) -> None:
    with pytest.raises(ValidationError):
        model(**fields)


class TestCreateReleaseInput:
    def test_minimal_valid_input(self) -> None:
        model = CreateReleaseInput(repo="coach", tag_name="v1.2.3")
        assert model.repo == "coach"
        assert model.tag_name == "v1.2.3"
        assert model.draft is False
        assert model.prerelease is False
        assert model.generate_release_notes is False
        assert model.name is None
        assert model.body is None
        assert model.make_latest is None
        assert model.target_commitish is None

    @pytest.mark.parametrize("repo", REPO_POSITIVE)
    def test_repo_accepts_condition_shape(self, repo: str) -> None:
        assert CreateReleaseInput(repo=repo, tag_name="v1").repo == repo

    @pytest.mark.parametrize("repo", REPO_NEGATIVE)
    def test_repo_rejects_condition_violations(self, repo: str) -> None:
        _invalid(CreateReleaseInput, repo=repo, tag_name="v1")

    @pytest.mark.parametrize("tag", REF_POSITIVE)
    def test_tag_name_accepts_git_ref_safe_values(self, tag: str) -> None:
        assert CreateReleaseInput(repo="coach", tag_name=tag).tag_name == tag

    @pytest.mark.parametrize("tag", REF_NEGATIVE)
    def test_tag_name_rejects_ref_unsafe_values(self, tag: str) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name=tag)

    @pytest.mark.parametrize(
        "ref", ["a..b", "@{x", "/branch", "branch.", "b.lock", "with space", "b\x01"]
    )
    def test_target_commitish_rejects_ref_unsafe_values(self, ref: str) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", target_commitish=ref)

    def test_target_commitish_accepts_git_ref_safe_value(self) -> None:
        model = CreateReleaseInput(repo="coach", tag_name="v1", target_commitish="release/v1")
        assert model.target_commitish == "release/v1"

    @pytest.mark.parametrize("body", ["line\x02", "v\x0bx", "f\x0cx", "a\rb", "del\x7f"])
    def test_body_rejects_control_characters(self, body: str) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", body=body)

    def test_body_accepts_newline_and_tab(self) -> None:
        model = CreateReleaseInput(repo="coach", tag_name="v1", body="line\nnext\ttab")
        assert model.body == "line\nnext\ttab"

    def test_body_rejects_overlong(self) -> None:
        with pytest.raises(ValidationError):
            CreateReleaseInput(repo="coach", tag_name="v1", body="a" * 125_001)

    def test_body_accepts_exact_limit(self) -> None:
        model = CreateReleaseInput(repo="coach", tag_name="v1", body="a" * 125_000)
        assert len(model.body or "") == 125_000

    @pytest.mark.parametrize("name", ["a\nb", "a\tb", "a\x7fb"])
    def test_name_rejects_all_control_characters(self, name: str) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", name=name)

    def test_name_length_limits(self) -> None:
        assert CreateReleaseInput(repo="coach", tag_name="v1", name="a" * 256).name is not None
        with pytest.raises(ValidationError):
            CreateReleaseInput(repo="coach", tag_name="v1", name="a" * 257)

    @pytest.mark.parametrize("value", ["true", "false", "legacy", None])
    def test_make_latest_accepts_enum_or_none(self, value: Any) -> None:
        model = CreateReleaseInput(repo="coach", tag_name="v1", make_latest=value)
        assert model.make_latest == value

    @pytest.mark.parametrize("value", ["True", "latest", "yes", 1])
    def test_make_latest_rejects_non_enum(self, value: Any) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", make_latest=value)

    def test_extra_field_is_rejected(self) -> None:
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", owner="someone")
        _invalid(CreateReleaseInput, repo="coach", tag_name="v1", url="https://api.github.com")


class TestUpdateReleaseInput:
    def test_release_id_required_and_positive(self) -> None:
        model = UpdateReleaseInput(repo="coach", release_id=7)
        assert model.release_id == 7

    @pytest.mark.parametrize("release_id", [0, -1, -7, "x", 1.5, None])
    def test_release_id_rejects_non_positive_or_non_int(self, release_id: Any) -> None:
        _invalid(UpdateReleaseInput, repo="coach", release_id=release_id)

    def test_release_id_coerces_digit_string(self) -> None:
        model = UpdateReleaseInput.model_validate({"repo": "coach", "release_id": "42"})
        assert model.release_id == 42

    def test_release_id_rejects_non_digit_string(self) -> None:
        with pytest.raises(ValidationError):
            UpdateReleaseInput.model_validate({"repo": "coach", "release_id": "12x"})

    def test_optional_fields_default_to_absent(self) -> None:
        model = UpdateReleaseInput(repo="coach", release_id=7)
        assert model.tag_name is None and model.name is None and model.body is None
        assert model.draft is None and model.prerelease is None
        assert model.make_latest is None
        assert model.generate_release_notes is None
        assert model.target_commitish is None

    @pytest.mark.parametrize(
        "tag", ["a..b", "@{x", "/tag", "tag.", "t.lock", "with space", "t\x01"]
    )
    def test_tag_name_validator_applies_when_provided(self, tag: str) -> None:
        _invalid(UpdateReleaseInput, repo="coach", release_id=7, tag_name=tag)

    def test_extra_field_is_rejected(self) -> None:
        _invalid(UpdateReleaseInput, repo="coach", release_id=7, method="DELETE")
        _invalid(UpdateReleaseInput, repo="coach", release_id=7, owner="someone")

    def test_provided_fields_only_in_patch_payload(self) -> None:
        model = UpdateReleaseInput(repo="coach", release_id=7, draft=True)
        payload = model.model_dump(exclude_unset=True, exclude={"repo", "release_id"})
        assert payload == {"draft": True}

    def test_explicit_none_is_provided_and_sent(self) -> None:
        model = UpdateReleaseInput(repo="coach", release_id=7, name=None)
        payload = model.model_dump(exclude_unset=True, exclude={"repo", "release_id"})
        assert payload == {"name": None}

    def test_untouched_optionals_are_not_sent(self) -> None:
        model = UpdateReleaseInput(repo="coach", release_id=7, name="Title")
        payload = model.model_dump(exclude_unset=True, exclude={"repo", "release_id"})
        assert payload == {"name": "Title"}
        assert "body" not in payload and "draft" not in payload

    def test_full_set_sends_every_provided_field(self) -> None:
        model = UpdateReleaseInput(
            repo="coach",
            release_id=7,
            tag_name="v2.0.0",
            name="Title",
            body="Notes",
            draft=True,
            prerelease=False,
            make_latest="false",
            generate_release_notes=False,
            target_commitish="main",
        )
        payload = model.model_dump(exclude_unset=True, exclude={"repo", "release_id"})
        assert set(payload) == {
            "tag_name",
            "name",
            "body",
            "draft",
            "prerelease",
            "make_latest",
            "generate_release_notes",
            "target_commitish",
        }


class TestCondition1NoOwnerInput:
    def test_no_owner_field_on_any_model(self) -> None:
        for model in (CreateReleaseInput, UpdateReleaseInput):
            fields = model.model_fields
            assert "owner" not in fields
            forbidden = {"owner", "token", "url", "header", "authorization", "method"}
            assert not forbidden.intersection(fields), forbidden.intersection(fields)
