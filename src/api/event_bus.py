import asyncio
from collections import defaultdict

# run_id → list of subscriber queues
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[run_id].append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    try:
        _subscribers[run_id].remove(q)
    except ValueError:
        pass
    if not _subscribers[run_id]:
        del _subscribers[run_id]


async def publish(run_id: str, event: dict) -> None:
    for q in list(_subscribers.get(run_id, [])):
        q.put_nowait(event)
