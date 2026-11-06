"""spa2mqtt: bridge Balboa-family hot-tub RS485 buses to MQTT / Home Assistant."""

from importlib.metadata import PackageNotFoundError, version

try:
    # The build sets the version from the git tag (hatch-vcs); read it from the installed metadata.
    __version__ = version("spa2mqtt")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0+unknown"
