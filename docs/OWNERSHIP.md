# Ownership

This is the team's ownership table. It is not an enforced `.github/CODEOWNERS` file. GitHub Free only enforces code owners on public repositories, and that file can wait. Until then, "one review from outside the pair" is the team rule.

Ownership means: this person reviews changes on the path and keeps it working. It does not mean they are the only person who may edit it. Last matching row wins when two rows overlap, same as CODEOWNERS.

GitHub usernames are not filled in yet. Replace the names with real logins when the team adds a CODEOWNERS file.

| Path | Owners | Notes |
| --- | --- | --- |
| `*` | Mihir | Architecture, docs, CI/CD, security review |
| `/docs/` | Mihir | Gameplan, ADRs, later legal notes and release notes |
| `/infra/` | Mihir | Local runtime notes. Workflows are a later branch |
| `/compose.yaml` | Mihir | Our app only. Isolated from Zetaris |
| `/tasks.py` | Mihir | Task runner. `zetaris-sync` behaviour is Urvashi's |
| `/ingestion/` | Urvashi, Saleeta | Prep, footprints, portfolio, seed content |
| `/zetaris/` | Urvashi | Migrations, sync, views |
| `/scripts/zetaris_sync.py` | Urvashi | The one sync command |
| `/agents/` | Ayush, Zain | Nightshift, graph, memory |
| `/agents/floodsense_agents/hitl.py` | Zain | Approval interrupt and checkpointer |
| `/agents/floodsense_agents/nodes/judge.py` | Zain, Mihir | LLM-as-a-Judge |
| `/api/` | Zain, Ayush | Runs, SSE, approval; cache is Ayush's |
| `/ui/` | Mihir, Zain | Mihir until LangGraph and HITL are done, then Zain |
| `/pgvector/` | Urvashi | Optional citation store. Ayush on embeddings |
| `/evals/` | Saleeta, Zain, Mihir | Not in the skeleton yet. Ahr/NRW 2021 and Valencia 2024 |
| `/demo/` | Saleeta | Not in the skeleton yet. Deck, script, video |

Planned paths that have no folder yet (`contracts/`, `knowledge/`, `engines/`, `evals/`, `demo/`, `.github/`) follow the same owners when they appear. See [GAMEPLAN.md](GAMEPLAN.md).
