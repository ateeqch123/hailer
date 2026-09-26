from email.header import decode_header

from hailer.messages import (
    METADATA_HEADERS,
    headers_from_api_payload,
    message_from_api_response,
    message_ids_from_list_response,
)
from hailer.classify import classify


def test_metadata_headers_include_the_required_set():
    required = {"From", "Subject", "Date", "Auto-Submitted", "Precedence", "List-Id"}
    assert required <= set(METADATA_HEADERS)
    assert "X-Hailer" in METADATA_HEADERS


def test_list_response_ids_skip_blanks():
    assert message_ids_from_list_response({"messages": [{"id": "a"}, {}, {"id": "b"}]}) == ["a", "b"]
    assert message_ids_from_list_response({}) == []


def test_api_message_decodes_subject_and_keeps_first_header():
    message = message_from_api_response(
        {
            "id": "18d2",
            "snippet": "A recruiter wrote",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Jordan <jordan@example.com>"},
                    {"name": "From", "value": "other@example.com"},
                    {"name": "Subject", "value": "=?utf-8?q?Interview?= next week"},
                    {"name": "Auto-Submitted", "value": "no"},
                    "not-a-header",
                ]
            },
        }
    )
    assert message.message_id == "18d2"
    assert message.headers["from"] == "Jordan <jordan@example.com>"
    assert message.headers["subject"] == "Interview next week"
    assert message.snippet == "A recruiter wrote"
    assert classify(message.headers, message.snippet) == "recruiter"


def test_decode_round_trip_matches_email_header():
    raw = "=?utf-8?q?Hiring?="
    assert headers_from_api_payload([{"name": "Subject", "value": raw}])["subject"] == "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in decode_header(raw)
    )
