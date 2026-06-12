from maildrop.mailparse import ParsedMessage, normalize_recipient, parse_message


RAW = """From: Sender <sender@example.com>
To: Alpha <alpha@aiprot.space>
Subject: =?utf-8?b?5rWL6K+V?=
Message-ID: <m1@example.com>
Content-Type: multipart/alternative; boundary="b"

--b
Content-Type: text/plain; charset=utf-8

Hello plain
--b
Content-Type: text/html; charset=utf-8

<p>Hello <b>html</b></p>
--b--
"""


def test_normalize_recipient_lowercases_domain_and_prefix():
    assert normalize_recipient("Alpha@AIPROT.SPACE") == "alpha@aiprot.space"


def test_parse_message_extracts_subject_sender_and_bodies():
    parsed = parse_message(RAW.encode("utf-8"), "alpha@aiprot.space")

    assert isinstance(parsed, ParsedMessage)
    assert parsed.recipient == "alpha@aiprot.space"
    assert parsed.sender == "sender@example.com"
    assert parsed.subject == "测试"
    assert parsed.text_body.strip() == "Hello plain"
    assert "Hello" in parsed.html_body
    assert parsed.headers["message-id"] == "<m1@example.com>"
