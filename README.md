# keep-sync

Fast Google Keep capture and search on macOS. A Python service syncs Keep in the background. A Raycast extension reads and writes only local files, so it never waits on the network.

## Setup

Requires macOS, [uv](https://docs.astral.sh/uv/), Node, and Raycast.

```sh
cd service && uv sync
uv run keep-sync setup    # asks for your email and oauth_token cookie, stores the token in Keychain, starts the launchd agent
cd ../raycast && npm install && npm run dev
```

To get the `oauth_token` cookie:

1. Open [accounts.google.com/EmbeddedSetup](https://accounts.google.com/EmbeddedSetup) and sign in.
2. In DevTools, go to Application > Cookies and copy the value of `oauth_token`.

The cookie works for a few minutes only, so run `setup` soon.

## Use

- **New Keep Note**: type and submit. The window closes at once.
- **Search Keep Notes**: search, copy, edit, and delete.
- `keep-sync status`: sync time, error, and queue counts. Log: `~/Library/Logs/keep-sync.log`.
- `keep-sync uninstall [--purge]`: remove the agent. `--purge` also removes the token and data.

## Develop

```sh
cd service && uv run pytest
cd raycast && npm test && npm run typecheck && npm run lint
```

After you change the service, restart the agent to load the new code.

```sh
launchctl kickstart -k gui/$(id -u)/local.keep-sync
```
