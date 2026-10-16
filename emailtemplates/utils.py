# coding=utf-8
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def suppress_and_log(*exceptions, message):
    """
    Like `contextlib.suppress`, but logs the exception, with its traceback; any exception
    when none is given. For the history of sent emails, which must never stop an email.
    """
    try:
        yield
    except exceptions or Exception:
        logger.exception(message)
