import json

import pytest

from finpulse.observability.logging import REDACTED, configure_logging, get_logger
from tests.conftest import make_settings


def test_sensitive_fields_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(LOG_FORMAT="json"))
    log = get_logger("test")

    log.info(
        "event",
        authorization="Bearer abc",
        payload={"description": "UPI/RENT/landlord", "amount_minor": 100},
        safe="visible",
    )

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["authorization"] == REDACTED
    assert line["payload"]["description"] == REDACTED
    assert line["payload"]["amount_minor"] == 100
    assert line["safe"] == "visible"
    assert line["level"] == "info"
    assert "timestamp" in line
