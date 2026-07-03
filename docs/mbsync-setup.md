# mbsync (isync) setup

mailintel treats a local **Maildir** as the immutable source of truth and uses
[mbsync](https://isync.sourceforge.io/) to keep it in sync with your IMAP account.

```sh
brew install isync        # macOS
# apt install isync       # Debian/Ubuntu
```

## Generic IMAP account

`~/.mbsyncrc`:

```
IMAPAccount work
Host imap.example.com
User you@example.com
# Read the password from a command instead of storing it in the file:
PassCmd "security find-generic-password -s mbsync-work -w"   # macOS Keychain
TLSType IMAPS

IMAPStore work-remote
Account work

MaildirStore work-local
Path ~/Mail/
Inbox ~/Mail/INBOX
SubFolders Verbatim

Channel work
Far :work-remote:
Near :work-local:
Patterns *
Create Near
Expunge Near
SyncState *
```

Store the password in the macOS Keychain once:

```sh
security add-generic-password -s mbsync-work -a you@example.com -w
```

## Credentials from .env

mailintel automatically loads `~/.mailintel/.env` (and `./.env`) before running
mbsync, so you can keep mail credentials there instead of the Keychain:

```sh
# ~/.mailintel/.env  — chmod 600 this file
EMAIL_USER=you@gmx.de
EMAIL_PASSWORD=your-password
DEEPSEEK_API_KEY=...
VOYAGE_API_KEY=...
```

and reference it in `~/.mbsyncrc` with:

```
PassCmd "echo $EMAIL_PASSWORD"
```

This works whenever mbsync is started by mailintel (`mailintel sync` / `watch` /
the `sync_now` MCP tool). If you run `mbsync` manually, export the variables
first (`set -a; source ~/.mailintel/.env; set +a`).

## GMX (gmx.de / gmx.net)

First enable IMAP in the GMX web interface:
**Einstellungen → POP3/IMAP Abruf → "POP3 und IMAP Zugriff erlauben"** — without
this, logins fail even with the right password.

```
IMAPAccount gmx
Host imap.gmx.net
Port 993
User you@gmx.de
PassCmd "echo $EMAIL_PASSWORD"
TLSType IMAPS

IMAPStore gmx-remote
Account gmx

MaildirStore gmx-local
Path ~/Mail/
Inbox ~/Mail/INBOX
SubFolders Verbatim

Channel gmx
Far :gmx-remote:
Near :gmx-local:
Patterns *
Create Near
Expunge Near
SyncState *
```

Notes:
- GMX folder names are German: `Gesendet` (sent), `Papierkorb` (trash),
  `Entwürfe` (drafts). mailintel's defaults already treat `Gesendet` as sent
  mail and exclude `Papierkorb`/`Entwürfe`/`Spam`.
- For **sending** through GMX (the `send_email` MCP tool): `mail.gmx.net`,
  port 587, STARTTLS — see the `[smtp]` block in `config.example.toml`. Sending
  must also be enabled in the GMX settings if you use an app-specific password.
- Free GMX accounts throttle IMAP polling; a `sync.interval_minutes` of 5–10 is
  safe.

## Gmail

Gmail needs an [app password](https://myaccount.google.com/apppasswords)
(requires 2FA) and benefits from excluding the "All Mail" duplicate view:

```
IMAPAccount gmail
Host imap.gmail.com
User you@gmail.com
PassCmd "security find-generic-password -s mbsync-gmail -w"
TLSType IMAPS

IMAPStore gmail-remote
Account gmail

MaildirStore gmail-local
Path ~/Mail/
Inbox ~/Mail/INBOX
SubFolders Verbatim

Channel gmail
Far :gmail-remote:
Near :gmail-local:
Patterns * ![Gmail]* "[Gmail]/Sent Mail"
Create Near
Expunge Near
SyncState *
```

Notes:
- `![Gmail]*` skips All Mail / Important / Starred (duplicates); Sent Mail is
  re-included so mailintel can detect threads waiting for replies.
- mailintel already excludes Trash/Spam/Junk/Drafts at ingest time (configurable
  in `[maildir] exclude_folders`).

## First sync and verify

```sh
mkdir -p ~/Mail
mbsync -a                 # first run downloads everything; can take a while
mailintel ingest
mailintel stats
```

After that, `mailintel sync` (one shot) or `mailintel watch` (continuous) runs
mbsync + ingest + enrichment for you.
