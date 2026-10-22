from rift_ros.models import Event, Incident, Severity

def test_event_roundtrip():
    e = Event(1.2, "rate", "/odom", "low", Severity.FAIL, 4.2, "Hz", ("odom",), {"min": 20})
    assert Event.from_dict(e.to_dict()) == e

def test_incident_roundtrip():
    i = Incident("x", 2, "r", [Event(1, "a", "b", "c")], {"robot":"r1"})
    j = Incident.from_dict(i.to_dict())
    assert j.incident_id == "x" and j.metadata["robot"] == "r1" and len(j.events) == 1

def test_schema_present():
    assert Incident("x", 0, "r", []).to_dict()["schema"] == "rift.incident/v2"
