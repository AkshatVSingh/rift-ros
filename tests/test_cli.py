from rift_ros.cli import main, _pair, _topic

def test_demo_command(tmp_path, capsys):
    assert main(['demo','--out',str(tmp_path/'d')]) == 0
    assert (tmp_path/'d'/'incident.json').exists()
    assert 'Failures:' in capsys.readouterr().out

def test_analyze_failing_incident_returns_one(tmp_path):
    main(['demo','--out',str(tmp_path/'d')]); assert main(['analyze',str(tmp_path/'d')]) == 1

def test_pair(): assert _pair('map:odom') == ('map','odom')
def test_topic_plain(): assert _topic('/scan').min_hz is None
def test_topic_rate(): assert _topic('/odom=20').min_hz == 20
