# Playbook: why every rule is there

This system was built by Claude Code, with Codex auditing the work, and ran on a real account before it was made general. Every rule below was either learned the hard way on that account or adopted from published research, and each one is labelled so you can tell which.

## 1. Generic AI posts don't work (learned)

The first version wrote posts from a topic list. They were well written and almost nobody read them. A model writing "insights" from a topic list produces what every other account already posts. That's why this repo has no "generate a post about topic X" job. Every post starts from something real: a news event, or your own work log.

## 2. News, and silence when there is none (learned)

Real news is what people react to. The radar posts at most one story per scan and the prompt says out loud that silence costs nothing. Quiet days post nothing, by design. An uncertain story is a no: the next scan can take it once it's clearer.

## 3. Write for the reply and the forward, not the like (adopted)

In August 2026 X open-sourced its ranking code. The weights reported from it at the time:

| Signal | Weight | What the prompts ask for |
|---|---|---|
| Share via copy link | 20.0 | a post you'd forward to one specific person, that stands alone |
| Reply | 5.0, 20.0 between mutual follows | end on a question someone can answer from experience in one line |
| Like | 0.5 | never write for the like |
| Report | -234.0 | no rage bait, no dunking, ever |
| Dwell time | scored, a fast scroll past is negative | the middle carries a fact the hook didn't give away |
| External link | demoted | no links in posts |

These are the reported weights from that release, not a guarantee of how X ranks today.

## 4. Hashtags: exactly 1 or 2, at the end (adopted, weakest evidence)

The research said three or more trips spam filtering and costs reach. The evidence that 1 or 2 help is thin; the evidence against 3+ is consistent. The cap is enforced in code (`clamp_tags`), not just the prompt, because a prompt rule already failed once on this account. If your reach drops, hashtags are the first thing to try removing.

## 5. Personal beats product (adopted)

From a builder's study of 6,000+ of his own posts: personal posts beat product posts about 2 to 1 in median likes, a concrete number helps, practical lists earn bookmarks, and the opening line should state the point instead of asking a question. Posts over 600 characters beat one-liners for him, which is where the long lane comes from. That's why the build post writes "I built, broke, learned, decided", never "my product now has feature X".

## 6. Every number must already exist (built in)

Models invent figures. The privacy lint fails any number in a personal post that isn't in your notes, and the humanizer pass is thrown away if it adds, drops or changes a figure or an @handle. News figures must be copied exactly from the source.

## 7. Privacy is code, not a prompt (built in)

The build post reads your own notes, which are full of client names and private details. The prompt asks the model to stay generic, and then code checks it anyway: deny list, folder names, anything that looks like a person's name, links, paths, ticket and commit ids, token-like strings. It fails closed. It is a strong filter, not a guarantee, so keep `deny_terms` current and read your first week of posts.

## 8. The humanizer can never cost a post (built in)

Every draft gets one rewrite pass to strip AI tells. If the rewrite breaks any check, the original gated draft is used. The pass makes posts better or does nothing.

## 9. Replies are where the reach is, and they stay manual (learned and policy)

Replying, and replying back to people who reply to you, carried some of the heaviest weights in the reported ranking code, and a small account's replies on big posts reach that post's audience. X requires prior written approval for automated replies, and one of the author's other accounts was suspended for automation. So the reply job drafts and you send. The queue is the most valuable output here and the one people skip most often.

## 10. Failures that look like success (lessons)

Things that happened on the original system, and what this repo does about them:

- **Two radars cancelled each other's posts.** Both matched scheduled posts by time slot only, not by account, so one account double posted and another lost its slot, and every run logged success. Here: nothing cancels or replaces posts at all; each run publishes or doesn't.
- **Generation stopped for 48 hours and no alert fired.** The model API was failing, and the alerting workflow itself had been switched off. Here: every run, including failures, writes a line to `state/run.log`, and `FAIL` lines are easy to grep or forward.
- **A retry posted the same post twice.** Here: the Zernio publisher sends an idempotency key, and the news lane records each story so the next scan can't repost it.
- **The publish time was computed before a slow scrape** and was in the past by the time it was used. Here: posts publish immediately at the end of the run.
- **A second AI auditing the first one's analysis overturned 6 of its claims**, including a "news gets 2x the views" conclusion drawn from six posts. Measure over weeks, not days, before changing what works.
