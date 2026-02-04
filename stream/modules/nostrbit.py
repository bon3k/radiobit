import asyncio
import json
import uuid
import time
from dataclasses import dataclass
from typing import Optional, List, Dict
from functools import lru_cache

from bech32 import bech32_decode, convertbits
import websockets



# CONFIGURATION

ZAP_STREAM_PUBKEY = "cf45a6ba1363ad7ed213a078e710d24115ae721c9b47bd1ebf4458eaefb4c2a5"

DEFAULT_RELAYS = [
    "wss://nos.lol",
    "wss://relay.snort.social",
    "wss://relay.damus.io",
]

STREAM_KINDS = [30311, 30312]
RELAY_TIMEOUT = 8.0
GLOBAL_TIMEOUT = 15.0



# MODEL NIP-19

@dataclass
class NostrPointer:
    type: str
    pubkey: Optional[str]
    relays: List[str]



# DECODE NIP-19

def decode_nip19(identifier: str) -> NostrPointer:
    hrp, data = bech32_decode(identifier)
    if data is None:
        raise ValueError("Bech32 inválido")

    raw = bytes(convertbits(data, 5, 8, False))

    if hrp == "npub":
        return NostrPointer(
            type="npub",
            pubkey=raw.hex(),
            relays=[]
        )

    if hrp == "nprofile":
        pubkey = None
        relays = []
        i = 0

        while i + 2 <= len(raw):
            t = raw[i]
            l = raw[i + 1]
            v = raw[i + 2:i + 2 + l]

            if t == 0x00:
                pubkey = v.hex()
            elif t == 0x01:
                relays.append(v.decode())

            i += 2 + l

        if not pubkey:
            raise ValueError("nprofile sin pubkey")

        return NostrPointer(
            type="nprofile",
            pubkey=pubkey,
            relays=relays
        )

    raise ValueError(f"NIP-19 no soportado: {hrp}")



# RELAYS & METRICS

relay_stats: Dict[str, Dict[str, float]] = {}


def build_relay_list(pointer: NostrPointer) -> List[str]:
    seen = set()
    ordered = []

    for r in pointer.relays + DEFAULT_RELAYS:
        if r not in seen:
            seen.add(r)
            ordered.append(r)

    return ordered


def record_relay_stat(relay: str, latency: float, success: bool):
    stats = relay_stats.setdefault(relay, {
        "success": 0,
        "fail": 0,
        "latency": 0.0,
    })

    if success:
        stats["success"] += 1
        stats["latency"] = (stats["latency"] + latency) / 2
    else:
        stats["fail"] += 1



# QUERY RELAY

async def _query_relay_inner(relay_url: str, pubkey_hex: str) -> Optional[str]:
    sub_id = str(uuid.uuid4())
    start = time.monotonic()

    req = [
        "REQ",
        sub_id,
        {
            "kinds": STREAM_KINDS,
            "authors": [ZAP_STREAM_PUBKEY],
            "#p": [pubkey_hex],
            "limit": 1,
        },
    ]
    close = ["CLOSE", sub_id]

    ws = await asyncio.wait_for(websockets.connect(relay_url), RELAY_TIMEOUT)

    try:
        await ws.send(json.dumps(req))

        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=RELAY_TIMEOUT)
            typ, sid, ev = json.loads(msg)

            if typ == "EVENT" and sid == sub_id:
                for tag in ev.get("tags", []):
                    if tag[0] == "streaming":
                        latency = time.monotonic() - start
                        record_relay_stat(relay_url, latency, True)
                        await ws.send(json.dumps(close))
                        return tag[1]

    finally:
        await ws.close()


async def _query_relay(relay_url: str, pubkey_hex: str) -> Optional[str]:
    try:
        return await asyncio.wait_for(
            _query_relay_inner(relay_url, pubkey_hex),
            timeout=RELAY_TIMEOUT
        )
    except Exception:
        record_relay_stat(relay_url, 0.0, False)
        return None



# CACHE

@lru_cache(maxsize=256)
def _cache_key(identifier: str) -> str:
    return identifier


# NETWORK CHECK

async def has_internet_async(timeout=2) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("1.1.1.1", 443),
            timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


# RESOLVE

async def resolve_m3u8_async(identifier: str) -> Optional[str]:
    if not await has_internet_async():
        return None
    
    pointer = decode_nip19(identifier)
    if not pointer.pubkey:
        return None

    relays = build_relay_list(pointer)

    tasks = [
        asyncio.create_task(_query_relay(relay, pointer.pubkey))
        for relay in relays
    ]

    try:
        for coro in asyncio.as_completed(tasks, timeout=GLOBAL_TIMEOUT):
            try:
                result = await coro
                if result:
                    for t in tasks:
                        t.cancel()
                    return result
            except Exception:
                pass
    finally:
        for t in tasks:
            t.cancel()

    return None


async def resolve_m3u8_with_timeout(
    identifier: str,
    timeout: float = GLOBAL_TIMEOUT
) -> Optional[str]:
    try:
        return await asyncio.wait_for(resolve_m3u8_async(identifier), timeout)
    except asyncio.TimeoutError:
        return None


async def resolve_multiple_identifiers(
    identifiers: List[str],
    timeout: float = GLOBAL_TIMEOUT
) -> Dict[str, str]:
    results = await asyncio.gather(
        *(resolve_m3u8_with_timeout(i, timeout) for i in identifiers),
        return_exceptions=True
    )

    return {
        ident: url
        for ident, url in zip(identifiers, results)
        if isinstance(url, str) and url
    }



# API SINC

def resolve_m3u8(identifier: str, timeout: float = GLOBAL_TIMEOUT) -> Optional[str]:
    return asyncio.run(resolve_m3u8_with_timeout(identifier, timeout))

