import sys
from core.crash_recovery import mark_clean_shutdown
from core.logger import get_logger

logger = get_logger()


_shutdown_hooks = []


def register_shutdown_hook(func):
    """
    Register a function to be executed during shutdown.
    """

    _shutdown_hooks.append(func)


def shutdown():

    logger.info("Shutdown initiated")

    for hook in reversed(_shutdown_hooks):

        try:

            hook()

        except Exception:

            logger.exception("Shutdown hook failed")

    mark_clean_shutdown()

    logger.info("Shutdown complete")

    sys.exit(0)