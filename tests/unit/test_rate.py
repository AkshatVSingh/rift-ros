from ros_doctor.collectors import rate
from ros_doctor.shell import CommandResult


def test_rate_parser_uses_last_average(monkeypatch):
    output = "average rate: 9.8\naverage rate: 10.1\n"
    monkeypatch.setattr(rate, "run", lambda *a, **k: CommandResult(124, output, "", True))
    result = rate.sample_rate("/scan")
    assert result.hz == 10.1
