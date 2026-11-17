# API inventory and implementation plan

Recorded on **2026-11-17**, against server source commit `d248371` and the
Android 3.57.0 client. This plan supports development while the prepared lab is
stopped. The inventory and this document do not change runtime behavior,
account state, external catalogs or emulator configuration.

## What the inventory establishes

The [machine-readable inventory](reference/client-api-inventory.json) contains
public protocol identifiers from static inspection of native
`Oak.ApiConnection.Send*` methods. Account data, request captures, binaries,
metadata dumps and native disassembly are excluded.

| Finding | Count | Meaning |
|---|---:|---|
| Native send methods inspected | 717 | Methods in the selected class whose names start with `Send` |
| Methods with a direct route literal | 709 | One method contains two alternative routes |
| Distinct route literals | 710 | Candidate endpoints across 62 route prefixes |
| Methods without a direct route literal | 8 | Delegates, helpers or constructed paths need follow-up |
| Current game routes registered in the server | 58 | Dispatch declarations, including partial handlers and empty reads |
| Registered routes present in the native scan | 57 | Exact string intersection with this inventory |
| Scanned routes without current dispatch | 653 | Work candidates, with very different dependencies and scope |

These counts do not measure game completion. A route can contain many operations,
conditions and response variants. Registering it does not establish that all are
implemented. One registered route, `/shop/get-sales-costume-collection-items`,
is outside this scan, so the inventory is demonstrably not an exhaustive list
of every possible client call.

`literal_key_candidates` are nearby identifier-shaped string literals. They are
research hints, not validated request schemas. An empty list can mean the method
forwards an object built elsewhere. Actual required fields, types and nesting
must be checked in packet construction and response consumers.

`server_dispatch` records only whether the current source routes a request to
the account, bootstrap or lobby handler. The snapshot uses parsed source
declarations and lobby template keys; it does not launch the server. Lua,
ILFix updates, non-`Send` methods and dynamically constructed routes remain
outside its scope. The earlier [observed response schemas](reference/api-contracts.json)
are a separate, limited startup observation.

## Work that can proceed with the lab stopped

1. Review the eight unresolved methods and follow their helper calls. Record
   exact routes separately from inferred or version-dependent paths.
2. Trace request builders and success/error consumers for a selected system.
   Record verified request fields, required response fields, account effects,
   public catalog dependencies and unresolved rules before implementing it.
3. Write cross-system regressions using synthetic guests and temporary SQLite
   databases. Exercise existing campaign, training, draws and reward handlers
   together, including restart and reconnect. Retain the existing focused tests.
4. Implement a small, coherent group of operations using matching public data
   and explicit local rules where official behavior is unknown. Preserve existing
   response shapes and receipts. Reject unsupported variants without mutation.
5. Verify atomic writes, retry behavior and unrelated profile preservation in
   automated tests before testing that group in the APK when the lab resumes.

The first three activities require no game interaction. Synthetic databases do
not read, clone or migrate the saved laboratory account. Protocol knowledge can
therefore advance independently of the user's play session.

## Proposed order

The counts below are route registration counts, not successful gameplay counts.
Priorities reflect the current objective: a reliable early single-player campaign.

| Order | System | Native routes / registered | First coherent unit | Main unresolved dependencies |
|---|---|---:|---|---|
| 1 | Campaign and quests | 21 / 10 | Quest completion and custom-state persistence | Matching tilemap events, quest grades, clear prerequisites, rewards and client merge behavior |
| 2 | Party and equipment | Part of user: 46 / 4 | Party membership and ordinary equipment changes | Owned inventory IDs, slot compatibility, shared-item restrictions and callback response fields |
| 3 | Beginner and daily missions | 9 / 3 | Reusable condition evaluation for verified mission types | Public conditions, reward kinds, daily rollover and prerequisites |
| 4 | Basic item management | 32 / 0 | Lock/unlock before selling, enhancement or evolution | Item-list semantics, response shape, eligibility and destructive-operation retry identity |
| 5 | Hero development | Part of user: 46 / 4 | Extend ordinary experience training beyond the initial knight | Hero-specific targets, evolution/rarity, story caps and equipped state |
| 6 | Summons completion | 15 / 4 | Inspect consumers and determine local history representation | Draw records, ordering, pagination and weapon-catalog rules |
| 7 | Training objectives | 3 / 0 | Verified objective completion and reward batches | Objective conditions, progression order, public rewards and separate claim receipts |

Orders 2 and 5 overlap the same `/user/*` prefix and must not be added together
as independent coverage. Existing training has explicit restrictions; a larger
hero roster alone does not establish support for training every owned hero.

For campaign work, inspect `/stage/clear-quest`, `/stage/set-custom` and
`/stage/set-quest-custom-state` first. Then inspect the configured early stages'
uses of `/stage/pay-gold`, `/stage/pay-items`, `/stage/insert-stone-piece` and
`/stage/add-follower`. Timers, revival and radar need their own contracts if those
stages use them. Rankings are a separate feature and do not block ordinary local
quest persistence. These are candidates from the client inventory, not a claim
that every listed operation is required by Inn.

For party/equipment work, start with `/user/save-party-member/v2`,
`/user/change-party-member/v2` and `/user/change-characters-equipments`. Determine
whether the specialized weapon/accessory/costume routes share a common state
model before implementing them. Successful changes must survive account reload
and preserve inventory ownership, character experience and party references.

The current beginner engine already handles atomic batches and repeated claims
for known conditions. Extend its verified condition coverage instead of assuming
every catalog mission is achieved. Daily, event, challenge-step and compass claims
have different reset/progression rules and need separate evidence.

## Automated checks for each unit

A system should have tests that verify observable state and protocol behavior:

- A valid action returns the fields read by the client and persists the intended
  change across reopening the database.
- Repeating the same logical operation does not charge twice, duplicate rewards
  or restore resources spent after the original operation.
- Unknown IDs, wrong ownership, incompatible slots, incomplete prerequisites,
  insufficient resources and malformed requests leave the whole account unchanged.
- Failure after an intermediate write rolls back profile changes and receipts
  together; mixed old/new batches award only new results.
- Other balances, characters, equipment, quest state and previously saved receipts
  remain intact. Reconnect and fresh-login sequence reuse follow explicit rules.

Request identity requires particular care for destructive actions and random
results. An identical body can also be a legitimate new action; deduplicating
all equal payloads forever would suppress real play. Use the existing receipt
and epoch rules where applicable, document their limits and test the chosen rule.

Passing synthetic tests establishes behavior of the local implementation. APK
testing still checks scene transitions, UI state merges and gameplay-dependent
sequences that cannot be inferred reliably from route registration alone.

## Work to defer

Multiplayer combat, rankings, guild systems, purchases and rotating live-service
events have extensive dependencies and little immediate value for the early
campaign objective. Official probabilities, pity rules and server-side battle
validation are not recoverable merely from route names. Local replacements need
explicitly documented behavior when the original rules are unavailable.

Additional profiles, save-slot administration and migrations of the current
laboratory save remain deferred at the user's request. This inventory introduces
none of those changes. Future work can proceed in focused commits and isolated
tests while the verified runtime remains available for the next play session.
