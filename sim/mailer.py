import html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


class Mailer:
    def __init__(self, address, password):
        self.address = address
        self.password = password

    @classmethod
    def from_env(cls):
        address = (os.environ.get("GMAIL_ADDRESS") or "").strip()
        password = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
        return cls(address, password) if address and password else None

    def send(self, subject, markdown):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = "Paper-trading bots <%s>" % self.address
        msg["To"] = self.address
        msg.set_content(markdown)
        msg.add_alternative(to_html(markdown), subtype="html")
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30)
        try:
            smtp.login(self.address, self.password)
            smtp.send_message(msg)
        finally:
            # close() rather than QUIT: a failed QUIT after a delivered message would get it sent twice.
            smtp.close()


def _inline(text):
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return re.sub(r"(https://[^\s<]+)", r'<a href="\1">\1</a>', text)


def _table(rows):
    cell = "border:1px solid #d1d5db;padding:4px 8px;text-align:left"
    out = ['<table style="border-collapse:collapse;font-size:13px">']
    body = [r for r in rows if r.replace("|", "").replace("-", "").strip()]
    for n, row in enumerate(body):
        tag = "th" if n == 0 else "td"
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        out.append("<tr>%s</tr>" % "".join('<%s style="%s">%s</%s>' % (tag, cell, _inline(c), tag) for c in cells))
    out.append("</table>")
    return "".join(out)


def to_html(markdown):
    out, table = [], []
    for line in markdown.splitlines() + [""]:
        if line.startswith("|"):
            table.append(line)
            continue
        if table:
            out.append(_table(table))
            table = []
        if line.startswith("- "):
            out.append("<p>&bull; %s</p>" % _inline(line[2:]))
        elif line.strip():
            out.append("<p>%s</p>" % _inline(line))
    return '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111827">%s</div>' % "".join(out)
