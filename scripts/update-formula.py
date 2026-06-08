#!/usr/bin/env python3
"""Generate an updated Homebrew formula for modastack.

Usage: python3 update-formula.py <version>

Installs modastack, discovers all dependencies via pip freeze, fetches
sdist URLs from PyPI, and generates a complete formula with resource
blocks. Rust-based resources are installed with build_isolation: false
to use the system maturin.
"""
import json
import subprocess
import sys
import urllib.request

RUST_RESOURCES = {"pydantic-core", "watchfiles", "rpds-py", "cryptography"}
SKIP_PACKAGES = {"modastack", "pip", "wheel", "maturin"}


def get_pypi_sdist(name, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.load(resp)
        for u in data["urls"]:
            if u["packagetype"] == "sdist":
                return u["url"], u["digests"]["sha256"]
    except Exception as e:
        print(f"WARNING: PyPI lookup failed for {name}=={version}: {e}", file=sys.stderr)
    return None, None


def get_installed_packages():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable", "--all"],
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

    # setuptools is needed by cryptography's Rust build but may not
    # appear in pip freeze — ensure it's always included.
    if "setuptools" not in {k.lower() for k in packages}:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "setuptools"],
            capture_output=True, text=True,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Version:"):
                packages["setuptools"] = line.split(":", 1)[1].strip()
                break

    mod_url, mod_sha = get_pypi_sdist("modastack", version)
    if not mod_url:
        print(f"ERROR: no sdist for modastack {version}", file=sys.stderr)
        sys.exit(1)

    resource_blocks = []
    rust_names = []
    other_names = []

    for name, ver in sorted(packages.items(), key=lambda x: x[0].lower()):
        normalized = name.replace("-", "_").lower()
        if normalized in {p.replace("-", "_") for p in SKIP_PACKAGES}:
            continue
        url, sha = get_pypi_sdist(name, ver)
        if not url:
            continue
        resource_blocks.append(
            f'  resource "{name.lower()}" do\n'
            f'    url "{url}"\n'
            f'    sha256 "{sha}"\n'
            f"  end"
        )
        if normalized in {p.replace("-", "_") for p in RUST_RESOURCES}:
            rust_names.append(name.lower())
        else:
            other_names.append(name.lower())

    resources_text = "\n\n".join(resource_blocks)
    rust_list = ", ".join(f'"{n}"' for n in sorted(rust_names))

    formula = f'''class Modastack < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/modastack"
  url "{mod_url}"
  sha256 "{mod_sha}"
  license "MIT"

  depends_on "maturin" => :build
  depends_on "rust" => :build
  depends_on "python@3.13"

{resources_text}

  def install
    venv = virtualenv_create(libexec, "python3.13")

    # Install non-Rust resources first (Rust resources depend on some of these)
    rust = [{rust_list}]
    resources.each do |r|
      next if rust.include?(r.name)
      venv.pip_install r
    end

    # Rust-based resources need --no-build-isolation to use system maturin
    rust.each do |name|
      venv.pip_install resource(name), build_isolation: false
    end

    venv.pip_install_and_link buildpath
  end

  test do
    assert_match "Usage", shell_output("#{{bin}}/modastack --help")
  end
end
'''
    print(formula, end="")


if __name__ == "__main__":
    main()
