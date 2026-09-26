# hailer

hailer watches Gmail accounts you have authorized and emails one address when a message looks like recruiter outreach or an automatic reply.

Access is the Gmail API through OAuth. Each account owner approves Google's consent screen. hailer does not ask for a Gmail password, an app password, or IMAP settings, and it does not connect to an account that has not granted OAuth.

## Install

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`pip install -e ".[dev]"` installs the `hailer` command and pytest. Use `pip install .` if you only want the command.

## Google Cloud setup

Do this once per Cloud project. You then consent once per Gmail account.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, or pick an existing one.
2. Enable the Gmail API: [Gmail API library page](https://console.cloud.google.com/apis/library/gmail.googleapis.com). Click Enable.
3. Configure the OAuth consent screen: [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent).
   - User type **External** if the accounts are consumer Gmail or span more than one Workspace. User type **Internal** if every account is in the same Workspace organization.
   - App name, user support email, and developer contact email are required.
   - Add these scopes:
     - `https://www.googleapis.com/auth/gmail.readonly` (read metadata)
     - `https://www.googleapis.com/auth/gmail.send` (send the notification from `notify_from`)
   - While the app is in **Testing**, add every Gmail account as a test user. Google allows up to 100 test users. hailer also stops at 100 accounts.
4. Create the client: [Credentials](https://console.cloud.google.com/apis/credentials) → Create credentials → OAuth client ID → Application type **Desktop app**. Download the JSON.
5. Save that download as `client_secret.json` next to where you run hailer (or pass another path to `--client-secret`). Start from `client_secret.json.example` if you want to see the shape. Do not commit the real file.

`hailer auth add` opens a browser on this machine and listens on localhost for the redirect. The account owner signs in and clicks Allow. Repeat that command for every account. One hundred accounts means one hundred consents. There is no bulk grant.

Refresh tokens for an app that is still in Testing expire after 7 days. Run `hailer auth add` again for each account when that happens, or publish the app to Production. `gmail.readonly` and `gmail.send` are sensitive scopes. An External app in Production that other people use has to go through Google's verification. An Internal Workspace app does not. For your own accounts, Testing plus a weekly re-consent works without verification.

### Quotas

Google's published Gmail API costs (see [Quota units](https://developers.google.com/gmail/api/reference/quota)):

| Method | Units |
| --- | --- |
| `users.messages.list` | 5 |
| `users.messages.get` | 5 |
| `users.messages.send` | 100 |
| `users.getProfile` | 1 |

The default project cap is 1,000,000,000 units per day. The per-user rate limit is 15,000 units per user per minute. Confirm the current numbers in Cloud Console; Google changes them.

One poll of an account is one list plus up to 25 gets: 130 units. One hundred accounts is about 13,000 units, spread across users, which is under the per-user limit. Notifications are the tighter constraint. Each one costs 100 units and they all send as `notify_from`. One hundred sends in a minute is 10,000 units on that single user. Consumer Gmail also has its own send cap (500 messages a day is the usual published figure; Workspace is higher). `--concurrency` defaults to 10 so reads do not all start at once.

## Configure

```bash
cp config.example.toml hailer.toml
```

`hailer.toml`:

```toml
notify_to = "sam@example.com"
notify_from = "sam.watch@gmail.com"
concurrency = 10
```

- `notify_to` receives one email per new recruiter or autoreply hit.
- `notify_from` is the authorized account that sends those emails. It must appear in `hailer auth list`.
- `concurrency` is how many accounts to poll at once. Default 10. `hailer check --concurrency` overrides it.

The default config path is `./hailer.toml`. `HAILER_CONFIG` overrides it:

```bash
HAILER_CONFIG=/etc/hailer/hailer.toml hailer check
```

Tokens are stored one file per account in `~/.local/share/hailer/tokens/<email>.json` (mode `0600`). The dedup database is `~/.local/share/hailer/notified.db`. Override those with `HAILER_TOKEN_DIR` and `HAILER_STATE_DB`. Do not commit tokens, `client_secret.json`, or `hailer.toml`.

## Commands

Connect `sam.watch@gmail.com`, then the second inbox. Each command is one Google consent:

```bash
hailer auth add --client-secret ./client_secret.json
hailer auth add --client-secret ./client_secret.json
hailer auth list
```

`hailer auth list` prints one email per line:

```text
other.inbox@gmail.com
sam.watch@gmail.com
```

See what would be sent, then send for real:

```bash
hailer check --dry-run
hailer check
hailer check --concurrency 4
```

Dry-run still requires a valid config, and `notify_from` still has to be an authorized account. It classifies and prints actions. It does not send mail and does not write the dedup database.

A dry-run line looks like:

```text
dry-run label=recruiter account=sam.watch@gmail.com message_id=18d2f0ab12c3ef45 from=Jordan Lee <jordan@greenhouse.io> subject=Interview for backend engineer
```

A real run prints `notified` instead of `dry-run`. A later poll that sees the same Gmail message id prints `skip-duplicate`.

## What a check does

1. Load every token file (at most 100).
2. Poll the accounts on a thread pool. Default concurrency is 10.
3. For each account, call `users.messages.list` with `q=is:unread in:inbox` and `maxResults=25`.
4. For each id, call `users.messages.get` with `format=metadata` and these headers: `From`, `Subject`, `Date`, `Auto-Submitted`, `Precedence`, `List-Id`, plus `X-Hailer`.
5. Classify. On `recruiter` or `autoreply`, send one mail as `notify_from` through `users.messages.send`, then record `(account, message id)` in sqlite.

The notification body contains the receiving account, the classification, the From header, the subject, and the Gmail message id. It does not contain the message body. Example:

```text
Subject: [hailer] recruiter on sam.watch@gmail.com: Interview for backend engineer

Hailer classified a Gmail message.

Account: sam.watch@gmail.com
Classification: recruiter
From: Jordan Lee <jordan@greenhouse.io>
Subject: Interview for backend engineer
Gmail message id: 18d2f0ab12c3ef45
```

Messages hailer itself sent (header `X-Hailer: notification`, or a subject that starts with `[hailer]`) are ignored, so an alert that mentions "recruiter" is not treated as a new recruiter email.

Dedup is per account and Gmail message id. The same id in two mailboxes can notify twice, once for each mailbox. A failed send is not recorded, so the next poll tries again.

## Classification

`classify()` in `src/hailer/classify.py` is a pure function. It does not use the network. Autoreply is decided first, so an out-of-office note is never also a recruiter hit.

**autoreply** when either is true:

- `Auto-Submitted` is present and, after trimming and lower-casing, is not `no` (for example `auto-replied` or `auto-generated`).
- The subject or snippet contains one of: `out of office`, `out-of-office`, `automatic reply`, `automatic response`, `auto-reply`, `auto reply`, `autoreply`, `away from the office`, `away from office`, `on vacation`, `i am currently out`, `i'm currently out`, `this is an automatic`.

The snippet is optional. Headers are enough when `Auto-Submitted` is set.

**recruiter** when it is not an autoreply and either is true:

- The From address domain is, or is a subdomain of, `greenhouse.io`, `lever.co`, `linkedin.com`, `indeed.com`, `ashbyhq.com`, or `myworkday.com`. `jobs.greenhouse.io` matches. `notgreenhouse.io` and `greenhouse.io.evil.com` do not. The display name is not the domain.
- The subject or snippet contains `recruiter`, `opportunity`, `interview`, or `hiring`, or the plurals `recruiters`, `opportunities`, and `interviews`. Matching is case-insensitive and uses word boundaries, so `preinterview` does not match.

**ignore** is everything else.

`Date`, `Precedence`, and `List-Id` are fetched and kept on the message. They do not change the label. A mailing list is ignore unless it also matches the rules above. `linkedin.com` matches the domain rule even when the note is not from a recruiter.

## Logs

Logs use account id, message id, and the label only:

```text
INFO hailer account=sam.watch@gmail.com message_id=18d2f0ab12c3ef45 label=recruiter
```

The subject, snippet, and body are not logged. Stdout from `hailer check` still prints From and subject so you can see the action.

## Tests

```bash
python -m pytest
```

The tests use fake Gmail clients. They do not call Google. Classifier, dedup store, and poll orchestration are covered offline.

GitHub Actions (`.github/workflows/test.yml`) runs on push and pull request to `main`, on Python 3.12, with `pip install -e ".[dev]"` and `python -m pytest`.
