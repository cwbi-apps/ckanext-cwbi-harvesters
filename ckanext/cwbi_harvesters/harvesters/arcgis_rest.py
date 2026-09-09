import hashlib
import json
import logging
import re
import unicodedata
import urllib.parse

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
    from ckanext.harvest.model import HarvestObjectExtra  # type: ignore[import-not-found]
    from ckanext.harvest.model import HarvestObjectError  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    class HarvesterBase(object):
        pass

    HarvestObject = None
    HarvestObjectExtra = None
    HarvestGatherError = None
    HarvestObjectError = None

from ckanext.cwbi_harvesters.harvesters.dcatus3_importer import (
    apply_existing_resource_ids,
    find_existing_package,
    package_id_from_action_result,
)
from ckanext.cwbi_harvesters.harvesters.utils import _safe_save


log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
_slugify_re = re.compile(r"[^a-z0-9]+")
REPORT_STATUSES = ("added", "updated", "not modified", "errored", "deleted")


def arcgis_rest_report(stats):
    """Project ckanext-harvest stats into the ArcGIS acceptance vocabulary."""
    normalized = {status: int((stats or {}).get(status, 0)) for status in REPORT_STATUSES}
    return {
        "discovered": sum(normalized[status] for status in REPORT_STATUSES[:-1]),
        "created": normalized["added"],
        "updated": normalized["updated"],
        "skipped": normalized["not modified"],
        "failed": normalized["errored"],
    }


def canonical_service_url(url):
    """Return a service endpoint without request parameters or a trailing slash."""
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    path = parsed.path.rstrip("/")
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query)
        if key != "f"
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), "")
    )


def _canonical_directory_url(url):
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    path = parsed.path.rstrip("/") + "/"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _is_usable_url(url):
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _service_context_parts(directory_url):
    path_parts = [part for part in urllib.parse.urlsplit(directory_url).path.split("/") if part]
    try:
        services_index = path_parts.index("services")
    except ValueError:
        return []
    return path_parts[services_index + 1 :]


def _remove_repeated_context_prefix(name_parts, context_parts):
    for size in range(len(context_parts), 0, -1):
        if name_parts[:size] == context_parts[-size:]:
            return name_parts[size:]
    return name_parts


def _join_directory(directory_url, parts):
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in parts if part)
    return _canonical_directory_url(urllib.parse.urljoin(directory_url, quoted))


def resolve_service_url(directory_url, service_name, service_type, explicit_url=None):
    """Resolve a service entry according to DM-CKAN-07."""
    name_parts = [
        part for part in str(service_name or "").strip("/").split("/") if part.strip()
    ]
    service_type = str(service_type or "").strip().strip("/")
    if not name_parts or not service_type:
        return None
    if _is_usable_url(explicit_url):
        return canonical_service_url(explicit_url)
    if not _is_usable_url(directory_url):
        return None

    context_parts = _service_context_parts(directory_url)
    remaining_parts = _remove_repeated_context_prefix(name_parts, context_parts)
    if not remaining_parts:
        remaining_parts = name_parts[-1:]

    endpoint = _join_directory(directory_url, remaining_parts + [service_type])
    return canonical_service_url(endpoint)


def _request_url(url):
    parsed = urllib.parse.urlsplit(url)
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parsed.query) if key != "f"]
    query.append(("f", "json"))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def _slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    name = _slugify_re.sub("-", normalized).strip("-")[:100]
    return name if len(name) >= 2 else "arcgis-service"


def _upsert_extra(extras, key, value):
    value = str(value)
    for extra in extras:
        if extra.get("key") == key:
            extra["value"] = value
            return
    extras.append({"key": key, "value": value})


class ArcGISRestHarvesterStrategy(HarvesterBase):
    """Harvest ArcGIS REST Services directories into CKAN datasets."""

    DISPLAY_NAME = "ArcGIS REST Services"
    SUMMARY = "Harvest datasets from ArcGIS REST Services directories."
    CONFIG_SCHEMA = []

    def validate_config(self, source_config):
        if not source_config:
            return source_config
        config = json.loads(source_config)
        if not isinstance(config, dict):
            raise ValueError("Harvest source configuration must be a JSON object")
        return json.dumps(config)

    def gather_stage(self, harvest_job):
        source_url = _canonical_directory_url(harvest_job.source.url)
        records = self._discover_services(source_url, harvest_job)
        if HarvestObject is None:
            raise RuntimeError("CKAN harvest model is unavailable")

        object_ids = []
        for record in records:
            extras = []
            if HarvestObjectExtra is not None:
                extras = [
                    HarvestObjectExtra(key="format", value="arcgis_rest_json"),
                    HarvestObjectExtra(key="status", value="new"),
                ]
            harvest_object = HarvestObject(
                guid=record["url"],
                job=harvest_job,
                content=json.dumps({"service": record}),
                extras=extras,
            )
            harvest_object.save()
            object_ids.append(harvest_object.id)

        log.info("ArcGIS REST gather discovered %s services", len(object_ids))
        return object_ids

    def fetch_stage(self, harvest_object):
        try:
            content = self._object_content(harvest_object)
            service = content.get("service") or {}
            endpoint = canonical_service_url(service.get("url") or harvest_object.guid)
            payload = self._load_json(endpoint)
            content["payload"] = payload

            metadata = self._load_optional_metadata(endpoint, service.get("type"))
            if metadata:
                content["metadata"] = metadata
            harvest_object.content = json.dumps(content)
            return True
        except Exception as exc:
            log.exception("ArcGIS REST fetch failed for %s", getattr(harvest_object, "guid", ""))
            self._set_report_status(harvest_object, "errored")
            self._save_object_error_safe(str(exc), harvest_object, "Fetch")
            return False

    def import_stage(self, harvest_object):
        try:
            content = self._object_content(harvest_object)
            package = self.make_package_dict(harvest_object, content)
            existing = find_existing_package(self._action_runner, package)
            if existing and self._package_is_unchanged(existing["match"], package):
                self._set_report_status(harvest_object, "not modified")
                log.info(
                    "ArcGIS REST import skipped unchanged %s",
                    self._extra_value(package, "identifier"),
                )
                return "unchanged"
            if existing:
                package["id"] = existing["match"]["id"]
                package["name"] = existing["match"].get("name", package["name"])
                apply_existing_resource_ids(package, existing["match"])
                result = self._action_runner("package_update", package)
                action = "updated"
                package_id = package_id_from_action_result(result, package["id"])
            else:
                result = self._action_runner("package_create", package)
                action = "created"
                package_id = package_id_from_action_result(result)

            if not package_id:
                raise ValueError("CKAN package action did not return a package id")
            self._set_report_status(harvest_object, "updated" if existing else "added")
            self._mark_harvest_object_current(harvest_object, package_id)
            log.info("ArcGIS REST import %s %s", action, self._extra_value(package, "identifier"))
            return True
        except Exception as exc:
            log.exception("ArcGIS REST import failed for %s", getattr(harvest_object, "guid", ""))
            self._set_report_status(harvest_object, "errored")
            self._save_object_error_safe(str(exc), harvest_object, "Import")
            return False

    def make_package_dict(self, harvest_object, content):
        service = content.get("service") or {}
        payload = content.get("payload")
        if not isinstance(payload, dict) or "error" in payload:
            raise ValueError("ArcGIS service payload is missing or reports an error")
        endpoint = canonical_service_url(service.get("url") or harvest_object.guid)
        title = str(service.get("name") or endpoint)
        name = self._package_name(title, endpoint, harvest_object)
        service_type = str(service.get("type") or "ArcGIS REST")
        notes = payload.get("serviceDescription") or payload.get("description") or ""
        extras = [
            {"key": "identifier", "value": endpoint},
            {"key": "arcgis_service_url", "value": endpoint},
            {"key": "arcgis_service_type", "value": service_type},
            {
                "key": "arcgis_payload_hash",
                "value": self._payload_hash(payload),
            },
            {"key": "metadata_source", "value": "arcgis_rest"},
            {"key": "metadata_type", "value": "geospatial"},
        ]
        source = getattr(harvest_object, "source", None)
        if source is not None:
            _upsert_extra(extras, "harvest_source_id", getattr(source, "id", ""))
            _upsert_extra(extras, "harvest_source_title", getattr(source, "title", ""))
            if getattr(source, "name", None):
                _upsert_extra(extras, "harvest_source_name", source.name)
        _upsert_extra(extras, "harvest_object_id", getattr(harvest_object, "id", ""))

        package = {
            "name": name,
            "title": title,
            "notes": notes,
            "extras": extras,
            "resources": [{"url": endpoint, "name": title, "format": service_type}],
            "private": False,
        }
        owner_org = getattr(source, "owner_org", None) if source is not None else None
        if source is not None and not owner_org:
            owner_org = self._owner_org_for_source(source)
        if owner_org:
            package["owner_org"] = owner_org
        return package

    def _discover_services(self, landing_url, harvest_job):
        pending = [landing_url]
        visited_directories = set()
        seen_services = set()
        records = []

        while pending:
            directory_url = pending.pop(0)
            if directory_url in visited_directories:
                continue
            visited_directories.add(directory_url)
            try:
                payload = self._load_json(directory_url)
            except Exception as exc:
                self._save_gather_error_safe(
                    "Unable to retrieve ArcGIS directory {0}: {1}".format(directory_url, exc),
                    harvest_job,
                )
                continue

            for service in payload.get("services") or []:
                if not isinstance(service, dict):
                    self._save_gather_error_safe(
                        "Skipped malformed ArcGIS service entry", harvest_job
                    )
                    continue
                endpoint = resolve_service_url(
                    directory_url,
                    service.get("name"),
                    service.get("type"),
                    service.get("url"),
                )
                if not endpoint:
                    self._save_gather_error_safe(
                        "Skipped ArcGIS service without name, type, or usable URL: {0}".format(
                            service
                        ),
                        harvest_job,
                    )
                    continue
                if endpoint in seen_services:
                    self._save_gather_error_safe(
                        "Skipped duplicate ArcGIS service endpoint: {0}".format(endpoint),
                        harvest_job,
                    )
                    continue
                seen_services.add(endpoint)
                records.append({
                    "name": str(service.get("name")),
                    "type": str(service.get("type")),
                    "url": endpoint,
                })

            for folder in payload.get("folders") or []:
                folder_url = self._resolve_folder_url(directory_url, folder)
                if folder_url:
                    pending.append(folder_url)

        return records

    def _resolve_folder_url(self, directory_url, folder):
        if _is_usable_url(folder):
            return _canonical_directory_url(folder)
        folder_parts = [part for part in str(folder or "").strip("/").split("/") if part]
        if not folder_parts:
            return None
        remaining = _remove_repeated_context_prefix(
            folder_parts, _service_context_parts(directory_url)
        )
        return _join_directory(directory_url, remaining or folder_parts)

    def _load_json(self, url):
        if requests is None:
            raise RuntimeError("requests is unavailable")
        response = requests.get(_request_url(url), timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ArcGIS response must be a JSON object")
        if "error" in payload:
            raise ValueError("ArcGIS response reports an error: {}".format(payload["error"]))
        return payload

    def _load_optional_metadata(self, endpoint, service_type):
        if requests is None:
            return None
        metadata_path = "metadata" if service_type == "ImageServer" else "info/metadata"
        url = endpoint.rstrip("/") + "/" + metadata_path
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as exc:
            log.info("Optional ArcGIS metadata unavailable at %s: %s", url, exc)
            return None

    def _object_content(self, harvest_object):
        content = json.loads(harvest_object.content or "{}")
        if not isinstance(content, dict):
            raise ValueError("harvest object content must be a JSON object")
        return content

    def _package_name(self, title, endpoint, harvest_object):
        existing_name = self._existing_package_name(harvest_object)
        if existing_name:
            return existing_name
        base = _slugify(title)
        existing = self._package_by_name(base)
        if existing and self._extra_value(existing, "identifier") != endpoint:
            suffix = hashlib.sha1(endpoint.encode("utf-8")).hexdigest()[:8]
            base = "{}-{}".format(base[: 100 - len(suffix) - 1].rstrip("-"), suffix)
        return base[:100].rstrip("-")

    def _existing_package_name(self, harvest_object):
        package_id = getattr(harvest_object, "package_id", None)
        if not package_id or model is None or not hasattr(model, "Package"):
            return None
        package = model.Package.get(package_id)
        return getattr(package, "name", None) if package is not None else None

    def _package_by_name(self, name):
        if model is None or not hasattr(model, "Package"):
            return None
        return model.Package.get(name)

    @staticmethod
    def _payload_hash(payload):
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _package_is_unchanged(self, existing, candidate):
        return (
            self._extra_value(existing, "identifier")
            == self._extra_value(candidate, "identifier")
            and self._extra_value(existing, "arcgis_payload_hash")
            == self._extra_value(candidate, "arcgis_payload_hash")
            and bool(self._extra_value(existing, "arcgis_payload_hash"))
        )

    @staticmethod
    def _extra_value(package, key):
        extras = (
            package.get("extras", [])
            if isinstance(package, dict)
            else getattr(package, "extras", [])
        )
        for extra in extras or []:
            if getattr(extra, "key", None) == key:
                return getattr(extra, "value", "")
            if isinstance(extra, dict) and extra.get("key") == key:
                return extra.get("value", "")
        return ""

    def _action_runner(self, action_name, data):
        try:
            return self._ckan_action(action_name)(self._context(), data)
        except Exception as exc:
            if action_name == "package_show" and self._is_not_found(exc):
                return None
            raise

    def _ckan_action(self, action_name):
        if toolkit is not None:
            return toolkit.get_action(action_name)
        get_action = getattr(self, "_get_action", None)
        if callable(get_action):
            return get_action(action_name)
        raise RuntimeError("CKAN toolkit is unavailable")

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

    def _owner_org_for_source(self, source):
        if getattr(source, "owner_org", None):
            return source.owner_org
        source_dataset = self._action_runner("package_show", {"id": source.id})
        owner_org = source_dataset.get("owner_org") if source_dataset else None
        if not owner_org:
            raise ValueError("harvest source is not assigned to a CKAN organization")
        return owner_org

    def _is_not_found(self, exc):
        not_found_type = (
            getattr(toolkit, "ObjectNotFound", None) if toolkit is not None else None
        )
        return (not_found_type is not None and isinstance(exc, not_found_type)) or (
            "not found" in str(exc).lower()
        )

    def _mark_harvest_object_current(self, harvest_object, package_id):
        if not package_id:
            raise ValueError("import did not return a CKAN package id")
        self._retire_previous_current_objects(harvest_object)
        harvest_object.current = True
        harvest_object.package_id = package_id
        add = getattr(harvest_object, "add", None)
        if callable(add):
            add()
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
        source = getattr(harvest_object, "source", None)
        source_id = getattr(source, "id", None)
        if source_id:
            query = query.filter(HarvestObject.harvest_source_id == source_id)
        for previous_object in query.all():
            previous_object.current = False
            previous_object.add()

    def _save_gather_error_safe(self, message, harvest_job):
        if HarvestGatherError is not None:
            _safe_save(HarvestGatherError(message=message, job=harvest_job).save)
            return
        method = getattr(self, "_save_gather_error", None)
        if callable(method):
            _safe_save(method, message, harvest_job)
        else:
            log.warning("ArcGIS REST gather: %s", message)

    def _save_object_error_safe(self, message, harvest_object, stage):
        if HarvestObjectError is not None:
            _safe_save(
                HarvestObjectError(message=message, object=harvest_object, stage=stage).save
            )
            return
        method = getattr(self, "_save_object_error", None)
        if callable(method):
            _safe_save(method, message, harvest_object, stage)
        else:
            log.warning("ArcGIS REST %s: %s", stage, message)

    @staticmethod
    def _set_report_status(harvest_object, status):
        """Set the status consumed by ckanext-harvest's completed job report."""
        harvest_object.report_status = status
        save = getattr(harvest_object, "save", None)
        if callable(save):
            _safe_save(save)
