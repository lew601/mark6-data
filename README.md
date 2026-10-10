# mark6-data

## Automated data updates

The Mark Six crawler is triggered hourly by two independent schedulers:

- Cloudflare Worker every hour at `:35` Hong Kong time, plus retries at
  `21:45` and `21:50`, through GitHub `workflow_dispatch`;
- GitHub Actions has the same schedule as a fallback.

The Cloudflare Worker source and deployment instructions are in
[`cloudflare/mark6-dispatcher/`](./cloudflare/mark6-dispatcher/). The
GitHub token is stored as a Cloudflare secret and must not be committed.