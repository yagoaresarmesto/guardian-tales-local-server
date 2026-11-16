# How it works

The client needs three distinct services. The platform service provides local
connection settings and locally issued credentials. The binary game service
returns account and initial game responses. The CDN reads preserved content from
disk. The server code does not make outbound network connections.

```mermaid
flowchart LR
    C[Android test client] -->|HTTPS 10500| P[Platform configuration and local guest issuer]
    C -->|Binary TLS 10100| G[Game packet transport]
    G --> B[Bootstrap session and route handlers]
    B --> A[Local account store]
    P --> A
    A --> D[(SQLite)]
    B --> T[Empty templates and external bootstrap data]
    C -->|HTTP 18080| R[Read-only resource server]
    R --> M[Preservation manifests and resource files]
    H[Local health client] -->|HTTP 17657| G
```

## Package map

| Module | Responsibility |
|---|---|
| `server.py` | Asyncio listeners, connection lifecycle, counters and status |
| `protocol.py` | Packet construction, frame encoding, response framing and Pong |
| `packet_reader.py` | Bounded frame decoding, checksums, raw LZ4 and packet parsing |
| `platform.py` | Platform HTTPS route bodies and local endpoint configuration |
| `bootstrap.py` | Connection sign-in state, guest identity/credentials and game API dispatch |
| `account.py` | SQLite profile, campaign receipts, prologue completion, migrations and attendance claims |
| `campaign.py` | First chapter identifiers, stage flags, reward constants and native progress encoding |
| `missions.py` | Supported beginner reward IDs and amounts from the pinned client catalog |
| `tutorials.py` | Passive help IDs and post-Inn acknowledgment IDs from the pinned client catalog |
| `lobby.py` | Empty initial lobby/catalog read responses with correct body encoding |
| `reference.py` | External reference input, built-in templates and local certificate defaults |
| `assets.py` | Separate manifest-backed HTTP resource server |
| `probe.py`, `demo.py`, `validation.py` | Developer checks, synthetic demo and regression runner |

## Account lifecycle

1. The database creates one local UUID and an empty account template.
2. Platform sign-in/sign-up issues credentials from this instance's own signing
   key. Incoming provider tokens are shape-checked and discarded, not forwarded.
3. Game sign-in reports `NeedPrologue=true` until the prologue selection is saved.
4. The client creates its temporary prologue party from its embedded data.
5. `/auth/sign-up/v2` saves the name, avatar, voice selection and starting weapons,
   creates one knight, and returns the local account identity.
6. A later sign-in reports `NeedPrologue=false`; account reads recover the stored
   character. Repeating the identical completion does not duplicate equipment.

All sessions map to this one local account. The credential implementation is an
interoperability mechanism, not multiuser authentication or authorization.

## Persistence

The backend owns one SQLite connection on the asyncio event-loop thread. Profile
JSON, prologue selection, local identity/secrets, attendance claims, the active campaign stage and diagnostic
counters are stored in separate tables. Successful mutations use transactions.
Known schema migrations repair only the specific older prototype state they
recognize; unknown legacy edits are not silently overwritten.

Attendance uses a UTC date ledger. Repeating a claim on the same date returns the
saved state. A catalog reward must resolve entirely to supported asset balances
before the transaction changes the profile or records the claim. Item/random
rewards are rejected until their inventory behavior exists.

## Incomplete operations

Unknown game routes close the connection instead of returning invented success.
Unknown platform routes return HTTP 503. The client can show a connection error
at these boundaries. Initial empty read responses do not imply working shops,
guilds, summoning, missions, progression or battle validation.

The first chapter query returns an empty progress string for each of its seven
stages. The native client constructs a `StageProgress` per entry and accepts an
empty string as initialized empty stores. An absent entry instead produces a null
progress object and blocks the entry UI.

Only the first story phase can start. Unlocking consumes 15 stamina, from charged
stamina first and reserve stamina second, and saves the opened/unlocked flags.
Retries after restart do not charge again. Quest 27 and its observed checkpoints are
saved in `UserProgress`; neither operation marks the phase cleared. The native
quest callbacks update their own in-memory quest objects, so their responses do
not send a second copy of `UserProgress`.

Purple coins, named items and known defeated monster handles have per-stage
receipts. Their native progress stores are encoded as version 2: a store count,
category IDs, byte-indexed boolean bitmaps, signed 32-bit integer overrides and
a trailing `StonePieces` byte (currently zero). Repeated or overlapping requests do not repeat grants.
Named item receipts retain their inventory IDs across restart. The monster drop
rule is provisional; see [status](status.md) before relying on its economy.

The first phase's clear exit requires an active stage, quest checkpoint 4 and the
glove chest receipt. A transaction saves its cleared flag, completion telemetry
and one 50-free-gem grade claim, then removes the active stage session. Retrying
the same completion after restart returns the saved progress without another
reward. This phase has no configured `StageSpec.Rewards` or `FailRewards`; its
grade reward is separate. The observed post-clear tutorial ID 200 is persisted
once and returned in `UserProgress` so the client's resource handler sees it.
The world-map acknowledgment 2019 also requires Inn cleared. Thirty-two passive
help popups, including summons help 1003 and mission-book help 1007, can be
recorded after local account creation independently of campaign or training.
These catalog entries have no start/move scene, actions or start/end conditions.
Only requested IDs are saved, with no system unlocks or rewards. Mixed tutorial
batches are validated before any acknowledgment is saved.

An optional tutorial catalog supplies the remaining known IDs. Their completion
markers can be stored after Inn is cleared. This records the client's UI state;
the handler does not execute tutorial actions, award items or alter quest/stage
state. Gameplay operations retain their own validation and persistence rules.
Unknown IDs and malformed catalogs are rejected before flags change.

The next tutorial sends `/user/add-character-experience` with a character-ID
dictionary of experience deltas. With an external training catalog, owned knights
without limit breaks or blessings can reach any listed level within the saved
story cap. Batches share one experience balance and are validated before any
mutation. One transaction saves the character totals, balance, spending counter
and request receipt. Costs are data, not individual allowlisted amounts.

Request receipts use the packet sequence ID within a persisted client request
epoch. `Reconnect: true` retains that epoch; a fresh sign-in starts another, so
a new request can legitimately spend the same amount or reuse a sequence ID.
Replays return current state without spending again. After a fresh session, a
matching completed request is recognized only when its proposed new target is
invalid; this cannot infer every ambiguous replay across a fresh client launch.
Without the catalog, the original one-time 37-point tutorial remains available.

Beginner mission claims currently accept Inn (0), knight level 2 (1) or spending
ten stamina (9), one
distinct mission per batch. Prerequisites are checked against saved clear/training
state or the sum of charged/reserve `Spent` counters. The transaction updates
asset balances, shared ticket/material inventory,
the base64 `GuideClaimed` bit array and a frozen reward receipt. A retry reuses
the original item IDs and reward notice while returning current account state.
Other missions and mixed batches remain unsupported.

The first collect-hero challenge uses a separate `(group_id, step)` reward
receipt and the integer `ChallengeClaimed` map. Only group 200's first step is
implemented for the saved one-knight account. Its transaction records step 1 and
50 free gems together; retries reuse the original reward notice. Later steps and
the all-step route require their own progression/retry contracts.

`/ad/init-inbox` is a parameterless compatibility read. Its callbacks open the
inbox while the global resource handler applies the returned saved `UserRecord`.
It preserves the existing local ad state and does not create rewards or implement
ad viewing/claims.

`/summon/enter` returns the empty local pickup catalog's `Checksum` and
`IsActiveEvent=false`. The scene loader compares these values before deciding
whether to reload its catalog. The checksum matches `/summon/on-event`; entry
does not modify the account or implement the actual summoning operations.

The automatic `/user/exchange-summon-pickup-ticket` check supports an empty
saved pair of event-coupon maps only. It returns `UserShop` plus empty
`ExchangeSummonPickUpTickets` and `ExchangeCollaborationPickUpTickets` dictionaries.
Regular/selectable inventory tickets are a separate resource and remain intact.
Existing event coupons are rejected until their conversion rules are implemented.

## Resource boundaries

The CDN accepts only files listed under `resources/files/` in preservation
manifests. URL aliases normalize the known version prefixes; later roots overlay
earlier ones. It supports ETags, conditional reads, HEAD and one explicit byte
range. It does not decrypt the content, download missing files, or compare every
file's bytes to its manifest SHA-256 while serving.

Private emulator routing, rootfs provisioning and SDK cache restoration are
installation-specific tooling outside this repository. See
[client integration](client-integration.md) for how the prepared test differed
from simply starting this Python backend.
