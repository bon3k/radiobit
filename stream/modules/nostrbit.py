import asyncio
import json
import uuid
from bech32 import bech32_decode, convertbits
import websockets

# pubkey de zap.stream
ZAP_STREAM_PUBKEY = "cf45a6ba1363ad7ed213a078e710d24115ae721c9b47bd1ebf4458eaefb4c2a5"
RELAYS = ["wss://nos.lol", "wss://relay.damus.io"]

def _npub_to_hex(npub: str) -> str:
    hrp, data = bech32_decode(npub)
    if hrp != "npub" or data is None:
        raise ValueError("Valor npub no válido")
    decoded = convertbits(data, 5, 8, False)
    return bytes(decoded).hex()

async def _query_relay(relay_url: str, npub_hex: str) -> str | None:
    sub_id = str(uuid.uuid4())
    req = [
        "REQ",
        sub_id,
        {
            "kinds": [30311],
            "authors": [ZAP_STREAM_PUBKEY],
            "#p": [npub_hex],
            "limit": 1,
        },
    ]
    close = ["CLOSE", sub_id]

    try:
        async with websockets.connect(relay_url) as ws:
            await ws.send(json.dumps(req))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                typ, sid, ev = json.loads(msg)
                if typ == "EVENT" and sid == sub_id:
                    for tag in ev.get("tags", []):
                        if tag[0] == "streaming":
                            await ws.send(json.dumps(close))
                            return tag[1]
            await ws.send(json.dumps(close))
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
        pass
    return None

async def resolve_m3u8_async(npub: str) -> str | None:
    """Devuelve la URL .m3u8 asociada a un npub o None si no se encuentra."""
    npub_hex = _npub_to_hex(npub)
    for relay in RELAYS:
        url = await _query_relay(relay, npub_hex)
        if url:
            return url
    return None

async def resolve_m3u8_with_timeout(npub: str, timeout: float = 5.0) -> str | None:
    """Envuelve la resolución con un timeout global por npub."""
    try:
        return await asyncio.wait_for(resolve_m3u8_async(npub), timeout=timeout)
    except asyncio.TimeoutError:
        return None

async def resolve_multiple_npubs(npubs: list[str], timeout: float = 5.0) -> dict[str, str]:
    """Resuelve múltiples npubs en paralelo, con timeout individual."""
    results = await asyncio.gather(
        *(resolve_m3u8_with_timeout(npub, timeout) for npub in npubs),
        return_exceptions=True
    )
    return {
        npub: url for npub, url in zip(npubs, results)
        if isinstance(url, str) and url
    }

def resolve_m3u8(npub: str) -> str | None:
    """Función bloqueante (sincrónica) para scripts que no usen asyncio."""
    return asyncio.run(resolve_m3u8_async(npub))

