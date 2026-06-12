from dataclasses import dataclass
from email import policy
from email.headerregistry import Address
from email.parser import BytesParser
from email.utils import parseaddr

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ParsedMessage:
    recipient: str
    sender: str
    subject: str
    text_body: str
    html_body: str
    raw_mime: str
    headers: dict[str, str]


def normalize_recipient(value: str) -> str:
    value = value.strip().strip("<>").lower()
    _, address = parseaddr(value)
    address = (address or value).strip().lower()
    if "@" not in address:
        raise ValueError("recipient must contain @")
    local, domain = address.rsplit("@", 1)
    if not local or not domain:
        raise ValueError("recipient local part and domain must be non-empty")
    return f"{local}@{domain}"


def _sender_address(value: object) -> str:
    if not value:
        return ""

    addresses = getattr(value, "addresses", None)
    if addresses:
        first = addresses[0]
        if isinstance(first, Address):
            return first.addr_spec

    _, address = parseaddr(str(value))
    return address


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def parse_message(raw: bytes, envelope_recipient: str) -> ParsedMessage:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    recipient = normalize_recipient(envelope_recipient)

    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = part.get_content_disposition()
            content_type = part.get_content_type()
            if content_disposition == "attachment":
                continue
            if content_type == "text/plain" and not text_body:
                text_body = part.get_content()
            elif content_type == "text/html" and not html_body:
                html_body = part.get_content()
    else:
        content_type = msg.get_content_type()
        if content_type == "text/html":
            html_body = msg.get_content()
        else:
            text_body = msg.get_content()

    if not text_body and html_body:
        text_body = _html_to_text(html_body)

    headers = {key.lower(): str(value) for key, value in msg.items()}

    return ParsedMessage(
        recipient=recipient,
        sender=_sender_address(msg["from"]),
        subject=str(msg["subject"] or ""),
        text_body=text_body or "",
        html_body=html_body or "",
        raw_mime=raw.decode("utf-8", errors="replace"),
        headers=headers,
    )
