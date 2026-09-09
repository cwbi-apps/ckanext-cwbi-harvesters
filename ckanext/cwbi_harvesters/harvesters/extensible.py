import logging

try:
    import ckan.plugins as plugins  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    plugins = None

try:
    import ckan.plugins.toolkit as toolkit  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    toolkit = None

try:
    from ckanext.harvest.harvesters import HarvesterBase  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class HarvesterBase(object):
        pass

from ckanext.cwbi_harvesters.harvesters.registry import get_harvester_alias
from ckanext.cwbi_harvesters.harvesters.registry import resolve_harvester_class


log = logging.getLogger(__name__)


def _chained_action(function):
    if toolkit is None:
        return function
    return toolkit.chained_action(function)


def _side_effect_free(function):
    if toolkit is None:
        return function
    return toolkit.side_effect_free(function)


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


class DcatUs3TransformHarvester(CwbiHarvesters):
    """Concrete DCAT-US 3 transform harvester type shown in CKAN harvest source UI."""

    def info(self):
        return {
            "name": "dcat_us_3_transform",
            "title": "DCAT-US 3 Transform",
            "description": (
                "Harvest DCAT-US 3 service records as CKAN packages and endpoint resources"
            ),
            "form_config_interface": "Text",
        }

    def _delegate_for_source_config(self, source_config):
        return resolve_harvester_class("dcat_us_3_transform")()


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


class CwbiEsriRestHarvester(CwbiHarvesters):
    """Concrete ArcGIS REST Services harvester type shown in CKAN."""

    if plugins is not None:
        plugins.implements(plugins.IActions)

    def info(self):
        return {
            "name": "cwbi_esri_rest",
            "title": "ArcGIS REST Services",
            "description": "Harvest datasets from ArcGIS REST Services directories",
            "form_config_interface": "Text",
        }

    def _delegate_for_source_config(self, source_config):
        return resolve_harvester_class("cwbi_esri_rest")()

    def get_actions(self):
        """Add the ArcGIS report to the native harvest job responses."""
        return {
            "harvest_job_show": self.harvest_job_show,
            "harvest_source_show_status": self.harvest_source_show_status,
        }

    @_chained_action
    @_side_effect_free
    def harvest_job_show(self, original_action, context, data_dict):
        result = original_action(context, data_dict)
        job = self._job_for_report(data_dict.get("id"))
        return self._decorate_report(result, job)

    @_chained_action
    @_side_effect_free
    def harvest_source_show_status(self, original_action, context, data_dict):
        result = original_action(context, data_dict)
        source = self._source_for_report(data_dict.get("id"))
        last_job = result.get("last_job") if isinstance(result, dict) else None
        if source is not None and last_job:
            job = self._job_for_report(last_job.get("id"))
            result["last_job"] = self._decorate_report(last_job, job)
        return result

    def _decorate_report(self, result, job):
        if not self._is_rest_source(job.source if job is not None else None):
            return result
        from ckanext.cwbi_harvesters.harvesters.arcgis_rest import (
            arcgis_rest_report,
        )

        decorated = dict(result)
        decorated["arcgis_rest_report"] = arcgis_rest_report(result.get("stats"))
        return decorated

    @staticmethod
    def _is_rest_source(source):
        if source is None:
            return False
        if getattr(source, "type", None) == "cwbi_esri_rest":
            return True
        try:
            import json

            config = json.loads(getattr(source, "config", "") or "{}")
        except (TypeError, ValueError):
            return False
        return (
            isinstance(config, dict)
            and (config.get("harvester") or config.get("harvester_type"))
            == "cwbi_esri_rest"
        )

    @staticmethod
    def _job_for_report(job_id):
        from ckanext.harvest.model import HarvestJob

        return HarvestJob.get(job_id)

    @staticmethod
    def _source_for_report(source_id):
        from ckanext.harvest.model import HarvestSource

        return HarvestSource.get(source_id)
