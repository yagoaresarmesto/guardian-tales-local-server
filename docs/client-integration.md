# Connecting a test client

The source-only quick start validates a backend. Connecting the original APK is
a separate integration task. This repository does not include an emulator image,
APK installer, extracted metadata, SDK cache, private CA, rootfs or
machine-specific routing scripts. Matching preserved game data is available
separately through the [offline content release and import guide](offline-content.md).
An experimental [MuMu Android 12 bridge](mumu-client.md) now supplies reproducible
hostname/trust/routing setup for a host backend whose TLS connection already
passes verification. Its new APK path is still being tested separately from the
earlier private laboratory observations below.

## Local lobby notice

For a live game mode summary, install the `lobby-notice` extra in the local
CDN environment and set `lobby_notice.json` in the active reference directory to
`{"enabled": true, "mode": "settings", "generation": 2}`. Use the next generation
when switching from an existing image. On a fresh login, the backend reads the
applied mode selections and the local save, then publishes a read-only snapshot.
Changes in those values automatically receive a new banner URL. **Move** links
to its full settings, including the Raid lineup, DKA rotation and individual
Expedition overrides. The optional `panel-art` extra and matching content
provide the Raid sprites. A missing mode reports its settings as unavailable.
To turn off this notice, keep its mode, set `enabled` to `false`, and increase
the generation.

The test backend can show a local PNG in the native lobby notice window. Place
`lobby_notice_1.png` in the active reference directory, then create
`lobby_notice.json` there with `{"enabled": true, "generation": 1}`. The standard
local CDN uses the same reference directory. All client languages use this image,
so put the desired message directly on the banner. Fully reopen the game and
enter the lobby to see it. On Android 3.57.0, the English test image
**This is a test** appeared over the lobby with the native close button and
the option to hide the notice for the day.

To remove the notice, set `{"enabled": false, "generation": 2}` and reopen the
game. Increase the generation on each change so the client refreshes its catalog.
When enabling a new image, use the matching filename, such as
`lobby_notice_3.png`. An installation without a settings file uses its original
notice catalog. The test notice has no rewards.

## Client version and content compatibility

The **APK is the client**: its platform and game requests must reach the local
server, which returns the implemented responses. The APK continues to render the
game and run its client-side logic. Starting the Python server alone does not
attach to an installed app or redirect its requests.

| Component | Current baseline |
|---|---|
| Client | Guardian Tales **3.57.0 for Android** |
| Distribution | **Google Play, European service**, package `com.kakaogames.gdts` |
| Platform configuration | `Version=v3.57.0`, `Market=googleplay`, `AppId=422316` |
| Game handshake | Exact ASCII `3.57.0`, padded to 16 bytes |
| External inputs | Compatible bootstrap bodies and preserved resources from the matching client/content snapshot |
| Original-client test | The prepared MuMu clone with the preserved EN/ES content and Japanese voice supplement |

The version requirement is enforced in code. A different game handshake is
rejected, and the platform route checks the version, market and application ID.
Other regional distributions, APK variants, platforms and versions have not been
validated, even if their displayed version looks similar.

Keep the client and content snapshot together. The APK version alone is not
enough: downloadable data can have its own revision, and the bootstrap catalog
must agree with the resources available locally. Install the matching base APK
and required splits when the preserved client uses a split installation. The
Japanese voice supplement is part of the tested content set, not a requirement
to select Japanese voice playback.

For now, reproduce the pinned baseline rather than updating the APK or content
independently. Supporting a newer client means reviewing its protocol, response
contracts and content assumptions, then testing that version explicitly; changing
a version string does not establish compatibility.

The source ZIP supplies the server and synthetic tests. Each client setup must
supply its own compatible APK installation; matching content can be imported
from the separate Release attachments. Neither the APK nor those attachments
are embedded in the source ZIP.

## Requirements for an APK experiment

Use a disposable test instance with the compatible 3.57.0 client and its preserved
resources. It needs all of the following:

1. Platform HTTPS requests reach the local platform service on port 10500.
2. Binary game requests reach port 10100.
3. Advertised CDN URLs resolve to the local read-only resource server on 18080.
4. The client trusts the certificate presented for the hostnames it actually uses.
5. Compatible bootstrap response bodies and resource manifests are available.
6. An offline experiment blocks the instance's non-local network traffic before
   the game starts, while retaining its management channel.

Inside Android, `127.0.0.1` means Android itself, not the Windows host. A bridge
such as an explicitly configured ADB reverse mapping or an Android-local service
is needed for host services. ADB forwarding alone does not establish TLS trust or
change the hostnames used by the client.

The certificate generated by the quick start covers **localhost and 127.0.0.1**.
It is for the synthetic probes. It does not cover the original game hostnames.
An APK integration requires a separately provisioned lab certificate/trust setup
for those names. The project does not disable TLS verification.

## Prepared Windows/MuMu test

The existing private workspace used a dedicated MuMu clone, transient hostname
and Android trust overlays, and reversible egress rules. Its earlier prepared
client reused a local SDK guest cache; the later clean-client experiment created
a new guest through the local platform service without importing that cache.
The binary/HTTPS backend ran in a prepared Python rootfs **inside Android**. The
read-only resource CDN ran on Windows and reached Android through ADB reverse.

This arrangement was necessary on that machine because Windows TLS inspection
substituted the server certificate. Antivirus settings and Windows trust were
not changed. The disposable clone's original hosts, trust listing, SDK cache,
preferences and network rules were verified on restoration; root was disabled
and the clone shut down. The normal emulator instance was not used.

Those machine-specific helpers remain outside the public repository. The
workspace's separate local launcher needs the original prepared environment;
copying this repository to another computer does not recreate it.

## Expected behavior and current stopping point

A newly installed client also requests `/static-data/device-specific-settings`
before sign-in. The local response provides no hardware-specific audio override,
so the native client uses its built-in DSP fallback. This needs no external
catalog and does not create gameplay progress.

Clean installation is a separate work in progress. The earlier prepared client
already had its static tables and downloaded content. A captured checksum-only
`/static-data/get` response does not supply those tables to a new client. Fresh
setups need a complete matching initial table response in addition to the CDN
resources; copying only that earlier response is insufficient. See the
[clean installation findings](status.md#clean-installation-experiment).

With the complete matching external inputs supplied, the separate clean-client
experiment has now passed local guest access, initial resource download and
extraction, and user-confirmed prologue completion with one saved character.
This establishes that path in the prepared clean laboratory. The matching data
is now packaged in the project's separate content release. The repository does
not yet recreate the laboratory's machine-specific routing/trust setup.

With the compatible private inputs and routing, the observed sequence is local
guest access, prologue, saved character, lobby, and world map. On a new account,
explicitly select a personality as well as the avatar and name. The game creates
its temporary prologue party; the backend saves the selected knight at completion.

The first story phase, Inn, can be unlocked, entered and cleared through its main
exit. Quest checkpoints, purple coins, named pickups, the glove chest and the
50-gem first-clear reward persist. The APK returned to the world map and reopened
the saved account after restart. The initial knight level 1-to-2 tutorial also
works for its observed 37-experience cost. With the matching external training
catalog, later knight level-ups and multi-level spending also work; the APK
accepted subsequent costs of 74, 111 and 559 experience. The mission book accepts the beginner
rewards for Inn and knight level 2. Optional collectibles, later phases,
general hero training and other progression remain unfinished. Unsupported game operations can
produce the client's connection-lost dialog. See [status](status.md) for the
precise verified scope.

The optional story-entry catalog prepares passage 110011001 (`passage_1_1`), the
loaded map's immediate destination after Inn, and main stage 100010002. Their
first entries cost 10 and 15 stamina respectively; subsequent entries are free.
Both currently require Inn's saved clear flag. Charged and reserve stamina both
count toward entry, including when charged stamina is zero. Return to the lobby
and reopen Adventure after updating the backend so chapter progress refreshes
the map. The APK has entered the passage and saved its 10-stamina unlock.
The optional monster catalog prepares reports for its nine named enemies.
The APK accepted the observed passage encounters. An optional completion catalog
prepares its clear exit after the seven reported enemies, preserving rewards and
quest progress. The APK accepted the clear retry and the passage's cleared flag
is saved. The second main phase's clear path is not yet verified; additional
passage grade rewards remain pending.

The discovered side map `substage_1_5` is a separate stage, 110010005. Its prepared
entry costs 10 stamina once and requires the saved discovery flag. Chapter reads
initialize progress for discovered stages even without an entry catalog, so
opening their entry screens does not receive a null progress object. The native
entry-screen load previously failed on that missing object. If that screen has
already stalled, reopen the game to rebuild its UI state. Side-stage gameplay
and completion are still unfinished.

The subsequent Use 10 Stamina beginner reward and first Collect 1 Heroes
challenge reward also passed their APK retries. Later challenge steps and other
mission groups remain unfinished; see the status record for the exact scope.

Summons entry supplies an empty catalog by default. The optional hero-selection
catalog supplies valid candidates and matching entry/catalog checksums. The APK
loaded this list and registered five wishlist heroes. Only the wishlist and shop
revision changed; its 1,000,400 gems and remaining profile were retained. If an
earlier empty list produced the invalid `-1` placeholder, reopen the game after
installing the catalog to discard that pending request.

The automatic pickup-ticket exchange check supports empty saved event-coupon
maps while preserving inventory tickets. With an explicit local draw catalog,
one/ten hero draws can spend free gems (cost type 0), ordinary controllers (3)
or selectable controllers (5). The APK completed two ten-draw controller batches
and one ten-draw gem batch, retaining the resulting heroes and rewards. The
subsequent four single draws used type 5 and also succeeded.
Reconnect reuses frozen results without a second charge. Probabilities are local
configuration; official promotions, pity, paid events, weapon selection/draws
and general hero training remain unfinished.

Passive help acknowledgments now use the pinned 32-popup allowlist, including
summons help 1003. The post-Inn world-map acknowledgment 2019 requires the saved
clear flag; its retry is tracked in the verification status. These flags do not
unlock or implement the corresponding game systems.
