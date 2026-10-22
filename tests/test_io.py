from rift_ros.io import write_events, read_events, write_incident, read_incident
from rift_ros.models import Event, Incident

def test_event_file_roundtrip(tmp_path):
    p=write_events(tmp_path/'e.jsonl',[Event(1,"x","s","m")]); assert read_events(p)[0].message=="m"
def test_incident_bundle_roundtrip(tmp_path):
    p=write_incident(tmp_path/'i', Incident('id',2,'why',[Event(1,'x','s','m')]))
    assert read_incident(p).incident_id=='id'
def test_read_directory(tmp_path):
    write_incident(tmp_path/'i', Incident('id',2,'why',[])); assert read_incident(tmp_path/'i').reason=='why'
