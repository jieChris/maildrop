from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: int
    recipient: str
    sender: str
    subject: str
    received_at: datetime
    text_body: str
