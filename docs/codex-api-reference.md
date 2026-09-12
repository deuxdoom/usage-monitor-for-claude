# Codex API Reference

How the monitor reads Codex. Two independent sources answer two different questions, and keeping
them apart is deliberate - see [Why the two are never mixed](#why-the-two-are-never-mixed).

| Source | Answers | Module |
|---|---|---|
| App-server protocol | Which account, which plan, how much of each server quota is used | `codex_api.py` |
| Local session rollouts | How many tokens each model consumed on this machine | `codex_sessions.py` |

The Claude side of the same split is documented in [claude-api-reference.md](claude-api-reference.md).

## Requirements

Install Codex and sign in with ChatGPT first. An API-key-only account does not supply subscription
quota windows, so the bars stay unavailable for it. The monitor never reads Codex credentials -
authentication belongs to Codex itself.

## Server quotas: the app-server protocol

The monitor launches the installed native Codex CLI (or the IDE extension's binary) as a
short-lived app-server and talks to it over standard input/output. Analytics and the OpenTelemetry
exporter are switched off for that child process:

```
codex app-server -c analytics.enabled=false -c otel.exporter="none"
```

Four requests are made on one connection, then the process is terminated:

| # | Method | Purpose |
|---|---|---|
| 1 | `initialize` | Handshake, followed by an `initialized` notification |
| 2 | `account/read` | Identity and plan (`refreshToken: false`) |
| 3 | `account/rateLimits/read` | The quota windows |
| 4 | `account/read` | Read again and compare - a mismatch means the account changed mid-read, and the whole result is discarded rather than pairing one account's identity with another's numbers |

### Fields read from `account/read`

Only three fields are used. The protocol carries no display name, so the account row falls back to
the blurred email - the same thing the Claude row does for an account without a name.

| Field | Used for |
|---|---|
| `type` | Must be `chatgpt`; anything else is reported as "ChatGPT sign-in required" |
| `email` | The account row, blurred until clicked |
| `planType` | The plan row, rendered as the product name ("ChatGPT Plus", not "Plus") |

### Fields read from `account/rateLimits/read`

Windows come from `rateLimitsByLimitId.codex`, falling back to `rateLimits` on builds that do not
send the newer shape. Each entry contributes one usage bar:

| Field | Used for | Rejected when |
|---|---|---|
| `usedPercent` | Bar fill and percentage | Not a finite number, or negative |
| `windowDurationMins` | Window length, which decides the label and the time marker | Not an integer in 1..525600 |
| `resetsAt` | Reset countdown | Present but not a finite epoch inside a sane range |

Nothing assumes which window is "primary" or "secondary". Bars are sorted by length, so the
shortest reads on top and the longest below - the same order the Claude default gives. A window
with no `resetsAt` is still shown; its countdown is simply blank rather than invented.
In the popup, a window whose `usedPercent` is zero also keeps its empty gauge but shows no
countdown, elapsed-time text, dividers or time marker, even if `resetsAt` is present. Once the
reported usage is positive, those indicators use the server timestamp again. This display rule
does not alter the cached server timestamps used by the poll scheduler.

### Cadence and backoff

A successful read is followed by a cooldown equal to the refresh interval chosen in the tray menu
(see [configuration.md](configuration.md#polling-intervals)). Each consecutive failure doubles that
wait, capped by `max_backoff`. A failed read clears the previous account values rather than leaving
a stale account on screen.

The interval is passed in by the caller and this module keeps none of its own, so a change in the
tray menu reaches the Codex side on the next read rather than after the old wait runs out.

## Local tokens: session rollouts

Token counters are read from `sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl` under
`CODEX_HOME` (default `~/.codex`). Only model names, timestamps and token counts are kept, and
only in memory.

Set `CODEX_HOME` before launching the monitor to point both the account reader and the local
totals at a different Codex home. This is independent of Claude's `--config-dir`, which selects
the Claude account and has no effect on Codex.

Two summary windows are produced, five hours and seven days. A server bar offers its expandable
detail only when a local window of the same length exists, so the two sides stay in step without
either repeating the other's numbers.

A rollout names its model in `turn_context`. A session imported into the desktop history has no
`turn_context` at all - there the model is in `session_meta.base_instructions.provenance.model`,
which is why an imported session is not reported as `Unknown`. Nothing else is read out of
`base_instructions`: it holds the full prompt text.

### Why the two are never mixed

Local token totals are **not** the numerator of the server quota:

- They can span **multiple Codex accounts** on the same machine, while the quota is one account's
- Cached input counts toward them, and reasoning is part of output
- An imported rollout stamps every record with the import time, so its tokens land in whichever
  window is current - the original timing is not in the file and is never invented

The detail panel says this in its own source note. The monitor never shows a Codex message count
or an estimated quota denominator, because neither can be derived honestly from these records.

## What Codex does not drive

The tray icon, its tooltip and the threshold alerts follow whichever agent the tray menu's
"Tray icon tracks" is set to; event commands always carry Claude quota state. The popup shows both
agents either way.

`icon_fields` and `tooltip_fields` name Claude API fields and are ignored while the tray follows
Codex, which always draws its shortest window on top and its longest below.

## Side effects

The monitor saves only its tray provider, refresh interval, popup font and popup view choices in
the settings file, using a temporary file in the same directory for replacement. Account and usage
data remain in memory. The delegated Codex process may write its own logs, databases or refreshed
credentials under its configured home, as Codex normally does. See
[PRIVACY.md](../PRIVACY.md) for the full account.
