from cysuml.__main__ import main


def test_command_is_a_placeholder(capsys):
    assert main() == 1
    assert "not implemented" in capsys.readouterr().err
