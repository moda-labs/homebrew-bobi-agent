class Modastack < Formula
  include Language::Python::Virtualenv

  desc "AI engineering team: manager + engineer agents with Linear, GitHub, Slack"
  homepage "https://github.com/moda-labs/modastack"
  url "https://files.pythonhosted.org/packages/source/m/modastack/modastack-0.2.0.tar.gz"
  sha256 "6ed8610da3716760fb61f26eee5f3ef39c88b3af3cca0e2e2817574404288a9d"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Usage", shell_output("#{bin}/modastack --help")
  end
end
