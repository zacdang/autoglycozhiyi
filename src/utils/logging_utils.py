"""
Centralised logging setup.
Call get_logger(__name__) at the top of every module.
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
