# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-10-22
- Owner: Mihir

## Context

Five people will change the data layer, the agent graph, the API, and the UI in the same week. Chat messages are a poor record of why we picked a stack or a citation shape. We need a place a reviewer can point to.

## Decision

We record architecture decisions as ADRs in `docs/adr/`.

- Files are numbered `NNNN-short-title.md` and are never renumbered.
- Each ADR states its status, date, context, decision, and consequences.
- Status is Proposed, Accepted, or Superseded.
- An accepted ADR is not rewritten to reverse itself. A later ADR supersedes it and links both ways.
- The person who owns the area proposes the decision. The team accepts it at stand-up. Mihir keeps the index honest.
- An ADR does not replace a pull request when the decision changes code or a shared contract.

The working stack in [../GAMEPLAN.md](../GAMEPLAN.md) (LangGraph, FastAPI, Vite, Zetaris migrations, Nightshift lanes, compose isolation, layered citations, the Judge before the human) is the backlog for `0002` onward. This ADR does not by itself accept those choices. Open research (vector search, embeddings, Lightning SQL dialects) stays proposed until the owner files the result.

## Consequences

- Decisions have a stable name and a file.
- The next accepted decision is `0002`, not a rewrite of this one.
- Reviewers can reject a silent contract change that has no ADR and no stand-up note.
