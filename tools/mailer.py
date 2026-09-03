"""Shared SMTP sender. Each tool may send from its own From address."""
import os, ssl, smtplib
from email.message import EmailMessage

def send(recipients, subject, body, attach_path=None, from_addr=None,
         mime=("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")):
    host = os.getenv("SMTP_HOST"); port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER"); pw = os.getenv("SMTP_PASS")
    sender = from_addr or os.getenv("SMTP_FROM") or user
    if not (host and user and pw):
        raise RuntimeError("Email is not configured on the server (set SMTP_HOST, SMTP_USER, SMTP_PASS).")
    msg = EmailMessage()
    msg["From"] = sender; msg["To"] = ", ".join(recipients); msg["Subject"] = subject
    msg.set_content(body)
    if attach_path and os.path.exists(attach_path):
        with open(attach_path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=mime[0], subtype=mime[1],
                               filename=os.path.basename(attach_path))
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=20) as srv:
            srv.starttls(context=ctx); srv.login(user, pw); srv.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("Email login rejected — check SMTP_USER and the app password (SMTP_PASS).")
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError("The recipient address was refused by the mail server.")
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError("Mail server error: %s" % e)
    print("[mail] sent to %s as %s" % (", ".join(recipients), sender))
    return sender
