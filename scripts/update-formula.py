#!/usr/bin/env python3
"""Generate an updated Homebrew formula for modastack.

Usage: python3 update-formula.py <version>

Fetches the sdist URL and SHA from PyPI. Dependencies are installed
from wheels at build time (no resource blocks needed), avoiding
source compilation issues with Rust/C extensions like pydantic-core.
"""
import json
import sys
import urllib.request


def get_pypi_sdist(version):
    url = f"https://pypi.org/pypi/modastack/{version}/json"
    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)
    for u in data["urls"]:
        if u["packagetype"] == "sdist":
            return u["url"], u["digests"]["sha256"]
    return None, None


def main():
    version = sys.argv[1]
    url, sha256 = get_pypi_sdist(version)
    if not url:
        print(f"ERROR: no sdist for modastack {version}", file=sys.stderr)
        sys.exit(1)

    formula = f'''class Modastack < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/modastack"
  url "{url}"
  sha256 "{sha256}"
  license "MIT"

  depends_on "python@3.13"

  def install
    venv = virtualenv_create(libexec, "python3.13")
    # Homebrew creates venvs without pip; bootstrap it so we can
    # install modastack with binary wheels (avoids Rust/C compilation).
    system libexec/"bin/python3", "-m", "ensurepip", "--upgrade"
    system libexec/"bin/pip", "install", "-v", "modastack==#{{version}}"
    bin.install_symlink libexec/"bin/modastack"
  end

  test do
    assert_match "Usage", shell_output("#{{bin}}/modastack --help")
  end
end
'''
    print(formula, end="")


if __name__ == "__main__":
    main()
