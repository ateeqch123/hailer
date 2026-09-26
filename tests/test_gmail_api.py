from hailer.gmail_api import MAX_MESSAGES_PER_ACCOUNT, UNREAD_QUERY, GmailApiClient
from hailer.messages import METADATA_HEADERS


class _Api:
    def __init__(self):
        self.calls = []
        self._last = None

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        self._last = "list"
        return self

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        self._last = "get"
        return self

    def send(self, **kwargs):
        self.calls.append(("send", kwargs))
        self._last = "send"
        return self

    def execute(self):
        if self._last == "list":
            return {"messages": [{"id": "m1"}]}
        if self._last == "get":
            return {
                "id": "m1",
                "snippet": "hello",
                "payload": {"headers": [{"name": "Subject", "value": "Hi"}]},
            }
        if self._last == "send":
            return {"id": "sent"}
        raise AssertionError(self._last)


def test_client_calls_list_get_and_send_with_metadata(tmp_path):
    api = _Api()
    client = GmailApiClient(tmp_path)
    client._services["a@example.com"] = api
    assert client.list_unread_ids("a@example.com") == ["m1"]
    message = client.get_message("a@example.com", "m1")
    client.send_raw("a@example.com", "cmF3")
    assert message.subject == "Hi"
    assert api.calls[0] == (
        "list",
        {"userId": "me", "q": UNREAD_QUERY, "maxResults": MAX_MESSAGES_PER_ACCOUNT},
    )
    assert UNREAD_QUERY == "is:unread in:inbox"
    assert MAX_MESSAGES_PER_ACCOUNT == 25
    kind, kwargs = api.calls[1]
    assert kind == "get"
    assert kwargs["userId"] == "me"
    assert kwargs["id"] == "m1"
    assert kwargs["format"] == "metadata"
    assert set(kwargs["metadataHeaders"]) == set(METADATA_HEADERS)
    assert api.calls[2] == ("send", {"userId": "me", "body": {"raw": "cmF3"}})
