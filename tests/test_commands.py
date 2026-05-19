from mudclient.ansi import strip_ansi
from mudclient.commands import parse_local_command, validate_host, validate_port


def test_parse_command():
    cmd = parse_local_command('/connect example.com 4000')
    assert cmd is not None
    assert cmd.name == 'connect'
    assert cmd.args == ['example.com', '4000']
    assert parse_local_command('say hi') is None


def test_validation():
    assert validate_host('example.com')
    assert not validate_host('bad host')
    assert validate_port(1)
    assert validate_port(65535)
    assert not validate_port(0)


def test_strip_ansi():
    raw = '\x1b[31mDanger\x1b[0m'
    assert strip_ansi(raw) == 'Danger'
