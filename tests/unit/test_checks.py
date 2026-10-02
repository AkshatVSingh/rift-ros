from ros_doctor.checks import expected_nodes, expected_topics
from ros_doctor.collectors.graph import TopicInfo
from ros_doctor.models import Severity


def test_expected_node_failure():
    result = expected_nodes(["/amcl"], ["/controller_server"])[0]
    assert result.severity == Severity.FAIL


def test_expected_topic_pass():
    result = expected_topics([TopicInfo("/scan")], ["/scan"])[0]
    assert result.severity == Severity.PASS
