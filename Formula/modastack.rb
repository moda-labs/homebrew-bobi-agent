class Modastack < Formula
  include Language::Python::Virtualenv

  desc "Event-driven AI agent framework"
  homepage "https://github.com/moda-labs/modastack"
  url "https://files.pythonhosted.org/packages/c0/39/14cdd1de074f10db33078fb109d6013d5b9fbbc066173c810aaf88794bf8/modastack-0.9.3.tar.gz"
  sha256 "5079e18edd29ab5d9438aa87d523d18e20b9f17196635337e2c0ff69b82bc61b"
  license "MIT"

  depends_on "python@3.13"

  def install
    venv = virtualenv_create(libexec, "python3.13")
    # Use python -m pip (venv inherits system pip via --system-site-packages)
    # instead of calling the pip binary (which doesn't exist in the venv).
    # This installs from wheels, avoiding Rust/C source compilation.
    system libexec/"bin/python3", "-m", "pip", "install", "-v",
           "modastack==#{version}"
    bin.install_symlink libexec/"bin/modastack"
  end

  test do
    assert_match "Usage", shell_output("#{bin}/modastack --help")
  end
end
