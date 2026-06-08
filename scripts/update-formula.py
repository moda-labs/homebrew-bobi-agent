#!/usr/bin/env python3
"""Generate an updated Homebrew formula for modastack.

Usage: python3 update-formula.py <version>

Installs modastack, resolves all dependencies via pip freeze,
fetches sdist URLs from PyPI, and generates the complete formula.
No external tools needed (replaces homebrew-pypi-poet).
"""
import json
import subprocess
import sys
import urllib.request

DEPENDS_ON_PACKAGES = {"cffi", "cryptography", "pycparser", "rpds-py"}
SKIP_PACKAGES = DEPENDS_ON_PACKAGES | {"modastack", "pip", "setuptools", "wheel"}


def get_pypi_sdist(name, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)
    for u in data["urls"]:
        if u["packagetype"] == "sdist":
            return u["url"], u["digests"]["sha256"]
    return None, None


def get_installed_packages():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
        capture_output=True, text=True, check=True,
    )
    packages = {}
    for line in result.stdout.strip().split("\n"):
        if "==" in line:
            name, version = line.split("==", 1)
            packages[name.strip()] = version.strip()
    return packages


def main():
    version = sys.argv[1]

    packages = get_installed_packages()
    modastack_url, modastack_sha = get_pypi_sdist("modastack", version)
    if not modastack_url:
        print(f"ERROR: no sdist for modastack {version}", file=sys.stderr)
        sys.exit(1)

    resources = []
    for name, ver in sorted(packages.items(), key=lambda x: x[0].lower()):
        normalized = name.replace("-", "_").lower()
        if normalized in {p.replace("-", "_") for p in SKIP_PACKAGES}:
            continue
        url, sha = get_pypi_sdist(name, ver)
        if not url:
            print(f"WARNING: no sdist for {name}=={ver}, skipping", file=sys.stderr)
            continue
        resources.append(
            f'  resource "{name.lower()}" do\n'
            f'    url "{url}"\n'
            f'    sha256 "{sha}"\n'
            f"  end"
        )

    depends_on = "\n".join(
        f'  depends_on "{pkg}"' for pkg in sorted(DEPENDS_ON_PACKAGES)
    )
    resource_text = "\n\n".join(resources)

    formula = f'''class Modastack < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/modastack"
  url "{modastack_url}"
  sha256 "{modastack_sha}"
  license "MIT"

{depends_on}
  depends_on "python@3.13"

{resource_text}

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
