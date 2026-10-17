"""Pydantic v2 input models for the GITHUB_RELEASES tools (MADR-0016).

Every tool argument is validated here before it can reach the client:
``extra="forbid"`` rejects unknown fields outright, ``owner`` does not exist
as an input anywhere (MADR-0016 condition 1 — the owner is hard-pinned in
``client.py``), ``repo`` is constrained to a safe charset without traversal
(condition 4), ``tag_name``/``target_commitish`` are git-ref-safe
(condition 3), and free-text fields reject control characters and enforce
the documented length ceilings (condition 5). ``release_id`` is a positive
integer serialized as decimal digits (condition 2).
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_MAX_LENGTH = 100
RELEASE_NAME_MAX_LENGTH = 256
RELEASE_BODY_MAX_LENGTH = 125_000

REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

# Characters forbidden in git refnames by git-check-ref-format(1), narrowed
# to what MADR-0016 condition 3 mandates: the documented ASCII set plus
# control characters.
GIT_REF_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f ~^:?*\\\[]")

# Control characters: body forbids all except line feed (\x0a) and tab
# (\x09); every other text field rejects all of them.
_ALL_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BODY_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _validate_repo(repo: str) -> str:
    """Reject repo names outside the condition-4 charset or with traversal."""
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("repo must match ^[A-Za-z0-9._-]{1,100}$")
    if repo.startswith("."):
        raise ValueError("repo must not start with '.'")
    if ".." in repo:
        raise ValueError("repo must not contain '..'")
    return repo


def _validate_git_ref(ref: str | None) -> str | None:
    """Reject tag/target values that are not git-ref-safe (condition 3)."""
    if ref is None:
        return None
    if not ref:
        raise ValueError("git reference must not be empty")
    if GIT_REF_FORBIDDEN.search(ref):
        raise ValueError(
            "git reference must not contain control characters, space, "
            "~^:?*[ or backslash"
        )
    if ".." in ref:
        raise ValueError("git reference must not contain '..'")
    if "@{" in ref:
        raise ValueError("git reference must not contain '@{'")
    if ref.startswith(("/", ".")) or ref.endswith(("/", ".")):
        raise ValueError("git reference must not start or end with '/' or '.'")
    if ref.endswith(".lock"):
        raise ValueError("git reference must not end with '.lock'")
    return ref


def _validate_plain_text(value: str | None, field_name: str) -> str | None:
    """Reject any control character in a plain-text field (condition 5)."""
    if value is None:
        return None
    if _ALL_CONTROL.search(value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def _validate_body(value: str | None) -> str | None:
    """Reject body control characters except line feed and tab (condition 5)."""
    if value is None:
        return None
    if _BODY_CONTROL.search(value):
        raise ValueError("body must not contain control characters (newline and tab allowed)")
    return value


class CreateReleaseInput(BaseModel):
    """Validated input for the ``create_release`` tool (POST on releases)."""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(
        ...,
        min_length=1,
        max_length=REPO_MAX_LENGTH,
        description=(
            "Repository name under the pinned @fpittelo account — "
            "letters, digits, dot, dash and underscore; no '..' and no "
            "leading dot."
        ),
    )
    tag_name: str = Field(
        ...,
        min_length=1,
        description=(
            "Git tag the release points at (git-ref-safe: no control "
            "characters, no space, no ' ~^:?*[\\', no '..', no '@{', no "
            "lead/trail '/' or '.', no '.lock' suffix)."
        ),
    )
    name: str | None = Field(
        default=None,
        max_length=RELEASE_NAME_MAX_LENGTH,
        description="Human-readable release title (at most 256 characters).",
    )
    body: str | None = Field(
        default=None,
        max_length=RELEASE_BODY_MAX_LENGTH,
        description=(
            "Release notes in Markdown (at most 125000 characters; control "
            "characters rejected except newline and tab)."
        ),
    )
    draft: bool = Field(
        default=False,
        description="Create the release as a draft (not world-readable until published).",
    )
    prerelease: bool = Field(
        default=False,
        description="Mark the release as a pre-release.",
    )
    make_latest: Literal["true", "false", "legacy"] | None = Field(
        default=None,
        description=(
            "Whether this release should be the latest: 'true', 'false' or "
            "'legacy' (default repository behaviour)."
        ),
    )
    generate_release_notes: bool = Field(
        default=False,
        description="Let GitHub generate release notes for the tag.",
    )
    target_commitish: str | None = Field(
        default=None,
        description=(
            "Branch or commit SHA the tag targets (git-ref-safe, same "
            "charset rules as tag_name); omitted when the tag already "
            "exists."
        ),
    )

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        """Apply the repo charset rules (MADR-0016 condition 4)."""
        return _validate_repo(value)

    @field_validator("tag_name", "target_commitish")
    @classmethod
    def validate_git_ref(cls, value: str | None) -> str | None:
        """Apply the git-ref-safe rules (MADR-0016 condition 3)."""
        return _validate_git_ref(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """Apply the plain-text rules (MADR-0016 condition 5)."""
        return _validate_plain_text(value, "name")

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str | None) -> str | None:
        """Apply the body rules (MADR-0016 condition 5)."""
        return _validate_body(value)


class UpdateReleaseInput(BaseModel):
    """Validated input for the ``update_release`` tool (PATCH by release id).

    Only fields explicitly provided by the caller are forwarded in the PATCH
    body (MADR-0016 partial-update mandate): the client distinguishes
    not-provided from ``None`` via ``model_fields_set`` (``exclude_unset``).
    """

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(
        ...,
        min_length=1,
        max_length=REPO_MAX_LENGTH,
        description=(
            "Repository name under the pinned @fpittelo account — "
            "letters, digits, dot, dash and underscore; no '..' and no "
            "leading dot."
        ),
    )
    release_id: int = Field(
        ...,
        ge=1,
        description=(
            "Numeric GitHub release identifier (>= 1); serialized as plain "
            "decimal digits in the PATCH path."
        ),
    )
    tag_name: str | None = Field(
        default=None,
        description=(
            "Replacement git tag (git-ref-safe: no control characters, no "
            "space, no ' ~^:?*[\\', no '..', no '@{', no lead/trail '/' or "
            "'.', no '.lock' suffix)."
        ),
    )
    name: str | None = Field(
        default=None,
        max_length=RELEASE_NAME_MAX_LENGTH,
        description="Replacement release title (at most 256 characters).",
    )
    body: str | None = Field(
        default=None,
        max_length=RELEASE_BODY_MAX_LENGTH,
        description=(
            "Replacement release notes (at most 125000 characters; control "
            "characters rejected except newline and tab)."
        ),
    )
    draft: bool | None = Field(
        default=None,
        description="Set whether the release is a draft.",
    )
    prerelease: bool | None = Field(
        default=None,
        description="Set whether the release is a pre-release.",
    )
    make_latest: Literal["true", "false", "legacy"] | None = Field(
        default=None,
        description=(
            "Whether this release should be the latest: 'true', 'false' or "
            "'legacy'."
        ),
    )
    generate_release_notes: bool | None = Field(
        default=None,
        description="Let GitHub (re)generate release notes for the tag.",
    )
    target_commitish: str | None = Field(
        default=None,
        description=(
            "Branch or commit SHA the tag targets (git-ref-safe, same "
            "charset rules as tag_name)."
        ),
    )

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        """Apply the repo charset rules (MADR-0016 condition 4)."""
        return _validate_repo(value)

    @field_validator("tag_name", "target_commitish")
    @classmethod
    def validate_git_ref(cls, value: str | None) -> str | None:
        """Apply the git-ref-safe rules (MADR-0016 condition 3)."""
        return _validate_git_ref(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """Apply the plain-text rules (MADR-0016 condition 5)."""
        return _validate_plain_text(value, "name")

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str | None) -> str | None:
        """Apply the body rules (MADR-0016 condition 5)."""
        return _validate_body(value)


def create_payload(params: CreateReleaseInput) -> dict[str, Any]:
    """Build the POST body — validated data only; repo stays in the path."""
    return params.model_dump(exclude_unset=True, exclude={"repo"})


def update_payload(params: UpdateReleaseInput) -> dict[str, Any]:
    """Build the PATCH body — only explicitly provided fields (condition 8)."""
    return params.model_dump(exclude_unset=True, exclude={"repo", "release_id"})
