import contextlib
import importlib.util
import io
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPOSITORY_ROOT / "scripts" / "update-formula.py"
COMMITTED_FORMULA_PATH = REPOSITORY_ROOT / "Formula" / "bobi.rb"

DEFAULT_SDIST_URL = "https://files.pythonhosted.org/bobi-default.tar.gz"
DEFAULT_SDIST_SHA256 = "1" * 64
CANDIDATE_SDIST_URL = "https://artifacts.example.test/bobi-candidate.tar.gz"
CANDIDATE_SDIST_SHA256 = "2" * 64
HOSTILE_SDIST_URL = (
    "https://artifacts.example.test/bobi.tar.gz"
    "#{system('touch /tmp/formula-injection')}"
)


def load_generator():
    spec = importlib.util.spec_from_file_location("update_formula", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load generator at {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UpdateFormulaTests(unittest.TestCase):
    def setUp(self):
        self.generator = load_generator()

    def render_formula(self, *arguments):
        lookups = []

        def fake_get_pypi_sdist(name, version):
            lookups.append((name, version))
            if name == "bobi":
                return DEFAULT_SDIST_URL, DEFAULT_SDIST_SHA256
            return (
                f"https://files.pythonhosted.org/{name}-{version}.tar.gz",
                "3" * 64,
            )

        stdout = io.StringIO()
        with (
            mock.patch.object(
                self.generator,
                "get_installed_packages",
                return_value={"setuptools": "80.0.0"},
            ),
            mock.patch.object(
                self.generator,
                "get_pypi_sdist",
                side_effect=fake_get_pypi_sdist,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.generator.main(["9.9.9", *arguments])

        return stdout.getvalue(), lookups

    def test_uses_pypi_sdist_by_default(self):
        formula, lookups = self.render_formula()

        self.assertIn(f'url "{DEFAULT_SDIST_URL}"', formula)
        self.assertIn(f'sha256 "{DEFAULT_SDIST_SHA256}"', formula)
        self.assertIn(("bobi", "9.9.9"), lookups)

    def test_candidate_sdist_override_replaces_pypi_source(self):
        formula, lookups = self.render_formula(
            "--sdist-url",
            CANDIDATE_SDIST_URL,
            "--sdist-sha256",
            CANDIDATE_SDIST_SHA256,
        )

        self.assertIn(f'url "{CANDIDATE_SDIST_URL}"', formula)
        self.assertIn(f'sha256 "{CANDIDATE_SDIST_SHA256}"', formula)
        self.assertIn('version "9.9.9"', formula)
        self.assertLess(
            formula.index('version "9.9.9"'),
            formula.index(f'sha256 "{CANDIDATE_SDIST_SHA256}"'),
        )
        self.assertNotIn(("bobi", "9.9.9"), lookups)

    def test_candidate_sdist_url_is_safe_as_ruby_source(self):
        formula, _ = self.render_formula(
            "--sdist-url",
            HOSTILE_SDIST_URL,
            "--sdist-sha256",
            CANDIDATE_SDIST_SHA256,
        )

        escaped_payload = r"\#{system('touch /tmp/formula-injection')}"
        self.assertIn(escaped_payload, formula)
        self.assertNotIn(
            "#{system('touch /tmp/formula-injection')}",
            formula.replace(escaped_payload, ""),
        )

    def test_candidate_sdist_url_requires_sha256(self):
        with self.assertRaises(SystemExit) as raised:
            self.render_formula("--sdist-url", CANDIDATE_SDIST_URL)

        self.assertNotEqual(0, raised.exception.code)

    def test_candidate_sdist_sha256_requires_url(self):
        with self.assertRaises(SystemExit) as raised:
            self.render_formula("--sdist-sha256", CANDIDATE_SDIST_SHA256)

        self.assertNotEqual(0, raised.exception.code)

    def test_candidate_sdist_sha256_must_be_hexadecimal(self):
        with self.assertRaises(SystemExit) as raised:
            self.render_formula(
                "--sdist-url",
                CANDIDATE_SDIST_URL,
                "--sdist-sha256",
                "not-a-digest",
            )

        self.assertNotEqual(0, raised.exception.code)

    def test_declares_supported_node_runtime_dependency(self):
        formula, _ = self.render_formula()

        self.assertIn(
            '  depends_on "node"\n',
            formula,
            "generated formula must use Homebrew's supported Node runtime",
        )

    def test_replaces_help_only_test_with_event_server_health_smoke(self):
        formula, _ = self.render_formula()
        test_body = formula.partition("  test do")[2]

        self.assertNotIn("bobi --help", test_body)
        self.assertIn("from bobi.events.server import ensure_running", test_body)
        self.assertIn("status = ensure_running(", test_body)
        self.assertIn(
            'Net::HTTP.get(URI("http://127.0.0.1:#{port}/health"))',
            test_body,
        )
        self.assertIn('assert_equal "started", startup.fetch("status")', test_body)
        self.assertIn('assert_equal "ok", health.fetch("status")', test_body)
        self.assertIn('assert_equal "local", health.fetch("mode")', test_body)

    def test_health_smoke_makes_npm_unusable(self):
        formula, _ = self.render_formula()
        test_body = formula.partition("  test do")[2]

        self.assertIn('(npm_shim_dir/"npm").write', test_body)
        self.assertIn("exit 97", test_body)
        self.assertIn('ENV.prepend_path "PATH", npm_shim_dir', test_body)
        self.assertIn("refute_path_exists npm_trace", test_body)

    def test_health_smoke_checks_installed_package_immutability(self):
        formula, _ = self.render_formula()
        test_body = formula.partition("  test do")[2]

        self.assertIn(
            'site_packages = libexec/"lib/python3.13/site-packages/bobi"',
            test_body,
        )
        self.assertIn("Digest::SHA256.file", test_body)
        self.assertIn("path.stat.mode", test_body)
        self.assertIn("path.stat.size", test_body)
        self.assertIn("before = snapshot.call", test_body)
        self.assertIn("assert_equal before, snapshot.call", test_body)

    def test_health_smoke_always_stops_embedded_server(self):
        formula, _ = self.render_formula()
        test_body = formula.partition("  test do")[2]

        self.assertIn("    ensure\n", test_body)
        self.assertIn('Process.kill("TERM", -pid)', test_body)
        self.assertIn('Process.kill("KILL", -pid)', test_body)
        self.assertIn("if pid.positive?", test_body)

    @unittest.skipUnless(shutil.which("ruby"), "Ruby is not installed")
    def test_generated_formula_has_valid_ruby_syntax(self):
        formula, _ = self.render_formula()

        result = subprocess.run(
            ["ruby", "-c"],
            input=formula,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_generator_does_not_modify_committed_formula(self):
        formula_before = COMMITTED_FORMULA_PATH.read_bytes()

        self.render_formula(
            "--sdist-url",
            CANDIDATE_SDIST_URL,
            "--sdist-sha256",
            CANDIDATE_SDIST_SHA256,
        )

        self.assertEqual(formula_before, COMMITTED_FORMULA_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
