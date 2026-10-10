# mark6-data

## Automated data updates

The Mark Six crawler is triggered hourly by two independent schedulers:

- Cloudflare Worker at `:15` Hong Kong time, through GitHub
  `workflow_dispatch`;
- GitHub Actions schedule at `:45` Hong Kong time as a fallback.

The Cloudflare Worker source and deployment instructions are in
[`cloudflare/mark6-dispatcher/`](./cloudflare/mark6-dispatcher/). The
GitHub token is stored as a Cloudflare secret and must not be committed.