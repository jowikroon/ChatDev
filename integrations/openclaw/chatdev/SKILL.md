---
name: chatdev
description: Let a ChatDev 2.0 team of AI agents build something (a small app, website, game, script, research report or data visualisation) on Hans' ChatDev server and bring back the result. Use when Hans asks to "laat ChatDev ...", wants a multi-agent build or research run, or asks which ChatDev workflows exist.
metadata: {"openclaw": {"requires": {"bins": ["python"]}}}
---

# ChatDev

ChatDev runs on Hans' VPS at https://chatdev.hansvanleeuwen.com. You talk to it through one script:

`python "{{CLIENT}}" <command>`

Credentials live in `~/.openclaw/chatdev.env` (written by the installer from the vault). Never print, copy or ask for them.

## Commands
- Check the server: `python "{{CLIENT}}" health` (expect `{"status": "healthy"}`)
- List workflows: `python "{{CLIENT}}" workflows`
- What a workflow does: `python "{{CLIENT}}" describe <workflow.yaml>`
- Run it: `python "{{CLIENT}}" run <workflow.yaml> "<task in plain words>" --out "{{OUT}}"`
  Progress goes to stderr, the answer to stdout (`session_id`, `token_usage`, `final_message`, `zip`).
- Fetch a result again later: `python "{{CLIENT}}" download <session_id> --out "{{OUT}}"`

## Which workflow
- Software, small apps, websites: `ChatDev_v1.yaml`
- Games: `GameDev_with_manager.yaml`
- Research with sources: `deep_research_v1.yaml`
- Charts from data: `data_visualization_enhanced_v3.yaml`
- General problem solving: `general_problem_solving_team.yaml`
Unsure: run `workflows` and `describe` first. Do not pick `demo_*` workflows unless Hans asks.

## How to work
1. Restate the task in one or two concrete sentences (what, for whom, must-haves). Ask only if the goal is unclear.
2. Run `health`. If it fails, report the exact error and stop.
3. Start `run`. A run takes several minutes and costs model tokens: one run per request, no retry loops.
4. Report: what was built, where the zip is, token usage, and anything the final message says is missing.
5. Never claim a run succeeded without a `final_message`. "Stream ended without a result" means the server may still be busy: wait a few minutes, then `download <session_id>`.

## Errors
- `refused access (401/403)`: the service token in `chatdev.env` is wrong or rotated. Tell Hans to rerun the installer.
- `429` / `insufficient_quota` in the message: the model account behind ChatDev has no credit. Tell Hans; do not retry.
- `Cannot reach`: the VPS or tunnel is down. Report it and stop.
