from db import get_session, LoginEvent
from sqlmodel import select

with get_session() as session:
    events = session.exec(select(LoginEvent)).all()
    print(f"\n=== LoginEvent registrati: {len(events)} ===")
    for e in events:
        print(f"  {e.username} | {e.channel} | {e.created_at}")
