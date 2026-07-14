"""
PogoCache
----------
Polls a Gmail inbox for unread messages whose subject contains a trigger
string, then writes each matching message to a local folder as a Markdown
note. Attachments are saved alongside the note; images are embedded with
Obsidian-style ![[filename]] syntax, everything else is referenced by name.

See README.md for setup instructions.
"""

import os
import sys
import time
import re
import email
import email.utils
import email.message
import imaplib
from email.header import decode_header
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration (from .env — see .env.example)
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and fill in your values."
        )
    return value


EMAIL_ADDRESS = _require_env("EMAIL_ADDRESS")
APP_PASSWORD = _require_env("APP_PASSWORD")
OUTPUT_FOLDER = Path(os.environ.get("OUTPUT_FOLDER", "./pogo_inbox")).expanduser().resolve()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
TRIGGER = os.environ.get("TRIGGER", "!pogo")

# MIME types treated as attachments worth saving
ATTACHMENT_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
    "application/pdf",
    "video/mp4", "video/quicktime",
    "audio/mpeg", "audio/mp4",
    "text/plain", "text/markdown", "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip", "application/x-zip-compressed",
}

# Extensions saved as files but referenced by name only (not inlined as content)
INLINE_TEXT_EXTENSIONS = {".md", ".txt"}

# Extensions embedded inline as images using ![[filename]] syntax
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decode_str(value: str) -> str:
    """Decode a MIME-encoded email header (subject, filename, etc.)."""
    parts = decode_header(value)
    result = ""
    for part, encoding in parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="replace")
        else:
            result += part
    return result


def safe_filename(subject: str) -> str:
    """Strip characters that are illegal in filenames on Windows/macOS/Linux."""
    subject = subject.strip() or "untitled"
    subject = re.sub(r'[<>:"/\\|?*]', "", subject)
    return subject[:80]


def unique_path(path: Path, reserved: set = None) -> Path:
    """
    Return `path` unchanged if it doesn't exist on disk AND isn't already
    reserved for use in this same operation, otherwise append _1, _2, etc.

    `reserved` lets callers track filenames already claimed in this run but
    not yet written to disk (e.g. the note's own path, decided before any
    attachments are written), so two files in the same batch can't collide.
    """
    reserved = reserved or set()

    def taken(p: Path) -> bool:
        return p.exists() or p in reserved

    if not taken(path):
        return path

    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not taken(candidate):
            return candidate
        counter += 1


def extract_parts(msg: email.message.Message) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Walk a (possibly multipart) email message.

    Returns:
        body        — plain text body
        attachments — list of (filename, raw_bytes)
    """
    body = ""
    attachments: list[tuple[str, bytes]] = []

    if not msg.is_multipart():
        charset = msg.get_content_charset() or "utf-8"
        try:
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
        return body, attachments

    for part in msg.walk():
        ct = part.get_content_type()
        cd = str(part.get("Content-Disposition", ""))

        has_filename = bool(part.get_filename())
        is_explicit_attachment = "attachment" in cd

        # Plain text body: only the first bare text/plain part with no
        # filename and no explicit attachment marker. This excludes things
        # like an iPhone's throwaway "Sent from my iPhone" alt-part being
        # mistaken for a real attachment.
        if ct == "text/plain" and not is_explicit_attachment and not has_filename and not body:
            charset = part.get_content_charset() or "utf-8"
            try:
                body = part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                pass
            continue

        # Real attachments: must have a filename OR be explicitly marked
        # Content-Disposition: attachment, and match a known MIME type
        # (or be explicitly marked regardless of type).
        if (has_filename or is_explicit_attachment) and (
            ct in ATTACHMENT_MIME_TYPES or is_explicit_attachment
        ):
            raw = part.get_payload(decode=True)
            if not raw:
                continue
            fname = part.get_filename()
            if fname:
                fname = decode_str(fname)
            else:
                ext = ct.split("/")[-1].replace("jpeg", "jpg")
                fname = f"attachment.{ext}"
            attachments.append((fname, raw))

    return body, attachments


def write_note(subject: str, body: str, attachments: list, date: datetime) -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    timestamp = date.strftime("%Y-%m-%d_%H-%M")
    safe_subj = safe_filename(subject)
    md_path = unique_path(OUTPUT_FOLDER / f"{timestamp}_{safe_subj}.md")

    # Reserve the note's path immediately so attachment filenames computed
    # below can never collide with it, even before it's written to disk.
    reserved_paths = {md_path}

    attachment_lines = ""
    for orig_fname, raw_bytes in attachments:
        ext = Path(orig_fname).suffix or ".bin"
        att_path = unique_path(
            OUTPUT_FOLDER / f"{timestamp}_{safe_subj}{ext}", reserved=reserved_paths
        )
        reserved_paths.add(att_path)

        try:
            att_path.write_bytes(raw_bytes)

            if ext.lower() in IMAGE_EXTENSIONS:
                attachment_lines += f"\n![[{att_path.name}]]\n"
            else:
                attachment_lines += f"\n{att_path.name} downloaded\n"

            print(f"  \u2713 Attachment saved: {att_path.name}")
        except Exception as e:
            print(f"  \u2717 Failed to save attachment '{orig_fname}': {e}")

    content = (
        f"# {safe_subj}\n"
        f"Date: {date.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"{body.strip()}\n"
        f"{attachment_lines}"
    )
    md_path.write_text(content, encoding="utf-8")
    print(f"  \u2713 Note written: {md_path.name}")


def check_mail(mail: imaplib.IMAP4_SSL) -> None:
    mail.select("inbox")
    status, messages = mail.search(None, "UNSEEN")
    if status != "OK" or not messages[0]:
        return

    ids = messages[0].split()
    print(f"  {len(ids)} new message(s)")

    for uid in ids:
        try:
            _, data = mail.fetch(uid, "(RFC822)")
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_str(msg.get("Subject", "untitled"))

            if TRIGGER not in subject:
                print(f"  \u2013 Skipped (no trigger): {subject}")
                mail.store(uid, "+FLAGS", "\\Seen")
                continue

            date_str = msg.get("Date", "")
            try:
                date = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()

            clean_subject = subject.replace(TRIGGER, "").strip() or "untitled"
            body, attachments = extract_parts(msg)
            write_note(clean_subject, body, attachments, date)
            mail.store(uid, "+FLAGS", "\\Seen")

        except Exception as e:
            print(f"  \u2717 Error processing UID {uid}: {e}")
            # Deliberately not marked read, so it retries next poll.


def run(once: bool = False) -> None:
    print(f"PogoCache running \u2014 checking every {POLL_INTERVAL}s")
    print(f"Trigger: '{TRIGGER}'")
    print(f"Writing to: {OUTPUT_FOLDER}\n")

    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking mail...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_ADDRESS, APP_PASSWORD)
            check_mail(mail)
            mail.logout()
        except Exception as e:
            print(f"  \u2717 Connection error: {e}")

        if once:
            break
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run(once="--once" in sys.argv)