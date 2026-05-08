from pydantic import BaseModel


class MailAccountListItem(BaseModel):
    id: int
    email: str
    receive_mode: str | None = None
    client_id: str | None = None
    access_token: str | None = None
    has_access_token: bool = False
    raw_line: str | None = None
    status: str
    password: str | None = None
    updated_at: str | None = None
    remark: str | None = None


class MailAccountCredentialResponse(BaseModel):
    password: str


class MailAccountCreateRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    receive_mode: str | None = None
    raw_line: str | None = None
    client_id: str | None = None
    access_token: str | None = None
    status: str = "idle"
    remark: str | None = None


class MailAccountUpdateRequest(BaseModel):
    email: str
    password: str | None = None
    status: str
    receive_mode: str | None = None
    raw_line: str | None = None
    client_id: str | None = None
    access_token: str | None = None
    remark: str | None = None


class MailAccountImportItem(BaseModel):
    email: str
    password: str
    remark: str | None = None
    raw_line: str | None = None
    client_id: str | None = None
    access_token: str | None = None


class MailAccountImportRequest(BaseModel):
    receive_mode: str
    items: list[MailAccountImportItem]


class MailAccountImportResponse(BaseModel):
    total_count: int
    success_count: int
    duplicate_count: int
    batch_no: str


class MailMessageItem(BaseModel):
    id: str
    received_at_utc: str | None = None
    received_at_beijing: str | None = None
    subject: str | None = None
    sender: str | None = None
    recipient: str | None = None
    content_preview: str | None = None
    content_text: str | None = None
    content_html: str | None = None


class MailFetchResponse(BaseModel):
    account_id: int
    email: str
    receive_mode: str | None = None
    provider: str
    supports_history: bool = False
    note: str | None = None
    messages: list[MailMessageItem]


class SingleMailInfoMessage(BaseModel):
    id: str | None = None
    send_time_utc: str | None = None
    send_time_beijing: str | None = None
    subject: str | None = None
    sender: str | None = None
    receiver: str | None = None
    content: str | None = None
    content_text: str | None = None


class SingleMailInfoResponse(BaseModel):
    status: int
    message: SingleMailInfoMessage | str | None
    provider: str | None = None
    receive_mode: str | None = None
