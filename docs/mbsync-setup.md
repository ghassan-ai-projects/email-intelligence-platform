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
