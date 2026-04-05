from core.logger import get_logger

from services.conversation_service import (
    get_active_session_id,
    get_session_data
)

logger = get_logger()


def restore_last_session():

    try:

        session_id = get_active_session_id()

        if not session_id:

            logger.info("No previous session found")

            return None

        data = get_session_data(session_id)

        if not data:

            logger.warning("Session data missing")

            return None

        logger.info(
            f"Restored session: {data.get('title')}"
        )

        return data

    except Exception:

        logger.exception(
            "Failed to restore session"
        )

        return None