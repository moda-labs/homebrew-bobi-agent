class Modastack < Formula
  include Language::Python::Virtualenv

  desc "AI engineering team: manager + engineer agents with Linear, GitHub, Slack"
  homepage "https://github.com/moda-labs/modastack"
  url "https://files.pythonhosted.org/packages/source/m/modastack/modastack-0.5.0.tar.gz"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Usage", shell_output("#{bin}/modastack --help")
  end
end
