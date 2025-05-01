import logging

from NkScriptEditor import nkConstants

class NukeHandler(logging.Handler):
    """Custom logging handler that prints to Nuke's Script Editor via print()"""
    def emit(self, record):
        try:
            msg = self.format(record)
            print(msg)
        except Exception:
            pass

def getLogger(module_name):
    # Create a logger for this module
    logger = logging.getLogger(module_name)
    logger.setLevel(nkConstants.logging_level)  # Set minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger.propagate = False
    # Create console handler and set its log level
    ch = logging.StreamHandler()
    ch.setLevel(nkConstants.logging_level)

    # Create formatter and attach it to the handler
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s:NkSE:%(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    ch.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(ch)

    nh = NukeHandler()
    nh.setLevel(nkConstants.logging_level)
    nh.setFormatter(formatter)
    logger.addHandler(nh)

    return logger
