"""What other features may use from Auth. Owner: Eman.

RAG, Community and Calls import sessions, accounts and request guards only
from here, so the auth internals can change as long as these keep working.
"""
from sqlalchemy import Select, select

from .deps import admin, daai, daai_from_token, optional_daai, optional_seeker, seeker, seeker_key
from .models import Daai, SeekerAccount, SeekerSession
from .security import seeker_id


def account_session_ids() -> Select:
    """Session ids that belong to a seeker account. Their data is kept until the account is deleted,
    while anonymous sessions follow the normal retention (RETENTION_HOURS)."""
    return select(SeekerAccount.session_id)


def account_gender(db, sid: str) -> str:
    """The sex ("m" or "f") a seeker account gave, or "" for an anonymous session, so a message about them
    can use the right Arabic grammar."""
    return db.scalar(select(SeekerAccount.gender).where(SeekerAccount.session_id == sid)) or ""


__all__ = ["Daai", "SeekerSession", "account_gender", "account_session_ids", "admin", "daai", "daai_from_token", "optional_daai",
           "optional_seeker", "seeker", "seeker_id", "seeker_key"]
