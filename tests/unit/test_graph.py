from ros_doctor.collectors import graph
from ros_doctor.shell import CommandResult


def test_list_nodes_deduplicates_and_sorts(monkeypatch):
    monkeypatch.setattr(graph, "run", lambda *a, **k: CommandResult(0, "/z\n/a\n/z\n", ""))
    assert graph.list_nodes() == ["/a", "/z"]


def test_list_topics_parses_types(monkeypatch):
    output = "/scan [sensor_msgs/msg/LaserScan]\n/clock [rosgraph_msgs/msg/Clock]\n"
    monkeypatch.setattr(graph, "run", lambda *a, **k: CommandResult(0, output, ""))
    topics = graph.list_topics()
    assert topics[0].name == "/clock"
    assert topics[1].types == ("sensor_msgs/msg/LaserScan",)
