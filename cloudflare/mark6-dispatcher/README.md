# Mark Six Cloudflare dispatcher

This Worker triggers the `Daily MarkSix Full Data Update` GitHub Actions
workflow once per hour through `workflow_dispatch`.

Cloudflare Cron Triggers use UTC. The configured `15 * * * *` schedule runs at
`:15` every hour in Hong Kong time as well.

## One-time setup

From this directory:

```bash
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler deploy
```

`GITHUB_TOKEN` must be a fine-grained GitHub token restricted to
`lew601/mark6-data` with `Actions: Read and write` permission. Do not commit
the token or put it in `wrangler.toml`.

After deployment, verify the Worker Cron Trigger is enabled in the Cloudflare
dashboard and run the Worker once manually if you want to test it immediately.

## Two independent triggers

The repository workflow also runs through GitHub's own schedule at `:45` HKT
as a fallback. Therefore the two schedulers are intentionally offset:

- Cloudflare: every hour at `:15` HKT
- GitHub Actions: every hour at `:45` HKT

If both triggers run in the same hour, the existing workflow concurrency group
serializes them and the second run exits without a commit when the data has not
changed.
