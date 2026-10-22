from rift_ros.demo import nav2_failure_demo
from rift_ros.models import Severity

def test_demo_has_failure_chain():
    i=nav2_failure_demo(); assert len(i.events)>=6 and sum(e.severity==Severity.FAIL for e in i.events)>=3

def test_demo_is_labeled_synthetic(): assert 'synthetic' in nav2_failure_demo().metadata['source']
