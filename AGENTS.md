# For AI agents

If you were asked to set up, install or configure this repo, follow [SETUP.md](SETUP.md) from the top.

If you were asked to change it:
- Python standard library only. No new dependencies.
- Code layout: `run.py` (CLI, selftest, doctor), `xauto/radar.py` (news, replies), `xauto/buildpost.py` (personal posts), `xauto/gates.py` (every mechanical check), `xauto/prompts.py` (every prompt), `xauto/publish.py` (where posts go), `xauto/llm.py` (model providers), `xauto/core.py` (config, state, log).
- Run `python run.py selftest` after any change to a gate, and add an assert for new gate behaviour.
- Never add automated replying, never weaken a gate to make a post pass, never write a secret anywhere but `.env`.
