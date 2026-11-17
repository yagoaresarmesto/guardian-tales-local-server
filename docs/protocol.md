# Observed 3.57.0 packet protocol

This describes the implemented client-version path, not an official specification.
See `protocol.py`, `packet_reader.py`, and the regression fixtures for the exact
byte operations. [API response schemas](reference/api-contracts.json) record
observed property names and types without account values. Observed presence alone
does not establish that a property is required.

## Connection and counters

Port 10100 uses TLS. After TLS negotiation, the client sends the ASCII version
`3.57.0`, zero-padded to 16 bytes. The server sends a little-endian 32-bit seed.
The first client and server frame counters both use that seed. Subsequent client
frame counters increment; server frame counters decrement, modulo 2^32.

Port 10500 is a separate HTTPS platform API, not another binary transport.

After the game handshake, an idle connection can wait for its next frame without
an inactivity deadline. The client may pause in menus or download choices without
sending keepalives. Once a frame's first byte arrives, its remaining header must
arrive within ten seconds; the body has a separate ten-second completion bound.
The initial version handshake is also limited to ten seconds. Server shutdown
still closes idle connections, including a bounded laboratory session's end.

## Outer frame

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | Checksum, little endian |
| 2 | 4 | Encoded payload length, little endian |
| 6 | 2 | Nonce, little endian |
| 8 | Variable | Encoded payload |

Decoded payload length is `~(encoded_length ^ counter) & 0xffffffff`.
The checksum covers bytes from offset 2 onward, starting at `0xf208` and updating
with `(value * 257 + byte + 1) & 0xffff`.

The codec reverses the observed byte recurrence and nonce-dependent rotation
before unpacking the compression envelope. This framing transformation is
separate from TLS. The network reader rejects wire frames above 1 MiB before
allocating their complete payload. The offline/LZ4 reader bounds decoded packets
at 16 MiB.

## Compression envelope and packet

The outer envelope contains a 32-bit boundary, stored bytes, and a trailing 32-bit
decoded size. Matching stored/decoded lengths indicate uncompressed bytes;
otherwise the payload is a raw LZ4 block. Responses currently use an uncompressed
outer envelope. The decoder accepts the observed compressed form.

The inner fixed header is little-endian `<HBBBBI>`:

| Type | Field |
|---|---|
| UInt16 | Version |
| Byte | Packet type |
| Byte | Reliable type |
| Byte | Result type |
| Byte | Body type |
| UInt32 | Sequence ID |

It is followed by a .NET-style 7-bit length-prefixed UTF-8 API string, an error
string for result types 1/2, a hint string, and, for a nonzero body type, a UInt32
body length and body bytes. API responses have an empty API string and echo the
request sequence ID.

For API JSON, body type 1 is UTF-8 JSON; body type 2 uses raw LZ4 followed by the
decoded size. The exact body type matters even when the resulting JSON is `[]`.
Static-data bootstrap bodies are retained externally in their observed encoding.

## Keepalive

The implemented Ping has packet type 3, body type 2, and one raw Int64 millisecond
timestamp. Pong has packet type 4 and two raw Int64 values: the echoed client
timestamp and current server timestamp. **These raw keepalive bodies are not
compressed JSON**, despite sharing the numeric body type.

## Local packet reader

```sh
python -m guardian_tales read-packet tests/fixtures/pong_real.bin
python -m guardian_tales read-packet local/frame.bin --layer frame --counter 0x12345678
```

The second command is a format example: a real wire frame requires its actual
connection counter. Decoded bodies can contain private data; keep your captures
and reader output outside the source repository.
