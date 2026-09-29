import logging
import sys

from footscan.config import settings


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. re-imported under uvicorn --reload)

    root.setLevel(settings.log_level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers at INFO
    for noisy in ("PIL", "matplotlib", "urllib3", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
