"""Short post-seen composition pause for owner-approved text only."""
import asyncio
import random


def composition_seconds(text: str) -> float:
    # Explicit owner actions remain short; automatic persona scheduling is separate.
    return min(18.0, max(2.0, len(text.strip()) / 12.0)) * random.uniform(.9, 1.1)


async def composition_pause(text: str) -> None:
    await asyncio.sleep(composition_seconds(text))
