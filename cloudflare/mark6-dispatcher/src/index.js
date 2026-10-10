const GITHUB_API_VERSION = "2022-11-28";

export default {
  async scheduled(controller, env) {
    const workflowPath = env.GITHUB_WORKFLOW_PATH || "daily-fetch.yml";
    const owner = env.GITHUB_OWNER || "lew601";
    const repository = env.GITHUB_REPOSITORY || "mark6-data";
    const dispatchUrl =
      `https://api.github.com/repos/${owner}/${repository}` +
      `/actions/workflows/${workflowPath}/dispatches`;

    const response = await fetch(dispatchUrl, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "mark6-cloudflare-dispatcher",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
      },
      body: JSON.stringify({ ref: "main" }),
    });

    if (!response.ok) {
      const responseBody = await response.text();
      throw new Error(
        `GitHub workflow dispatch failed (${response.status}): ${responseBody}`,
      );
    }

    console.log(
      JSON.stringify({
        event: "workflow_dispatch",
        workflow: workflowPath,
        repository: `${owner}/${repository}`,
        scheduledTime: new Date(controller.scheduledTime).toISOString(),
        cron: controller.cron,
      }),
    );
  },
};
