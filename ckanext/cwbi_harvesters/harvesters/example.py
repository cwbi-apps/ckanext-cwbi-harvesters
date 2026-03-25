"""Template strategy for creating new local harvesters.

Copy this file and adjust the class name plus business logic,
then register an alias in `harvesters/registry.py`.
"""

import json

try:
    from ckanext.harvest.harvesters import HarvesterBase  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class HarvesterBase(object):
        pass


class ExampleHarvesterStrategy(HarvesterBase):
    """Minimal strategy contract used by CwbiHarvesters."""

    DISPLAY_NAME = "Example Strategy"
    SUMMARY = "Minimal strategy skeleton for adding a new local harvester."
    CONFIG_SCHEMA = []

    def validate_config(self, source_config):
        """Validate/normalize source config JSON string."""
        if not source_config:
            return source_config

        config_obj = json.loads(source_config)
        # Add custom config validation here.
        return json.dumps(config_obj)

    def gather_stage(self, harvest_job):
        """Create HarvestObject rows and return their IDs."""
        # Add gather logic here.
        return []

    def fetch_stage(self, harvest_object):
        """Optional fetch step. Most strategies can return True."""
        return True

    def import_stage(self, harvest_object):
        """Create/update/delete CKAN datasets from harvest object content."""
        # Add import logic here.
        return True
