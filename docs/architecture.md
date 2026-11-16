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
| `account.py` | SQLite profile, prologue completion, schema migrations and attendance claims |
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
JSON, prologue selection, local identity/secrets, attendance claims and diagnostic
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

The world-map handler currently returns an empty `StageProgresses` dictionary.
Chapter unlock and phase entry state still need implementation.

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
