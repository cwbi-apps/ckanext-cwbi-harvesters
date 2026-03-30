import logging

try:
    from ckanext.harvest.harvesters import HarvesterBase  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class HarvesterBase(object):
        pass

from ckanext.cwbi_harvesters.harvesters.registry import get_harvester_alias
from ckanext.cwbi_harvesters.harvesters.registry import resolve_harvester_class


log = logging.getLogger(__name__)


class CwbiHarvesters(HarvesterBase):
    """
    Delegates the harvest lifecycle to a configured harvester implementation.

    Harvest source configuration can include one of:
      - harvester
      - harvester_type

    Accepted values:
            - A local alias defined in ckanext.cwbi_harvesters.harvesters.registry
    """

    def info(self):
        return {
            "name": "cwbi_harvesters",
            "title": "CWBI Harvesters",
            "description": "Delegates to local harvester strategies in this package",
            "form_config_interface": "Text",
        }

    def _delegate_for_source_config(self, source_config):
        alias = get_harvester_alias(source_config)
        harvester_class = resolve_harvester_class(alias)
        return harvester_class()

    def _call_delegate(self, delegate, method_name, *args):
        method = getattr(delegate, method_name, None)
        if not callable(method):
            raise TypeError(
                "Configured harvester '{0}' does not implement '{1}'".format(
                    delegate.__class__.__name__, method_name
                )
            )
        return method(*args)

    def validate_config(self, source_config):
        delegate = self._delegate_for_source_config(source_config)
        method = getattr(delegate, "validate_config", None)
        if not callable(method):
            return source_config
        return method(source_config)

    def gather_stage(self, harvest_job):
        delegate = self._delegate_for_source_config(harvest_job.source.config)
        return self._call_delegate(delegate, "gather_stage", harvest_job)

    def fetch_stage(self, harvest_object):
        delegate = self._delegate_for_source_config(harvest_object.source.config)
        return self._call_delegate(delegate, "fetch_stage", harvest_object)

    def import_stage(self, harvest_object):
        delegate = self._delegate_for_source_config(harvest_object.source.config)
        return self._call_delegate(delegate, "import_stage", harvest_object)


class CwbiEsriHarvester(CwbiHarvesters):
    """Concrete ESRI harvester type shown in CKAN harvest source UI."""

    def info(self):
        return {
            "name": "cwbi_esri",
            "title": "ESRI Harvester",
            "description": "Harvest datasets from ArcGIS REST search endpoints",
            "form_config_interface": "Text",
        }

    def _delegate_for_source_config(self, source_config):
        return resolve_harvester_class("cwbi_esri")()
