import httpx, os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

OWNER = "openai"
REPO = "openai-python"
PR_AGE_HOURS = 12

async def fetch_open_prs():
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls?state=open"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS)
        prs = resp.json()
        return prs

async def fetch_pr_status(client, sha):
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/commits/{sha}/status"
    resp = await client.get(url, headers=HEADERS)
    data = resp.json()
    return data.get("state", "unknown")

async def notify_slack(message):
    async with httpx.AsyncClient() as client:
        await client.post(SLACK_WEBHOOK_URL, json={"text": message})

async def check_and_alert():
    prs = await fetch_open_prs()
    now = datetime.now(timezone.utc)

    unreviewed = []
    failed_ci = []

    async with httpx.AsyncClient() as client:
        for pr in prs:
            created_at = datetime.strptime(pr["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_hours = (now - created_at).total_seconds() / 3600

            # Skip PRs that are fresh
            if age_hours < PR_AGE_HOURS:
                continue

            # Check for reviews
            reviews_url = pr["_links"]["self"]["href"] + "/reviews"
            reviews_resp = await client.get(reviews_url, headers=HEADERS)
            reviews = reviews_resp.json()

            if not reviews:
                unreviewed.append(pr)

            # Check CI status
            status = await fetch_pr_status(client, pr["head"]["sha"])
            if status == "failure":
                failed_ci.append(pr)

    msg_lines = []

    if unreviewed:
        msg_lines.append("*🚨 Unreviewed PRs (>{}h):*".format(PR_AGE_HOURS))
        for pr in unreviewed:
            msg_lines.append(f"- <{pr['html_url']}|{pr['title']}> by `{pr['user']['login']}`")

    if failed_ci:
        msg_lines.append("*❌ PRs with Failed CI:*")
        for pr in failed_ci:
            msg_lines.append(f"- <{pr['html_url']}|{pr['title']}> (CI: Failed)")

    if msg_lines:
        await notify_slack("\n".join(msg_lines))
    else:
        await notify_slack("✅ All clear! No unreviewed or failed PRs.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(check_and_alert())
