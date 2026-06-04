class Modastack < Formula
  include Language::Python::Virtualenv

  desc "AI engineering team: manager + engineer agents with Linear, GitHub, Slack"
  homepage "https://github.com/moda-labs/modastack"
  url "https://files.pythonhosted.org/packages/source/m/modastack/modastack-0.5.0.tar.gz"
  sha256 "f709734131732d4d8f675fa5275bbeadd636a59e2b26efba530a9f171b380af5"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_create(libexec, "python3.13")
    system libexec/"bin/pip", "install", *std_pip_args(build_isolation: true), buildpath
  end

  test do
    assert_match "Usage", shell_output("#{bin}/modastack --help")
  end
end
