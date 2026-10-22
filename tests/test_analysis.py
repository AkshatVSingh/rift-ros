from rift_ros.analysis import summarize, timeline, render_summary
from rift_ros.models import Event, Severity

def events():
    return [Event(2,"b","two","ok"), Event(1,"a","one","bad",Severity.FAIL), Event(3,"a","three","warn",Severity.WARN)]

def test_summary_counts():
    s=summarize(events()); assert s.total==3 and s.failures==1 and s.warnings==1

def test_failed_sources(): assert summarize(events()).failed_sources == ("one",)
def test_timeline_sorts(): assert [e.ts for e in timeline(events())] == [1,2,3]
def test_anomaly_timeline_filters_info(): assert len(timeline(events(), True)) == 2
def test_render_mentions_source(): assert "one" in render_summary(events())
def test_empty_summary(): assert summarize([]).total == 0
