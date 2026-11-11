"""OpenAI, on the user's own key: GPT text for history composition and the Realtime voice model for narration.

Narration uses gpt-realtime-2.1-mini over the Realtime API because every Speech-API model (tts-1, tts-1-hd,
gpt-4o-mini-tts) shuts down on 6 Jan 2027. The model returns 24 kHz PCM, which we encode to MP3 so the
app's /api/tts/{key}.mp3 route and player stay exactly as they were.
"""

import asyncio
import base64
import logging

import lameenc
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

TEXT_MODEL = "gpt-6-sol"
VOICE_MODEL = "gpt-realtime-2.1-mini"
VOICES = ("marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")
DEFAULT_VOICE = "marin"
SAMPLE_RATE = 24000
CHUNK_CHARS = 1400  # one realtime response per chunk keeps each reading short and faithful

NARRATOR = (
    "You are the narrator of NVM, an app that tells the history of Indian streets. "
    "Read the user's text aloud exactly as written, word for word, in order, in English. "
    "Do not add, skip, summarise, translate, comment or greet. Pronounce Indian names naturally. "
    "Speak warmly and unhurriedly, like a documentary narrator, with a brief pause at each full stop."
)


async def generate_text(api_key: str, system: str, prompt: str) -> str:
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.responses.create(model=TEXT_MODEL, instructions=system, input=prompt)
    return resp.output_text


def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for sentence in text.replace("\n", " ").split(". "):
        piece = sentence if sentence.endswith(".") else sentence + "."
        if cur and len(cur) + len(piece) + 1 > CHUNK_CHARS:
            out.append(cur.strip())
            cur = ""
        cur += " " + piece
    if cur.strip():
        out.append(cur.strip())
    return out


def _pcm_to_mp3(pcm: bytes) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(SAMPLE_RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())


async def synthesize_mp3(api_key: str, text: str, voice: str = DEFAULT_VOICE) -> bytes:
    client = AsyncOpenAI(api_key=api_key)
    pcm = bytearray()
    async with client.realtime.connect(model=VOICE_MODEL) as conn:
        await conn.session.update(
            session={
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": NARRATOR,
                "audio": {"output": {"voice": voice, "format": {"type": "audio/pcm", "rate": SAMPLE_RATE}}},
            }
        )
        for chunk in _chunks(text):
            await conn.conversation.item.create(item={"type": "message", "role": "user", "content": [{"type": "input_text", "text": chunk}]})
            await conn.response.create()
            async for event in conn:
                if event.type == "response.output_audio.delta":
                    pcm += base64.b64decode(event.delta)
                elif event.type == "response.done":
                    break
                elif event.type == "error":
                    raise RuntimeError(getattr(event.error, "message", "realtime error"))
    if not pcm:
        raise RuntimeError("no audio returned")
    return await asyncio.to_thread(_pcm_to_mp3, bytes(pcm))
