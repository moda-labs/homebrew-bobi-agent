import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BOTTLE_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "tests.yml"


def yaml_block(workflow, header):
    lines = workflow.splitlines(keepends=True)
    try:
        start = next(
            index for index, line in enumerate(lines) if line.rstrip() == header
        )
    except StopIteration as error:
        raise AssertionError(f"Missing YAML block: {header}") from error

    indentation = len(header) - len(header.lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        line_indentation = len(line) - len(line.lstrip())
        if line_indentation <= indentation:
            end = index
            break
    return "".join(lines[start:end])


def yaml_run_script(workflow, header):
    block = yaml_block(workflow, header)
    lines = block.splitlines()
    try:
        run_index = next(
            index for index, line in enumerate(lines) if line.strip() == "run: |"
        )
    except StopIteration as error:
        raise AssertionError(f"Missing run script: {header}") from error

    script_indentation = len(lines[run_index]) - len(lines[run_index].lstrip()) + 2
    return "\n".join(
        line[script_indentation:] if line else ""
        for line in lines[run_index + 1 :]
    )


class BottleWorkflowTests(unittest.TestCase):
    def test_pull_requests_run_generator_contract_tests(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        generator_job = yaml_block(workflow, "  generator-tests:")

        self.assertIn("\n  pull_request:\n", workflow)
        self.assertIn("ruby/setup-ruby@v1", generator_job)
        self.assertIn(
            "python3 -m unittest discover -s tests -v",
            generator_job,
        )

    def test_workflow_can_render_unpublished_candidate_sdist(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        render_step = yaml_block(
            workflow,
            "      - name: Render unpublished candidate formula",
        )

        self.assertIn("candidate_sdist_url:", workflow)
        self.assertIn("candidate_sdist_sha256:", workflow)
        self.assertIn("shasum -a 256", render_step)
        self.assertIn(
            'if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then',
            render_step,
        )
        self.assertLess(
            render_step.index("candidate sdist SHA-256 mismatch"),
            render_step.index('-m pip install "$CANDIDATE_ARCHIVE"'),
        )
        self.assertIn("scripts/update-formula.py", render_step)
        self.assertIn("--sdist-url", render_step)
        self.assertIn("--sdist-sha256", render_step)

    def test_candidate_formula_replaces_formula_in_tapped_checkout(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        setup_header = "      - name: Set up Homebrew"
        render_header = "      - name: Render unpublished candidate formula"
        render_step = yaml_block(workflow, render_header)

        self.assertLess(workflow.index(setup_header), workflow.index(render_header))
        self.assertIn(
            'TAP_FORMULA="$(brew --repo moda-labs/bobi-agent)/Formula/bobi.rb"',
            render_step,
        )
        self.assertIn('> "$TAP_FORMULA"', render_step)
        self.assertNotIn("> Formula/bobi.rb", render_step)
        self.assertIn(
            "grep -Fq 'from bobi.events.server import ensure_running'",
            render_step,
        )

    def test_candidate_checksum_mismatch_stops_before_install(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        render_script = yaml_run_script(
            workflow,
            "      - name: Render unpublished candidate formula",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            runner_temp = Path(temporary_directory)
            candidate = runner_temp / "candidate.tar.gz"
            candidate.write_bytes(b"candidate bytes")
            environment = os.environ.copy()
            environment.update(
                {
                    "CANDIDATE_SDIST_URL": candidate.as_uri(),
                    "CANDIDATE_SDIST_SHA256": "0" * 64,
                    "RUNNER_TEMP": str(runner_temp),
                }
            )

            result = subprocess.run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-e",
                    "-o",
                    "pipefail",
                    "-c",
                    render_script,
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("candidate sdist SHA-256 mismatch", result.stdout)
            self.assertFalse((runner_temp / "formula-generator").exists())

    def test_candidate_build_has_no_persisted_checkout_credential(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()

        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertEqual(2, workflow.count("persist-credentials: false"))

    def test_supported_macos_bottle_jobs_run_formula_test(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        bottle_job = yaml_block(workflow, "  bottle:")

        self.assertIn(
            "github.event_name == 'workflow_dispatch' ||",
            bottle_job,
        )
        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'",
            bottle_job,
        )
        self.assertNotIn("if: false", bottle_job)
        self.assertIn("os: [macos-15, macos-14]", bottle_job)
        self.assertIn("brew test --verbose --keep-tmp", bottle_job)

    def test_formula_test_failure_preserves_event_server_log(self):
        workflow = BOTTLE_WORKFLOW_PATH.read_text()
        brew_test = yaml_block(
            workflow,
            "      - name: Test installed formula",
        )

        self.assertIn("brew test --verbose --keep-tmp", brew_test)
        self.assertIn("event-server.log", brew_test)
        self.assertIn(
            'cp "$LOG_PATH" "$RUNNER_TEMP/bobi-event-server.log"',
            brew_test,
        )


if __name__ == "__main__":
    unittest.main()
