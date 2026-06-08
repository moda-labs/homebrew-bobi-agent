#!/usr/bin/env python3
"""Generate an updated Homebrew formula for modastack.

Usage: python3 update-formula.py <version> [formula-path]

Reads the existing formula to preserve depends_on and structure,
regenerates resource blocks from PyPI via homebrew-pypi-poet.
"""
import json
import re
import subprocess
import sys
import urllib.request

DEPENDS_ON_PACKAGES = {"cffi", "cryptography", "pycparser", "rpds-py"}


def get_pypi_info(version):
    url = f"https://pypi.org/pypi/modastack/{version}/json"
    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)
    sdist = next(u for u in data["urls"] if u["packagetype"] == "sdist")
    return sdist["url"], sdist["digests"]["sha256"]


def get_resources(version):
    result = subprocess.run(
        ["poet", f"modastack=={version}"],
        capture_output=True, text=True, check=True,
    )
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError("poet produced no output")

    blocks = re.split(r"\n(?=resource \")", raw)
    filtered = []
    for block in blocks:
        m = re.match(r'resource "([^"]+)"', block)
        if not m:
            continue
        name = m.group(1).replace("-", "_").lower()
        if name in {p.replace("-", "_") for p in DEPENDS_ON_PACKAGES}:
            continue
        indented = "\n".join(f"  {line}" for line in block.strip().split("\n"))
        filtered.append(indented)

    return "\n\n".join(filtered)


def main():
    version = sys.argv[1]
    url, sha256 = get_pypi_info(version)
    resources = get_resources(version)
    depends_on = "\n".join(
        f'  depends_on "{pkg}"' for pkg in sorted(DEPENDS_ON_PACKAGES)
    )

    formula = f'''class Modastack < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/modastack"
  url "{url}"
  sha256 "{sha256}"
  license "MIT"

{depends_on}
  depends_on "python@3.13"

{resources}

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Usage", shell_output("#{{bin}}/modastack --help")
  end
end
'''
    print(formula, end="")


if __name__ == "__main__":
    main()
