from rift_ros import collectors

def test_topic_rate_parsing(monkeypatch):
    class R: returncode=124; stdout='average rate: 19.5\n'; stderr=''; timed_out=True
    monkeypatch.setattr(collectors,'run',lambda *a,**k:R())
    assert collectors.topic_rate('/scan',0.1)==19.5

def test_tf_requires_translation_and_rotation(monkeypatch):
    class R: returncode=124; stdout='At time 1\nTranslation: [0,0,0]\n'; stderr=''; timed_out=True
    monkeypatch.setattr(collectors,'run',lambda *a,**k:R())
    assert not collectors.tf_available('map','odom',0.1)

def test_tf_success(monkeypatch):
    class R: returncode=0; stdout='Translation: [0,0,0]\nRotation: [0,0,0,1]\n'; stderr=''; timed_out=False
    monkeypatch.setattr(collectors,'run',lambda *a,**k:R())
    assert collectors.tf_available('map','odom',0.1)
