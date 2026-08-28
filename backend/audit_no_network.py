"""Audit script (not part of the app): proves Demo/Manual analysis makes zero
external network calls. Monkeypatches socket.socket.connect to raise for any
destination that is NOT the local Postgres container ('db') or localhost, then
runs the REAL analysis pipeline (_analyze_one) end to end. If any code path
tried to reach Reddit, an AI provider, or an SMTP server, this would raise
and the script would fail loudly instead of silently passing.
"""
import asyncio
import ipaddress
import socket
import sys
import uuid
from datetime import datetime, timezone

# Docker's internal bridge network (where our own Postgres container lives)
# only ever hands out private/loopback addresses. Any call to a real external
# host (Reddit, an AI provider, an SMTP relay) resolves to a public IP, so
# this is a reliable way to distinguish "talking to our own DB container"
# from "talking to the outside world" without hardcoding the compose subnet.
_original_connect = socket.socket.connect


def _is_internal(host: str) -> bool:
    if host in {"localhost"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if not _is_internal(host):
        raise RuntimeError(f"BLOCKED EXTERNAL NETWORK CALL to {address!r} — this must never happen in Demo/Manual mode")
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect

from app.config import get_settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models.account import Account, Profile  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.enums import SourceMode  # noqa: E402
from app.models.topic import Topic, TopicKeyword  # noqa: E402
from app.services import jobs as jobs_service  # noqa: E402
from app.services.dedupe import compute_dedupe_hash, normalize_url  # noqa: E402


async def main():
    settings = get_settings()
    print(f"REDDIT_API_ENABLED={settings.reddit_api_enabled}")
    print(f"AI_ANALYSIS_ENABLED={settings.ai_analysis_enabled}")
    assert settings.reddit_api_enabled is False
    assert settings.ai_analysis_enabled is False

    async with AsyncSessionLocal() as session:
        account = Account(name="Network Audit Account")
        session.add(account)
        await session.flush()
        session.add(Profile(account_id=account.id, email=f"audit-{uuid.uuid4()}@example.com"))

        topic = Topic(account_id=account.id, name="Audit topic", description="audit", priority="high")
        topic.keywords = [TopicKeyword(phrase="prioritize leads")]
        session.add(topic)
        await session.commit()

        title = "Any tool to prioritize leads for my agency?"
        body = "Looking for a tool to prioritize leads based on real signals"
        url = ""
        convo = Conversation(
            account_id=account.id,
            source_mode=SourceMode.manual,
            url=url,
            url_normalized=normalize_url(url) if url else f"manual://agency/{title}",
            dedupe_hash=compute_dedupe_hash("agency", title, datetime.now(timezone.utc)),
            subreddit="agency",
            language="en",
            raw_title=title,
            raw_body=body,
            published_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            num_comments=1,
        )
        session.add(convo)
        await session.flush()

        # This is the exact function the manual-import and CSV-import endpoints
        # call to analyze a conversation. If it needed the network, it would
        # raise now (socket.socket.connect is guarded above).
        await jobs_service._analyze_one(session, convo, settings)
        await session.commit()

        print(f"score_total={convo.score_total}")
        print(f"state={convo.state.value}")
        print(f"recommended_action={convo.recommended_action.value if convo.recommended_action else None}")
        assert convo.score_total is not None and convo.score_total > 0, "analysis did not actually run"

        await session.delete(convo)
        await session.delete(topic)
        prof = (await session.execute(__import__("sqlalchemy").select(Profile).where(Profile.account_id == account.id))).scalars().first()
        if prof:
            await session.delete(prof)
        await session.delete(account)
        await session.commit()

    print("OK: analysis completed successfully with ZERO external network calls.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
