from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NewType


FrameID = NewType("FrameID", int)
FrameDatetime = NewType("FrameDatetime", datetime)


class CameraName(str, Enum):
    PIE = "Pan Island Expressway (PIE)"
    AYE = "Ayer Rajah Expressway (AYE)"
    ECP = "East Coast Parkway (ECP)"
    CTE = "Central Expressway (CTE)"
    TPE = "Tampines Expressway (TPE)"
    KPE = "Kallang-Paya Lebar Expressway (KPE)"
    SLE = "Seletar Expressway (SLE)"
    BKE = "Bukit Timah Expressway (BKE)"
    KJE = "Kranji Expressway (KJE)"
    MCE = "Marina Coastal Expressway (MCE)"


@dataclass(frozen=True, slots=True)
class CCTVFrameRecord:
    frame_id: FrameID
    datetime: FrameDatetime
    camera_name: CameraName

