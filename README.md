# PogoCache

Turn tagged emails into local Markdown notes — automatically.

Point this at a Gmail inbox, and any unread email whose subject contains a
trigger string (default `!pogo`) gets pulled down, converted into a
timestamped `.md` file, and dropped in a staging folder on your machine. Attachments
are saved alongside it — images are embedded inline using Obsidian-style
`![[filename]]` syntax, everything else is saved and referenced by name.
Useful as a lightweight "email-to-notes" pipeline for Obsidian, a personal
wiki, or any folder-based temporary note storage.

## Features

- Polls Gmail on a configurable interval (IMAP, read-only footprint)
- Only processes emails matching a trigger string in the subject
- Saves attachments: images, PDFs, docs, spreadsheets, audio, video, zip, plain text
- Images embedded inline; other files referenced by filename
- Filename-safe, collision-proof output (`_1`, `_2`, ... suffixes)
- Per-message error isolation — one bad email won't crash the run or block the rest
- Zero-config output folder — just point it anywhere

## Requirements

- Python 3.10+
- A Gmail account with 2-Step Verification enabled (required for App Passwords)

## Installation

```bash
git clone https://github.com/braydenboq/PogoCache.git
cd PogoCache
pip install -r requirements.txt
```

## Getting a Gmail App Password

Gmail won't accept your normal password for IMAP access from a script — you
need a dedicated App Password:

1. Turn on 2-Step Verification: <https://myaccount.google.com/signinoptions/two-step-verification>
2. Go to <https://myaccount.google.com/apppasswords>
3. Create a new App Password (name it something like "pogo-cache")
4. Copy the 16-character password — you'll only see it once

This password only works for IMAP/SMTP access and can be revoked anytime
from the same page, independent of your main Google password.

## Configuration

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable | Description | Default |
|---|---|---|
| `EMAIL_ADDRESS` | Gmail address to poll | *required* |
| `APP_PASSWORD` | Gmail App Password from the step above | *required* |
| `OUTPUT_FOLDER` | Where notes and attachments are written | `./pogo_inbox` |
| `POLL_INTERVAL` | Seconds between inbox checks | `60` |
| `TRIGGER` | Subject must contain this string to be collected | `!pogo` |

`.env` is gitignored — your credentials never get committed.

## Usage

```bash
python pogo_cache.py
```

Runs continuously, checking the inbox every `POLL_INTERVAL` seconds. Stop
with `Ctrl+C`.

For a single check-and-exit (useful for testing, or running via cron /
Task Scheduler instead of a long-lived loop):

```bash
python pogo_cache.py --once
```

## Output format

Each matching email becomes a file like:

```
2026-07-14_09-32_Grocery list.md
```

Containing:

```markdown
# Grocery list
Date: 2026-07-14 09:32

Body text of the email goes here.

![[2026-07-14_09-32_Grocery list.jpg]]
```

Emails without the trigger string are marked as read and skipped — they're
left untouched otherwise.

## Customization

All the tunables live at the top of `pogo_cache.py`:

- `ATTACHMENT_MIME_TYPES` — which MIME types are saved as attachments
- `IMAGE_EXTENSIONS` — which extensions get embedded inline vs. referenced
- `INLINE_TEXT_EXTENSIONS` — reserved for future use (currently `.md`/`.txt`
  attachments are saved and referenced the same as any other file type; kept
  as a separate set in case that behavior diverges later)

## Security notes

- Uses an App Password, not your real Gmail password — revoke it anytime
  without affecting your main account
- IMAP access only; the script never sends mail or modifies anything beyond
  marking processed messages as read
- Keep `.env` out of version control (already handled by `.gitignore`)

## License

MIT — do whatever you want with it.
