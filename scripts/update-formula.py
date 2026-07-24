#!/usr/bin/env python3
"""Generate an updated Homebrew formula for bobi.

Usage: python3 update-formula.py <version> [--sdist-url URL --sdist-sha256 SHA256]

Installs bobi, discovers all dependencies via pip freeze, fetches
sdist URLs from PyPI, and generates a complete formula with resource
blocks. Rust-based resources are installed with build_isolation: false
to use the system maturin.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request

PACKAGE = "bobi"
RUST_RESOURCES = {"pydantic-core", "watchfiles", "rpds-py", "cryptography"}
SKIP_PACKAGES = {PACKAGE, "pip", "wheel", "maturin"}


def ruby_string(value):
    """Render a string without allowing Ruby interpolation."""
    return json.dumps(str(value), ensure_ascii=True).replace("#{", r"\#{")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the Bobi Homebrew formula.",
    )
    parser.add_argument("version", help="Bobi version represented by the formula")
    parser.add_argument(
        "--sdist-url",
        help="Use this Bobi sdist URL instead of resolving it from PyPI",
    )
    parser.add_argument(
        "--sdist-sha256",
        help="SHA-256 digest for --sdist-url",
    )
    args = parser.parse_args(argv)

    if bool(args.sdist_url) != bool(args.sdist_sha256):
        parser.error("--sdist-url and --sdist-sha256 must be provided together")
    if args.sdist_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sdist_sha256):
        parser.error("--sdist-sha256 must be exactly 64 hexadecimal characters")
    return args


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


def main(argv=None):
    args = parse_args(argv)
    version = args.version

    packages = get_installed_packages()

    # setuptools is needed by cryptography's Rust build but doesn't
    # appear in pip freeze. Install it explicitly and add it.
    if "setuptools" not in {k.lower() for k in packages}:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "setuptools"],
            capture_output=True, check=True,
        )
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "setuptools"],
            capture_output=True, text=True, check=True,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Version:"):
                packages["setuptools"] = line.split(":", 1)[1].strip()
                break

    if args.sdist_url:
        mod_url, mod_sha = args.sdist_url, args.sdist_sha256.lower()
    else:
        mod_url, mod_sha = get_pypi_sdist(PACKAGE, version)
    if not mod_url:
        print(f"ERROR: no sdist for {PACKAGE} {version}", file=sys.stderr)
        sys.exit(1)

    resource_blocks = []
    rust_names = []

    for name, ver in sorted(packages.items(), key=lambda x: x[0].lower()):
        normalized = name.replace("-", "_").lower()
        if normalized in {p.replace("-", "_") for p in SKIP_PACKAGES}:
            continue
        url, sha = get_pypi_sdist(name, ver)
        if not url:
            continue
        resource_blocks.append(
            f"  resource {ruby_string(name.lower())} do\n"
            f"    url {ruby_string(url)}\n"
            f"    sha256 {ruby_string(sha)}\n"
            f"  end"
        )
        if normalized in {p.replace("-", "_") for p in RUST_RESOURCES}:
            rust_names.append(name.lower())

    resources_text = "\n\n".join(resource_blocks)
    rust_list = ", ".join(ruby_string(name) for name in sorted(rust_names))

    formula = f'''class Bobi < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/bobi-agent"
  url {ruby_string(mod_url)}
  version {ruby_string(version)}
  sha256 {ruby_string(mod_sha)}
  license "MIT"

  depends_on "maturin" => :build
  depends_on "rust" => :build
  depends_on "node"
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
    require "digest"
    require "find"
    require "json"
    require "net/http"
    require "pathname"
    require "shellwords"

    python = libexec/"bin/python"
    site_packages = libexec/"lib/python3.13/site-packages/bobi"
    runtime_root = testpath/"runtime"
    npm_shim_dir = testpath/"npm-shim"
    npm_trace = testpath/"npm-invoked"
    runtime_root.mkpath
    npm_shim_dir.mkpath

    (npm_shim_dir/"npm").write <<~SH
      #!/bin/sh
      printf '%s\\n' "$*" >> "$BOBI_HOMEBREW_NPM_TRACE"
      exit 97
    SH
    (npm_shim_dir/"npm").chmod 0755

    snapshot = lambda do
      files = {{}}
      Find.find(site_packages) do |entry|
        path = Pathname(entry)
        relative = path.relative_path_from(site_packages).to_s
        digest = path.file? ? Digest::SHA256.file(path).hexdigest : nil
        target = path.symlink? ? path.readlink.to_s : nil
        files[relative] = [path.stat.mode, path.stat.size, digest, target]
      end
      files
    end

    smoke = testpath/"event-server-smoke.py"
    smoke.write <<~PYTHON
      import json
      import sys
      from pathlib import Path

      from bobi.events.server import ensure_running

      port = int(sys.argv[1])
      runtime_root = Path(sys.argv[2])
      status = ensure_running(
          port,
          bind="127.0.0.1",
          project_path=runtime_root,
      )
      print(json.dumps({{"status": status}}))
    PYTHON

    ENV["BOBI_HOMEBREW_NPM_TRACE"] = npm_trace.to_s
    ENV["PYTHONDONTWRITEBYTECODE"] = "1"
    ENV.prepend_path "PATH", Formula["node"].opt_bin
    ENV.prepend_path "PATH", npm_shim_dir

    node_version = shell_output("#{{Formula["node"].opt_bin}}/node --version")
    assert_operator node_version.delete_prefix("v").split(".").first.to_i, :>=, 20

    before = snapshot.call
    port = free_port
    pid_file = runtime_root/"state/event-server.pid"
    log_file = runtime_root/"state/event-server.log"

    begin
      command = [python, smoke, port.to_s, runtime_root].map do |argument|
        Shellwords.escape(argument.to_s)
      end.join(" ")
      startup = JSON.parse(
        shell_output(command),
      )
      assert_equal "started", startup.fetch("status")

      health = JSON.parse(
        Net::HTTP.get(URI("http://127.0.0.1:#{{port}}/health")),
      )
      assert_equal "ok", health.fetch("status")
      assert_equal "local", health.fetch("mode")
      refute_path_exists npm_trace
      assert_equal before, snapshot.call
    ensure
      failure = $!
      if pid_file.exist?
        pid = pid_file.read.to_i
        if pid.positive?
          begin
            Process.kill("TERM", -pid)
            sleep 1
            Process.kill(0, -pid)
            Process.kill("KILL", -pid)
          rescue Errno::ESRCH
            # The embedded server exited after TERM.
          end
        end
      end
      if failure && log_file.exist?
        $stderr.puts "=== event-server.log ==="
        $stderr.puts log_file.read
      end
    end
  end
end
'''
    print(formula, end="")


if __name__ == "__main__":
    main()
