import os, re, ipaddress, logging
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from core import ORIGIN
from fastapi import HTTPException

logger=logging.getLogger(__name__)
EMAIL_BASE_URL='https://integrations.emergentagent.com'
EMAIL_KEY=os.environ['EMERGENT_EMAIL_KEY']
EMAIL_FROM_NAME=os.environ['EMAIL_FROM_NAME']
EMAIL_REPLY_TO=os.environ.get('EMAIL_REPLY_TO')
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)
def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)
def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)
class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []
    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []
def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan(); scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")
async def send_email(*, to: str, subject: str, html: str):
    _assert_safe_email(subject,html)
    payload={'to':[to],'subject':subject,'html':html,'from_name':EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO: payload['contact_email']=EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp=await client.post(f'{EMAIL_BASE_URL}/api/v1/email/send',headers={'X-Email-Key':EMAIL_KEY},json=payload)
        resp.raise_for_status()
        return resp.json().get('id')
    except httpx.HTTPStatusError as e:
        logger.warning('Email service refused request: %s', e.response.status_code)
        raise HTTPException(503,'Email is temporarily unavailable')
    except httpx.HTTPError:
        raise HTTPException(503,'Email is temporarily unavailable')
async def send_reset(user, token):
    link=f'{ORIGIN}/reset-password?token={token}'
    html=(f'<table role="presentation" width="100%"><tr><td style="padding:32px;font-family:Arial,sans-serif">'
          f'<h2>{escape(EMAIL_FROM_NAME)}</h2><p>Hello {escape(user["name"])},</p>'
          f'<p>A password reset was requested for your workspace account.</p><p><a href="{escape(link)}">Reset your password</a></p>'
          f'<p>This link expires in 30 minutes and can be used once. If you did not request this, ignore this email.</p>'
          f'<p style="color:#888;font-size:12px">Sent by {escape(EMAIL_FROM_NAME)}. We never ask for your password by email.</p></td></tr></table>')
    return await send_email(to=user['email'],subject=f'Reset your {EMAIL_FROM_NAME} password',html=html)