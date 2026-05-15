from cloak_relay.models import bool_from_value, get_session_id


def test_session_id_defaults_to_default():
    assert get_session_id({}) == "default"


def test_session_id_rejects_empty_string():
    try:
        get_session_id({"sessionId": "   "})
    except ValueError as exc:
        assert "sessionId" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_bool_from_value_accepts_json_and_text_values():
    assert bool_from_value(True, default=False) is True
    assert bool_from_value("true", default=False) is True
    assert bool_from_value("0", default=True) is False
    assert bool_from_value(None, default=True) is True
