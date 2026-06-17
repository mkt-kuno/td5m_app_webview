import os
import sys


def get_config_dir(app_name: str = "TDS530Logger") -> str:
    """
    Return the platform-appropriate configuration directory for the app.
    Creates the directory if it does not exist.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if not base:
            base = os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:  # Linux and others
        base = os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".config")

    config_dir = os.path.join(base, app_name)
    os.makedirs(config_dir, exist_ok=True)
    return config_dir
