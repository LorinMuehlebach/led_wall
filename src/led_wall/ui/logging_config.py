import logging
from logging.handlers import RotatingFileHandler
import os
import copy


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;21m"
    blue = '\x1b[38;5;39m'
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    green = '\033[92m'
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = "%(asctime)s %(levelname)-8s %(message)s (%(filename)s:%(lineno)d)"

    def __init__(self):
        super().__init__()
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.green + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        colored_record = copy.copy(record)
        log_fmt = self.FORMATS.get(colored_record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(colored_record)

def get_rotating_file_handler(filename: str, path=None):
    #use file path if nothing is specified
    if path is None:
        path = "/var/log/yuon/"
        if not os.path.exists(path):
            os.makedirs(path)

    file_handler = RotatingFileHandler(path+filename, maxBytes=1000000, backupCount=5)

    return file_handler


def file_logger(filename: str, path="/home/ubuntu/data/log/yuon/"):
    # file handler for logs written to disk
    fh = get_rotating_file_handler(filename, path)
    fh_format = logging.Formatter("%(asctime)s  %(levelname)-8s %(message)s (%(filename)s:%(lineno)d)")
    fh.setFormatter(fh_format)
    fh.setLevel(logging.WARNING)  # only important to disk

    # stream handler for logs written to terminal
    sh = logging.StreamHandler()
    sh.setFormatter(CustomFormatter())
    #sh.setLevel(logging.INFO)  # log all comandline

    #use basicConfig such that this settings will be used by all libraries
    logging.basicConfig(
        level=logging.INFO,
        handlers = [sh,fh],
        force = True
    )

def getLogger(name):
    return logging.getLogger(name)    

#default config -------------------------------
sh = logging.StreamHandler()
sh.setFormatter(CustomFormatter())
sh.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,
    handlers = [sh]
)

CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
INFO = 20
DEBUG = 10
NOTSET = 0

if __name__ == "__main__":
    logging_config.file_logger("testlogs.log")

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    logger.debug("Debug")
    logger.info("Info")
    logger.warning("Warning")
    logger.error("Error")
