import logging
import os

# Tool mode
dev_mode = True
logging_level = logging.DEBUG if dev_mode else logging.WARNING

# Tool paths
home_dir = os.path.expanduser("~")
config_dir = os.path.join(home_dir, ".nuke", "NkScriptEditor")
pref_filepath = os.path.join(config_dir, "preferences.pref")
