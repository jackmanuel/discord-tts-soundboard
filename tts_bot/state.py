import asyncio
from dataclasses import dataclass, field


@dataclass
class BotState:
    voice_client: object = None
    disconnect_task: object = None
    request_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    user_sounds: dict = field(default_factory=dict)
    last_tts_file: str = None
    pipeline: object = None
