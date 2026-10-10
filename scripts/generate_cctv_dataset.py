from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
import sqlite3
from pathlib import Path

from pipeline.models import CCTVFrameRecord, CameraName, FrameDatetime, FrameID

CAMERAS = [camera.value for camera in CameraName]


def stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def choose_camera(timestamp: dt.datetime) -> CameraName:
    """
    Deterministically vary camera selection so the dataset is balanced and reproducible.
    """
    month_key = timestamp.strftime("%Y-%m")
    day_key = timestamp.strftime("%Y-%m-%d")
    hour = timestamp.hour
    minute = timestamp.minute

    weights = {
        CameraName.PIE.value: 18,
        CameraName.AYE.value: 12,
        CameraName.ECP.value: 11,
        CameraName.CTE.value: 14,
        CameraName.TPE.value: 10,
        CameraName.KPE.value: 8,
        CameraName.SLE.value: 7,
        CameraName.BKE.value: 8,
        CameraName.KJE.value: 6,
        CameraName.MCE.value: 6,
    }

    # Slightly bias certain cameras at different times of day so tests can
    # exercise a more varied distribution without breaking determinism.
    if 6 <= hour <= 9:
        weights[CameraName.CTE.value] += 5
        weights[CameraName.AYE.value] += 3
    elif 17 <= hour <= 20:
        weights[CameraName.PIE.value] += 5
        weights[CameraName.TPE.value] += 4
    elif hour <= 5:
        weights[CameraName.MCE.value] += 4
        weights[CameraName.KPE.value] += 3

    rng = random.Random(stable_seed(f"{month_key}|{day_key}|{hour}|{minute}"))
    population = []
    for camera, weight in weights.items():
        population.extend([camera] * weight)
    return CameraName(rng.choice(population))


def build_rows(start: dt.datetime, end: dt.datetime):
    frame_id = 1
    current = start
    while current <= end:
        yield CCTVFrameRecord(
            frame_id=FrameID(frame_id),
            datetime=FrameDatetime(current.replace(microsecond=0)),
            camera_name=choose_camera(current),
        )
        frame_id += 1
        current += dt.timedelta(minutes=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic CCTV frame dataset.")
    parser.add_argument(
        "--output",
        default=str(Path("data") / "cctv_frames.db"),
        help="Path to the SQLite database to create.",
    )
    parser.add_argument(
        "--start",
        default="2026-01-01T00:00:00",
        help="Inclusive start datetime in ISO 8601.",
    )
    parser.add_argument(
        "--end",
        default="2026-10-09T23:55:00",
        help="Inclusive end datetime in ISO 8601.",
    )
    args = parser.parse_args()

    start = dt.datetime.fromisoformat(args.start)
    end = dt.datetime.fromisoformat(args.end)
    if end < start:
        raise ValueError("end must be greater than or equal to start")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(output_path)
    try:
        conn.execute(
            """
            CREATE TABLE frames (
                frame_id INTEGER PRIMARY KEY,
                datetime TEXT NOT NULL,
                camera_name TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX idx_frames_datetime ON frames(datetime)")
        conn.execute("CREATE INDEX idx_frames_camera_name ON frames(camera_name)")

        rows = list(build_rows(start, end))
        conn.executemany(
            "INSERT INTO frames(frame_id, datetime, camera_name) VALUES (?, ?, ?)",
            [
                (int(row.frame_id), row.datetime.isoformat(timespec="seconds"), row.camera_name.value)
                for row in rows
            ],
        )
        conn.commit()

        counts = dict(conn.execute("SELECT camera_name, COUNT(*) FROM frames GROUP BY camera_name").fetchall())
        total = conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
        print(f"Created {output_path}")
        print(f"Rows: {total}")
        print("Distribution:")
        for camera in CAMERAS:
            print(f"  {camera}: {counts.get(camera, 0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
