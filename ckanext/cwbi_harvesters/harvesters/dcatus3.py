import json
import logging

try:
    import requests  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    requests = None

try:
    from ckan import model  # type: ignore[import-not-found]
    import ckan.plugins.toolkit as toolkit  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    model = None
    toolkit = None

try:
    from ckanext.harvest.harvesters import HarvesterBase  # type: ignore[import-not-found]
    from ckanext.harvest.model import HarvestGatherError  # type: ignore[import-not-found]
    from ckanext.harvest.model import HarvestObject  # type: ignore[import-not-found]
    from ckanext.harvest.model import HarvestObjectError  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class HarvesterBase(object):
        pass

    HarvestGatherError = None
    HarvestObject = None
    HarvestObjectError = None

from ckanext.cwbi_harvesters.harvesters.dcatus3_importer import import_package
from ckanext.cwbi_harvesters.harvesters.dcatus3_transform import transform_catalog
from ckanext.cwbi_harvesters.harvesters.utils import _safe_save


log = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 60


class DcatUs3TransformHarvesterStrategy(HarvesterBase):
    """DCAT-US 3 DataService strategy used by the CWBI harvester plugin."""

    DISPLAY_NAME = "DCAT-US 3 Transform"
    SUMMARY = "Harvest DCAT-US 3 service records as CKAN packages and endpoint resources."
    CONFIG_SCHEMA = []

    def validate_config(self, source_config):
        if not source_config:
            return source_config

        config_obj = json.loads(source_config)
        if not isinstance(config_obj, dict):
            raise ValueError("Harvest source configuration must be a JSON object")
        return json.dumps(config_obj)

    def gather_stage(self, harvest_job):
        try:
            owner_org = self._owner_org_for_source(harvest_job.source)
            catalog = self._load_catalog(harvest_job.source.url)
            transformed = transform_catalog(catalog, owner_org)

            harvest_objects = []
            for skipped in transformed["skipped_records"]:
                self._save_gather_error_safe(
                    "Skipped source record: {0}".format(skipped),
                    harvest_job,
                )

            for package in transformed["packages"]:
                identifier = self._identifier_from_package(package) or package["name"]
                harvest_object = HarvestObject(
                    guid=identifier,
                    job=harvest_job,
                    content=json.dumps({
                        "identifier": identifier,
                        "package": package,
                    }),
                )
                harvest_object.save()
                harvest_objects.append(harvest_object.id)

            log.info(
                "DCAT-US 3 transform gather created %s harvest objects from %s service records",
                len(harvest_objects),
                transformed["summary"]["source_service_record_count"],
            )
            return harvest_objects
        except Exception as exc:
            log.exception("DCAT-US 3 transform gather failed")
            self._save_gather_error_safe(str(exc), harvest_job)
            return None

    def fetch_stage(self, harvest_object):
        try:
            content = self._object_content(harvest_object)
            package = content.get("package")
            if not isinstance(package, dict):
                raise ValueError("harvest object does not contain a package payload")
            if not package.get("name"):
                raise ValueError("package payload is missing name")
            if not package.get("owner_org"):
                raise ValueError("package payload is missing owner_org")
            return True
        except Exception as exc:
            log.exception("DCAT-US 3 transform fetch failed for %s", harvest_object.guid)
            self._save_object_error_safe(str(exc), harvest_object, "Fetch")
            return False

    def import_stage(self, harvest_object):
        try:
            package = self._object_content(harvest_object)["package"]
            result = import_package(self._action_runner, package)
            self._mark_harvest_object_current(harvest_object, result.get("package_id"))
            log.info(
                "DCAT-US 3 transform import %s %s",
                result["action"],
                result["identifier"],
            )
            return True
        except Exception as exc:
            log.exception("DCAT-US 3 transform import failed for %s", harvest_object.guid)
            self._save_object_error_safe(str(exc), harvest_object, "Import")
            return False

    def _mark_harvest_object_current(self, harvest_object, package_id):
        if not package_id:
            raise ValueError("import did not return a CKAN package id")

        self._retire_previous_current_objects(harvest_object)
        harvest_object.current = True
        harvest_object.package_id = package_id
        harvest_object.add()

        if model is not None:
            model.Session.commit()

    def _retire_previous_current_objects(self, harvest_object):
        if model is None or HarvestObject is None:
            return

        query = (
            model.Session.query(HarvestObject)
            .filter(HarvestObject.guid == harvest_object.guid)
            .filter(HarvestObject.current == True)
            .filter(HarvestObject.id != harvest_object.id)
        )

        source_id = self._harvest_source_id(harvest_object)
        if source_id:
            query = query.filter(HarvestObject.harvest_source_id == source_id)

        for previous_object in query.all():
            previous_object.current = False
            previous_object.add()

    def _harvest_source_id(self, harvest_object):
        source_id = getattr(harvest_object, "harvest_source_id", None)
        if source_id:
            return source_id

        source = getattr(harvest_object, "source", None)
        if source is not None and getattr(source, "id", None):
            return source.id

        job = getattr(harvest_object, "job", None)
        source = getattr(job, "source", None) if job is not None else None
        return getattr(source, "id", None)

    def _load_catalog(self, url):
        if requests is None:
            raise RuntimeError("requests is unavailable")
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def _context(self):
        if model is None:
            raise RuntimeError("CKAN model is unavailable")
        return {
            "model": model,
            "session": model.Session,
            "ignore_auth": True,
            "user": self._site_user_name(),
            "api_version": 3,
            "extras_as_string": True,
        }

    def _site_user_name(self):
        get_user_name = getattr(self, "_get_user_name", None)
        if callable(get_user_name):
            return get_user_name()

        if toolkit is not None and model is not None:
            site_user = toolkit.get_action("get_site_user")(
                {
                    "model": model,
                    "session": model.Session,
                    "ignore_auth": True,
                    "defer_commit": True,
                },
                {},
            )
            return site_user["name"]

        raise RuntimeError("CKAN toolkit is unavailable")

    def _ckan_action(self, action_name):
        if toolkit is not None:
            return toolkit.get_action(action_name)

        get_action = getattr(self, "_get_action", None)
        if callable(get_action):
            return get_action(action_name)

        raise RuntimeError("CKAN toolkit is unavailable")

    def _action_runner(self, action_name, data):
        try:
            return self._ckan_action(action_name)(self._context(), data)
        except Exception as exc:
            if action_name == "package_show" and self._is_not_found(exc):
                return None
            raise

    def _owner_org_for_source(self, source):
        source_dataset = self._action_runner("package_show", {"id": source.id})
        owner_org = source_dataset.get("owner_org") if source_dataset else None
        if not owner_org:
            raise ValueError("harvest source is not assigned to a CKAN organization")
        return owner_org

    def _object_content(self, harvest_object):
        try:
            content = json.loads(harvest_object.content or "{}")
        except ValueError as exc:
            raise ValueError("harvest object content is not valid JSON: {0}".format(exc))
        if not isinstance(content, dict):
            raise ValueError("harvest object content is not a JSON object")
        return content

    def _identifier_from_package(self, package):
        for extra in package.get("extras", []) or []:
            if extra.get("key") == "identifier":
                return extra.get("value")
        return ""

    def _is_not_found(self, exc):
        not_found_type = getattr(toolkit, "ObjectNotFound", None) if toolkit is not None else None
        if not_found_type is not None and isinstance(exc, not_found_type):
            return True
        return "not found" in str(exc).lower()

    def _save_gather_error_safe(self, message, harvest_job):
        if HarvestGatherError is not None:
            _safe_save(HarvestGatherError(message=message, job=harvest_job).save)
            return
        _safe_save(self._save_gather_error, message, harvest_job)

    def _save_object_error_safe(self, message, harvest_object, stage):
        if HarvestObjectError is not None:
            _safe_save(
                HarvestObjectError(message=message, object=harvest_object, stage=stage).save
            )
            return
        _safe_save(self._save_object_error, message, harvest_object, stage)