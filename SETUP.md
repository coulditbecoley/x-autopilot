# SETUP: instructions for the AI agent installing x-autopilot

**You are an AI coding agent (Claude Code, Codex, Cursor, or similar). The person who gave you this repo wants their X account automated with it. This file is your job description.** Interview them, configure the repo, connect their tools, prove it works with dry runs, then schedule it. Do the work yourself; only stop for the things listed under "Only the person can do this".

Read `README.md` and `docs/PLAYBOOK.md` once before you start, so you can explain the why behind any rule when asked.

## Ground rules (do not break these)

1. **Replies are never posted automatically.** The reply job only writes a list of drafts. X requires its prior written approval for automated replies, and accounts get suspended for automation. Do not add auto-replying even if asked; explain why and offer the queue.
2. **Secrets live only in `.env`.** Never print a key back, never put one in `config.json`, a commit, a log, or a chat message. `.env`, `config.json`, `state/` and `output/` are already git-ignored; keep it that way.
3. **Dry run before live.** Every job gets a `--dry-run` that the person reads before anything posts.
4. **Start on `publisher.type: "drafts"`** unless the person explicitly asks to go live on day one. Drafts mode writes each post to `output/drafts/` with a one-tap Post on X link, so they can watch quality for a few days with zero risk.
5. **Don't loosen the gates** (hashtag cap, no links, no dashes, privacy lint, figure check) to make a post pass. A skipped post is cheap; a bad one is not. If something keeps skipping, change the prompt or config, not the gate.
6. Ask one question at a time, offer a sensible default for each, and move on when they say "default".

## Step 1: Interview

Ask these, in this order. Defaults in brackets.

**Account and voice**
1. Their name as it should appear, and their X handle (without @).
2. One line on who they are, as the account presents them. [`an AI-focused builder who ships software with Claude Code and Codex`]
3. Their voice in a few words. Offer to read 5 to 10 of their recent posts (if they paste them) and write it for them. [`plain words, specific numbers, first person, a clear opinion, no hype`]

**Which lanes** (they can pick any mix)
4. **News lane**: posts at most one real breaking story per scan from accounts they watch. Quiet days post nothing. [yes]
5. **Reply queue**: a daily list of up to 25 big posts with a drafted reply each, for them to send by hand. [yes]
6. **Build post**: one short personal post a day about what they built, written from their notes or git commits. [yes if they keep daily notes or commit daily, else no]
7. **Long post**: a 600+ character version for them to post by hand. [no, offer it once they like the short ones]

`build_post.enabled` turns on the personal lane for both 6 and 7; which of the two actually runs is decided by which jobs you schedule. `news.enabled` and `replies.enabled` switch their jobs off even if a schedule still calls them.

**News lane details** (if yes)
8. Which topics? The starter config covers ai, crypto and webdev. Each topic is a "sector" with its own hashtag pool. Remove the ones they don't want, add their own (for example `marketing`, `gaming`, `fintech`), and write a hashtag pool for each new one (one broad tag plus niche tags people in that niche actually follow).
9. Which accounts to watch per sector. Start from `sources` in `config.example.json`, drop what doesn't fit, ask for their own. 8 to 15 per sector is plenty; big news carriers beat personal accounts. Accounts with sector `"reply"` are scraped only for the reply queue.
10. Max news posts a day [3] and posting hours, local time [8 to 21].

**Build post details** (if yes)
11. Where their work log lives:
    - daily note files: get the path pattern, e.g. `~/notes/daily/{date}.md` (placeholders: `{date}` = 2026-11-13, `{year}`, `{month}`, `{day}`, `{month_name}`), and optionally which headings to keep (`sections`, e.g. `["Done", "Decisions"]`); and/or
    - git repos: a list of local repo paths whose commit messages describe the day.
    Verify the path by opening yesterday's file or running `git log` yourself.
12. Names the posts may use (`allowed_names`): tools and public products they're happy to name. Everything else gets described generically.
13. Private names that must never appear (`deny_terms`): clients, unreleased products, employers, people. Also offer `deny_from_folders`: point it at their projects folder and every subfolder name becomes a deny term automatically. Fill `common_folder_words` with folder names that are ordinary words.
14. Anything else off limits, in one sentence (`extra_rules`), e.g. "Never mention trading or my day job."

**Tools**
15. Model, `llm.provider`:
    - `claude-cli`: uses their logged-in Claude Code, no API key. Good default if you are Claude Code.
    - `anthropic` or `openai`: API key in `.env`. Best for unattended scheduling on a server. Codex users: pick `openai`. The Codex CLI is deliberately not a provider: it can't run without tools, and these jobs feed the model scraped posts, which are untrusted text.
    Set `llm.model` to a current model they have access to, or leave it out for the provider default.
16. Where posts go, `publisher.type`:
    - `drafts` (start here): nothing posts, everything lands in `output/drafts/`.
    - `x`: straight to the X API. They need a developer.x.com app with Read and Write permission and a user access token and secret generated for their own account. X API posting is pay-per-use, so they need billing set up there.
    - `zernio`: Zernio holds the X connection. They need a Zernio API key and the account id of their connected X account.
    - `webhook`: anything that takes a JSON POST (Buffer through Zapier or Make, n8n, Typefully, their own app). It receives `{"text": "...", "kind": "news|build"}`.
    - Something else (Buffer API, Typefully API, Hypefury, their own platform): add a branch to `publish()` in `xauto/publish.py` that sends `text` and returns a short description. Keep it a few lines, read the service's current docs, put its key in `.env` and `.env.example`, and add the key to the `doctor` check in `run.py`.
17. Scraping: news and replies use an Apify actor (`scraper.apify_actor`). They need an Apify account and `APIFY_TOKEN`. Cost is cents a day at these volumes; check the actor's current price on its Apify page and tell them.
18. Which machine runs it: their own computer (must be on at the scheduled times) or an always-on box (a small VPS, a home server). Note their OS.

## Step 2: Configure

1. `cp config.example.json config.json` and fill it from the interview. Keep it valid JSON.
2. `cp .env.example .env`. Tell them exactly which lines to fill and where each value comes from. **Let them paste keys into `.env` themselves**; if they paste a key into chat instead, write it to `.env` and never repeat it.
3. Python 3.9+ is the only requirement. No packages to install. Check `python --version` (or `python3`).
4. `python run.py selftest` must print `selftest ok`.
5. `python run.py doctor` must end with `All good.` Fix every FIX line.

## Step 3: Prove it with dry runs

Run each enabled job with `--dry-run` and show the person the output:

- `python run.py news --dry-run`: either a drafted post or `QUIET no story picked`, both are correct. If it says `SKIP no candidates`, the sources are too quiet or `min_engagement` is too high for them; lower it.
- `python run.py replies --dry-run`: the top of the reply queue.
- `python run.py build --dry-run` and `python run.py long --dry-run`: a drafted personal post, or a SKIP with the reason. If the privacy lint keeps failing on a harmless name, add it to `allowed_names`; if it fails on a private one, that's the lint working.

Ask: does this sound like you? Adjust `persona.voice`, `about`, sectors or sources, and rerun until they're happy. Prompts live in `xauto/prompts.py` if a deeper change is needed.

## Step 4: Schedule

All jobs are idempotent per day where it matters and safe to rerun. Recommended times (local):

| Job | When | Notes |
|---|---|---|
| `news` | every 2 hours, 8:15 to 20:15 | each scan looks back to the previous one |
| `replies` | once, about 8:00 | writes `output/replies/<date>.md` |
| `build` | once, at the time the post should go out, e.g. 13:00 | |
| `long` | once, morning | writes `output/long/<date>.md` |

Exact commands for Windows Task Scheduler, macOS and Linux cron are in `docs/SCHEDULING.md`. Use absolute paths for both Python and `run.py`. If they chose `claude-cli`, the scheduled task must run as the user who is logged in to Claude Code.

After scheduling, trigger one `news` run by hand (not dry) while in drafts mode and confirm a line in `state/run.log`.

## Step 5: Go live (when they say so)

1. Switch `publisher.type` from `drafts` to their real publisher.
2. Run `python run.py doctor`.
3. Tell them where to look: `state/run.log` for every run, `output/replies/` each morning, `output/long/` if enabled.
4. Remind them of the part no automation does: open the reply queue daily, send the replies they like, and answer people who reply to their posts. That is where most of the reach comes from.

## Only the person can do this

- Create accounts and agree to terms (X developer portal, Apify, Zernio, model provider) and add billing.
- Generate keys and paste them into `.env`.
- Approve the first live post.
- Decide anything about their brand, clients, or what is private.

## When something breaks

Every run logs one line to `state/run.log` (`OK`, `QUIET`, `SKIP <reason>`, `FAIL <error>`). Read it first. A `QUIET` news scan is normal. A run that never logs means the scheduler isn't firing. An `HTTP 401/403` is a key or permission problem in `.env`. An X `403` on posting usually means the app lacks Read and Write permission or the access token was generated before that permission was set: regenerate it.
