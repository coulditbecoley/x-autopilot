# x-autopilot

Automate an X account in your niche, from the news sources you pick, in your own voice, without it sounding like a bot. Built by Claude Code for [@coulditbecoley](https://x.com/coulditbecoley) and made general so anyone can run it. Why each rule exists: [docs/PLAYBOOK.md](docs/PLAYBOOK.md).

**Easiest setup: give this repo to your AI coding agent.** Clone it, open Claude Code or Codex in the folder, and say:

> Read SETUP.md and set this up for me.

It interviews you (your voice, topics, accounts to watch, where your notes live, which tools you use), configures everything, runs dry runs for you to approve, and schedules the jobs.

## What it does

| Job | What happens | Posts automatically? |
|---|---|---|
| `news` | Scans the X accounts you watch every couple of hours. If one real story broke, writes one post about it in your voice, with a take and a question. Most scans post nothing. | yes |
| `replies` | Each morning, picks up to 25 fast-moving big posts and drafts a reply to each, with a one-tap "Reply on X" link. | **never**, you send them |
| `build` | Writes one short post a day about what you actually built, from your daily notes or git commits, then runs a privacy check before it goes anywhere. | yes |
| `long` | Same, as a 600 to 2,200 character post with a practical list and two backup hooks. | no, you post it |

Every draft passes through code checks after the model: 1 or 2 hashtags at the end, no links, no em dashes, a closing question on news posts, no invented numbers, and (for personal posts) no private names. Then one humanizer pass that is thrown away if it breaks anything.

## Plug in your own tools

- **Model:** Anthropic API, OpenAI API, or your logged-in **Claude Code** (no API key needed, runs with every tool off). Codex users: use the OpenAI API. Either agent can do the setup.
- **Posting:** X API directly, Zernio, any webhook (Buffer via Zapier or Make, n8n, your own app), or **drafts** mode where nothing posts and you get a file of ready-to-post links. Adding another tool is one small function; SETUP.md tells your agent how.
- **Scraping:** an Apify actor, cents a day at this volume.

Standard library Python 3.9+. Nothing to `pip install`.

## Manual setup

```bash
cp config.example.json config.json   # edit persona, sectors, sources, lanes
cp .env.example .env                 # add the keys your config needs
python run.py selftest               # offline checks
python run.py doctor                 # checks keys and the model connection
python run.py news --dry-run         # see what it would post
```

Then schedule the jobs: [docs/SCHEDULING.md](docs/SCHEDULING.md). Config fields are explained in [SETUP.md](SETUP.md), step 1.

## What it costs

- Model: a few calls per scan with a story, one per quiet scan. With a CLI provider it uses your existing subscription.
- Scraping: an Apify pay-per-result actor; check its current price on Apify.
- Posting: X API posting is pay-per-use; Zernio and webhook tools have their own pricing. Drafts mode is free.

## Rules it will not break

- **No automated replies.** X requires its written approval for those, and accounts get suspended for automation.
- **No secrets in the repo.** Keys live in `.env`, which is git-ignored with your config, state and output.
- **Silence over filler.** A quiet news day posts nothing. A personal post that fails the privacy check skips the day.

You are responsible for what your account posts and for following X's rules. Start in drafts mode and read a week of output before going live.

## Credits

Built with Claude Code, audited with Codex. Writing rules adapted from X's open-sourced ranking code (August 2026) and a public study of 6,000+ posts by a large indie-builder account. See [docs/PLAYBOOK.md](docs/PLAYBOOK.md).

MIT licensed.
