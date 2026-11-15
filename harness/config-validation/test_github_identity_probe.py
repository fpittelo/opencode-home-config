#!/usr/bin/env python3
"""Regression tests for harness/probes/verify-github-identities.py (#423 AC3).

stdlib unittest only: no pytest, no third-party imports, no network. Each case
runs the probe as a subprocess against a loopback ``http.server`` stand-in for
GitHub's ``/user`` endpoint, driven by dummy tokens injected through the probe's
environment variables.

Why this suite exists (#423): the ``GITHUB_CODE_REVIEWER`` MCP credential
resolved to ``@fpittelo`` — the PR author — so separation of duties was void at
runtime while every identity read reported success. A login-only comparison
would have declared the broken state healthy, so the probe must assert the
expected **login AND id** per namespace, and must fail closed on a missing
token, a non-loopback endpoint override, and any unexpected identity.

Run:
    python3 harness/config-validation/test_github_identity_probe.py
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "harness" / "probes" / "verify-github-identities.py"
GUIDE = REPO_ROOT / "docs" / "Admin-and-User-Guide.md"

# Dummy credentials: never real tokens, never printed.
OWNER_TOKEN = "dummy-owner"
REVIEWER_TOKEN = "dummy-reviewer"
DRIFTED_TOKEN = "dummy-drifted"

OWNER_LOGIN = "fpittelo"
OWNER_ID = 3135901
REVIEWER_LOGIN = "devfpittelo"
REVIEWER_ID = 327061373
# Same login as the machine account, different id: the exact #423 bug class a
# login-only check would pass.
DRIFTED_ID = 999999999

PROBE_ENV_VARS = (
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GITHUB_TOKEN_CODE_REVIEWER",
    "GITHUB_API_BASE_URL",
    "SHELLOPTS",
)


def documented(lines: list[str], namespace: str, login: str, user_id: int) -> bool:
    """True when some line documents namespace -> login -> id, in that order."""
    namespace_token = f"`{namespace}`"
    login_token = f"`{login}`"
    id_token = f"`{user_id}`"
    for line in lines:
        start = line.find(namespace_token)
        if start < 0:
            continue
        login_at = line.find(login_token, start + len(namespace_token))
        if login_at < 0:
            continue
        if line.find(id_token, login_at + len(login_token)) >= 0:
            return True
    return False


class FakeGitHub:
    """Loopback stand-in for ``GET /user``, dispatching on the bearer token."""

    def __init__(self, identities: dict[str, tuple[str, int]]) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/user":
                    self.send_error(404)
                    return
                header = self.headers.get("Authorization", "")
                token = header[len("Bearer ") :] if header.startswith("Bearer ") else ""
                identity = identities.get(token)
                if identity is None:
                    self.send_error(401)
                    return
                body = json.dumps({"login": identity[0], "id": identity[1]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass  # silence: captured stdout is asserted on by the leak case

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class ProbeTestCase(unittest.TestCase):
    """Shared harness: loopback fake, hermetic HOME, stripped real credentials."""

    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = home.name

    def fake_github(
        self, identities: dict[str, tuple[str, int]] | None = None
    ) -> FakeGitHub:
        server = FakeGitHub(
            identities
            if identities is not None
            else {
                OWNER_TOKEN: (OWNER_LOGIN, OWNER_ID),
                REVIEWER_TOKEN: (REVIEWER_LOGIN, REVIEWER_ID),
            }
        )
        self.addCleanup(server.close)
        return server

    def run_probe(self, env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in PROBE_ENV_VARS}
        env["HOME"] = self.home  # empty HOME: no daemon-freshness source material
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(PROBE)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )

    def passing_env(self, server: FakeGitHub, reviewer_token: str) -> dict[str, str]:
        return {
            "GITHUB_PERSONAL_ACCESS_TOKEN": OWNER_TOKEN,
            "GITHUB_TOKEN_CODE_REVIEWER": reviewer_token,
            "GITHUB_API_BASE_URL": server.url,
        }


class ExpectedIdentitiesPass(ProbeTestCase):
    def test_all_namespaces_pass_against_expected_identities(self) -> None:
        server = self.fake_github()
        result = self.run_probe(self.passing_env(server, REVIEWER_TOKEN))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"GITHUB: {OWNER_LOGIN}/{OWNER_ID} PASS", result.stdout)
        self.assertIn(
            f"GITHUB_CODE_REVIEWER: {REVIEWER_LOGIN}/{REVIEWER_ID} PASS", result.stdout
        )
        self.assertIn(f"GITHUB_SECURITY: {OWNER_LOGIN}/{OWNER_ID} PASS", result.stdout)
        self.assertIn("SUMMARY: 3/3 namespaces PASS", result.stdout)


class FailClosed(ProbeTestCase):
    def test_reviewer_slot_holding_the_owner_token_fails(self) -> None:
        """#423 regression: the reviewer namespace resolving to the author."""
        server = self.fake_github()
        result = self.run_probe(self.passing_env(server, OWNER_TOKEN))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"GITHUB_CODE_REVIEWER: {OWNER_LOGIN}/{OWNER_ID} FAIL", result.stdout
        )
        self.assertIn("SUMMARY: 2/3 namespaces PASS", result.stdout)

    def test_wrong_id_with_the_right_login_fails(self) -> None:
        """Asserting the id, not merely the login, is the #423 fix."""
        server = self.fake_github(
            {
                OWNER_TOKEN: (OWNER_LOGIN, OWNER_ID),
                REVIEWER_TOKEN: (REVIEWER_LOGIN, DRIFTED_ID),
            }
        )
        result = self.run_probe(self.passing_env(server, REVIEWER_TOKEN))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"GITHUB_CODE_REVIEWER: {REVIEWER_LOGIN}/{DRIFTED_ID} FAIL", result.stdout
        )

    def test_missing_token_fails_closed(self) -> None:
        server = self.fake_github()
        env = self.passing_env(server, REVIEWER_TOKEN)
        del env["GITHUB_TOKEN_CODE_REVIEWER"]
        result = self.run_probe(env)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GITHUB_CODE_REVIEWER: TOKEN MISSING", result.stdout)

    def test_non_loopback_endpoint_override_is_refused(self) -> None:
        server = self.fake_github()
        for hostile in ("https://api.example.invalid", "http://198.51.100.7:8080"):
            with self.subTest(endpoint=hostile):
                env = self.passing_env(server, REVIEWER_TOKEN)
                env["GITHUB_API_BASE_URL"] = hostile
                result = self.run_probe(env)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("loopback", (result.stdout + result.stderr).lower())

    def test_localhost_loopback_override_is_accepted(self) -> None:
        server = self.fake_github()
        env = self.passing_env(server, REVIEWER_TOKEN)
        env["GITHUB_API_BASE_URL"] = server.url.replace("127.0.0.1", "localhost")
        result = self.run_probe(env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shell_xtrace_refuses_to_run(self) -> None:
        """A traced shell can echo environment exports into logs (#423/MADR-0010)."""
        server = self.fake_github()
        env = self.passing_env(server, REVIEWER_TOKEN)
        env["SHELLOPTS"] = "braceexpand:hashall:xtrace"
        result = self.run_probe(env)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("xtrace", result.stderr.lower())


class NoTokenLeak(ProbeTestCase):
    def test_output_never_contains_a_token(self) -> None:
        server = self.fake_github()
        passing = self.run_probe(self.passing_env(server, REVIEWER_TOKEN))
        failing = self.run_probe(self.passing_env(server, OWNER_TOKEN))
        for label, result in (("passing", passing), ("failing", failing)):
            with self.subTest(run=label):
                output = result.stdout + result.stderr
                for token in (OWNER_TOKEN, REVIEWER_TOKEN):
                    self.assertNotIn(token, output)


class SingleSourceAndDocsParity(unittest.TestCase):
    def load_probe(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location("verify_github_identities", PROBE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_expected_map_is_single_sourced_and_matches_the_admin_guide(self) -> None:
        expected = self.load_probe().EXPECTED_IDENTITIES
        self.assertEqual(
            set(expected), {"GITHUB", "GITHUB_CODE_REVIEWER", "GITHUB_SECURITY"}
        )
        self.assertEqual(
            expected["GITHUB_CODE_REVIEWER"], (REVIEWER_LOGIN, REVIEWER_ID)
        )
        self.assertEqual(expected["GITHUB"], expected["GITHUB_SECURITY"])
        self.assertEqual(expected["GITHUB"], (OWNER_LOGIN, OWNER_ID))

        source = PROBE.read_text(encoding="utf-8")
        guide_lines = GUIDE.read_text(encoding="utf-8").splitlines()
        for namespace, (login, user_id) in expected.items():
            with self.subTest(namespace=namespace):
                # Single source: each literal declared exactly once in the probe.
                self.assertEqual(source.count(f'"{login}"'), 1)
                self.assertEqual(source.count(str(user_id)), 1)
                # Docs parity: the admin guide documents the same pair.
                self.assertTrue(
                    documented(guide_lines, namespace, login, user_id),
                    "docs/Admin-and-User-Guide.md must document "
                    f"{namespace} -> {login}/{user_id}",
                )


if __name__ == "__main__":
    unittest.main()
