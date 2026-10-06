from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class EntitySummary(BaseModel):
    """A person or business FinPulse holds financial data for."""

    id: uuid.UUID
    display_name: str
    kind: Literal["business", "individual"] | str
    segment: str
    data_origin: str
