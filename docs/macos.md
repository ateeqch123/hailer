# Hailer on macOS

This is the setup for Hassan. Hailer watches Gmail accounts you have authorized and emails one address when a message looks like recruiter outreach or an automatic reply. The steps below are the ones the project actually implements.

## What must already be installed

- **Python 3.12 or newer.** `pyproject.toml` sets `requires-python = ">=3.12"`. On the Mac, check with `python3 --version`. If that is older than 3.12, install Python 3.12 or newer before the next section. The README writes `python`; on macOS the 3.12 binary is often `python3`. Use whichever command prints 3.12 or newer.
- **Git**, so you can clone the repository. Check with `git --version`. Hailer is installed from that checkout. There is no separate installer.

## Install Hailer

Clone the repository and install it into a virtual environment. `pip install .` installs the `hailer` command. `pip install -e ".[dev]"` is the other documented install: it installs the same command and also pytest.

```bash
git clone https://github.com/ateeqch123/hailer.git
cd hailer
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

Leave the virtual environment activated for the commands below. Run them from this `hailer` directory. `hailer.toml` and `client_secret.json` are read from the current directory unless you point elsewhere, as described later.

## Google Cloud

Do this once per Cloud project. Each Gmail account still consents separately.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, or pick an existing one.
2. Enable the Gmail API: [Gmail API library page](https://console.cloud.google.com/apis/library/gmail.googleapis.com). Click Enable.
3. Configure the OAuth consent screen: [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent).
   - User type **External** if the accounts are consumer Gmail or span more than one Workspace. User type **Internal** if every account is in the same Workspace organization.
   - App name, user support email, and developer contact email are required.
   - Add these scopes:
     - `https://www.googleapis.com/auth/gmail.readonly` (read metadata)
     - `https://www.googleapis.com/auth/gmail.send` (send the notification from `notify_from`)
   - While the app is in **Testing**, add every Gmail account as a test user. Google allows up to 100 test users. Hailer also stops at 100 accounts.
4. Create the client: [Credentials](https://console.cloud.google.com/apis/credentials) → Create credentials → OAuth client ID → Application type **Desktop app**. Download the JSON.
5. Save that download as `client_secret.json` in the `hailer` directory (the directory you run `hailer` from). You can keep it somewhere else and pass that path to `--client-secret`. `client_secret.json.example` shows the shape of the file. Do not commit the real file.

`hailer auth add` opens a browser on this Mac and listens on localhost for the redirect. The account owner signs in and clicks Allow.

Refresh tokens for an app that is still in Testing expire after 7 days. Run `hailer auth add` again for each account when that happens, or publish the app to Production. `gmail.readonly` and `gmail.send` are sensitive scopes. An External app in Production that other people use has to go through Google's verification. An Internal Workspace app does not. For your own accounts, Testing plus a weekly re-consent works without verification.

## Connect each Gmail account

One command is one Google consent. Repeat it for every account, up to 100. There is no bulk grant. Each account owner completes the consent screen.

```bash
hailer auth add --client-secret ./client_secret.json
```

`--client-secret` defaults to `./client_secret.json`, so `hailer auth add` is the same command when that file is in the current directory.

A successful run prints `Connected <email>.` and reminds you to repeat the command for each account. Run it again for an account you already connected when you need a new token (for example after the 7-day Testing expiry). That replaces the token file for that address.

See what is connected:

```bash
hailer auth list
```

That prints one email per line. With no accounts yet, it prints `No connected accounts.`

## hailer.toml

```bash
cp config.example.toml hailer.toml
```

Edit `hailer.toml`. These are the only fields Hailer reads:

```toml
notify_to = "sam@example.com"
notify_from = "sam.watch@gmail.com"
concurrency = 10
```

Replace the example addresses with yours.

- `notify_to` is the address that receives one email per new recruiter or autoreply hit. Required.
- `notify_from` is the authorized Gmail account that sends those emails. Required. It must appear in `hailer auth list`.
- `concurrency` is how many accounts to poll at once. Optional. If you omit it, Hailer uses 10. It must be an integer of at least 1.

The default config path is `./hailer.toml`. `HAILER_CONFIG` overrides that path. There is no config-file flag.

```bash
HAILER_CONFIG=/path/to/hailer.toml hailer check
```

Do not commit `hailer.toml` if the addresses are private.

## Check mail

Dry-run classifies and prints actions. It does not send mail and does not write the dedup database. It still needs a valid `hailer.toml`, and `notify_from` still has to be an authorized account.

```bash
hailer check --dry-run
```

Send for real:

```bash
hailer check
```

`--concurrency` overrides the `concurrency` field for that run. It must be an integer of at least 1. This example polls 4 accounts at a time:

```bash
hailer check --concurrency 4
```

A dry-run line looks like:

```text
dry-run label=recruiter account=sam.watch@gmail.com message_id=18d2f0ab12c3ef45 from=Jordan Lee <jordan@greenhouse.io> subject=Interview for backend engineer
```

A real run prints `notified` instead of `dry-run`. A later poll that sees the same Gmail message id prints `skip-duplicate`. If no accounts are connected, `hailer check` prints `No connected accounts. Run hailer auth add for each Gmail account.`

## Where tokens are stored

Hailer does not ask for a Gmail password, an app password, or IMAP settings. It does not connect to an account that has not granted OAuth. Access is the Gmail API after that account owner approves Google's consent screen.

Each account's token is one file:

```text
~/.local/share/hailer/tokens/<email>.json
```

On macOS that is still under your home directory's `.local` folder, not `~/Library/Application Support`. `hailer auth add` creates the directory (mode `0700`) and writes the token file (mode `0600`). `HAILER_TOKEN_DIR` overrides the token directory if you set it.

The dedup database, which stops the same Gmail message id from being notified twice for one account, is `~/.local/share/hailer/notified.db`. `HAILER_STATE_DB` overrides that path. Dry-run does not write it.
