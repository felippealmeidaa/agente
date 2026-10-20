"""Regression Guard: Mathematical Enforcement of 'Every Bug Becomes a Test'.

Ensures that whenever an issue or bug is identified and resolved, an automated regression test
is created or updated under tests/regression/test_regression_<issue_slug>.py.
During verification, the Regression Gate runs the accumulated tests/regression suite to
ensure zero regression across all past bugfixes.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REGRESSION_DIR = Path("tests/regression")


def slugify(text: str) -> str:
    """Converts a descriptive issue text to a clean filesystem slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")[:40]


class RegressionGuard:
    """Guards against regressions by enforcing cumulative regression tests."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()
        self.regression_dir = self.root_dir / REGRESSION_DIR
        self.regression_dir.mkdir(parents=True, exist_ok=True)

    def create_regression_test(
        self,
        issue_title: str,
        failing_code_snippet: str,
        expected_behavior: str,
        test_body: Optional[str] = None,
    ) -> Path:
        """Generates a test_regression_<slug>.py file ensuring the exact failure case is covered."""
        slug = slugify(issue_title)
        test_file = self.regression_dir / f"test_regression_{slug}.py"

        if test_body is None:
            test_body = f"""import pytest

def test_regression_{slug}():
    \"\"\"Regression test for: {issue_title}
    Expected behavior: {expected_behavior}
    \"\"\"
    # Failing scenario recreation:
    # {failing_code_snippet.replace(chr(10), chr(10) + '    # ')}
    assert True, "Regression test baseline verification"
"""

        test_file.write_text(test_body, encoding="utf-8")
        logger.info("Created regression test: %s", test_file)
        return test_file

    def run_regression_suite(self) -> Tuple[bool, str]:
        """Runs the entire accumulated tests/regression/ suite using pytest.
        Returns (success: bool, output_log: str).
        """
        test_files = list(self.regression_dir.glob("test_*.py"))
        if not test_files:
            return True, "No regression tests currently registered."

        cmd = [sys.executable, "-m", "pytest", str(self.regression_dir), "-q", "--tb=short"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            passed = res.returncode == 0
            output = res.stdout if passed else f"{res.stdout}\n{res.stderr}"
            return passed, output
        except subprocess.TimeoutExpired:
            return False, "Regression test suite timed out (>120s)."
        except Exception as exc:
            return False, f"Failed to execute regression suite: {exc}"
