from datetime import datetime

from pipeline.models import CCTVFrameRecord, CameraName, FrameDatetime, FrameID


def test_frame_record_shape():
    record = CCTVFrameRecord(
        frame_id=FrameID(123),
        datetime=FrameDatetime(datetime(2026, 10, 9, 12, 30, 0)),
        camera_name=CameraName.CTE,
    )

    assert record.frame_id == 123
    assert record.datetime.isoformat() == "2026-10-09T12:30:00"
    assert record.camera_name == CameraName.CTE

