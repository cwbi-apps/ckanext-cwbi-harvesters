import json
import logging
import re
import unicodedata
import urllib.parse
import uuid
from html.parser import HTMLParser
from string import Template

import requests  # type: ignore[import-not-found]
import sqlalchemy as sa  # type: ignore[import-not-found]

from ckan import logic  # type: ignore[import-not-found]
from ckan import model  # type: ignore[import-not-found]
from ckan.logic import ValidationError  # type: ignore[import-not-found]
from ckanext.harvest.logic.schema import unicode_safe  # type: ignore[import-not-found]
from ckanext.harvest.model import HarvestObject  # type: ignore[import-not-found]
from ckanext.harvest.model import HarvestObjectExtra  # type: ignore[import-not-found]
from ckanext.harvest.harvesters import HarvesterBase  # type: ignore[import-not-found]
from ckanext.cwbi_harvesters.harvesters.utils import _safe_save


log = logging.getLogger(__name__)

TYPES = [
    "Web Map",
    "KML",
    "Mobile Application",
    "Web Mapping Application",
    "WMS",
    "Map Service",
]

_slugify_strip_re = re.compile(r"[^\w\s-]")
_slugify_hyphenate_re = re.compile(r"[-\s]+")


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, data):
        self.fed.append(data)

    def get_data(self):
        return "".join(self.fed)


def _slugify(value):
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize("NFKD", value)
    value = str(_slugify_strip_re.sub("", value).strip().lower())
    return _slugify_hyphenate_re.sub("-", value)


def strip_tags(html):
    parser = MLStripper()
    parser.feed(html or "")
    return parser.get_data()


class ArcGISHarvesterStrategy(HarvesterBase):

    """ArcGIS strategy used by CwbiHarvesters delegation."""

    DISPLAY_NAME = "ArcGIS REST"
    SUMMARY = "Harvest datasets from ArcGIS REST search endpoints."
    CONFIG_SCHEMA = [
        {
            "key": "private_datasets",
            "type": "boolean",
            "default": False,
            "description": "Create harvested datasets as private in CKAN.",
        },
        {
            "key": "extra_search_criteria",
            "type": "string",
            "description": "Additional ArcGIS search clause appended to the modified date query.",
        },
    ]

    extent_template = Template(
        (
            '{"type": "Polygon", "coordinates": [[[$minx, $miny], '
            "[$minx, $maxy], [$maxx, $maxy], [$maxx, $miny], [$minx, $miny]]]}"
        )
    )

    def validate_config(self, source_config):
        if not source_config:
            return source_config

        config_obj = json.loads(source_config)
        if "private_datasets" in config_obj:
            config_obj["private_datasets"] = bool(config_obj["private_datasets"])

        if "extra_search_criteria" in config_obj:
            config_obj["extra_search_criteria"] = str(config_obj["extra_search_criteria"])

        return json.dumps(config_obj)

    def gather_stage(self, harvest_job):
        source_url = harvest_job.source.url.rstrip("/") + "/"
        source_config = json.loads(harvest_job.source.config or "{}")
        extra_search_criteria = source_config.get("extra_search_criteria")

        num = 100
        modified_from = 0
        modified_to = 999999999999999999

        query_template = "modified:%5B{modified_from}%20TO%20{modified_to}%5D"
        if extra_search_criteria:
            query_template = query_template + " AND ({0})".format(extra_search_criteria)

        query = query_template.format(
            modified_from=str(modified_from).rjust(18, "0"),
            modified_to=str(modified_to).rjust(18, "0"),
        )

        start = 0
        new_metadata = {}

        while start != -1:
            search_path = "sharing/search?f=pjson&q={query}&num={num}&start={start}".format(
                query=query,
                num=num,
                start=start,
            )
            try:
                url = urllib.parse.urljoin(source_url, search_path)
            except TypeError as exc:
                _safe_save(self._save_gather_error,
                    "Unable to build url ({0}, {1}): {2}".format(source_url, search_path, exc),
                    harvest_job,
                )
                return None

            try:
                response = requests.get(url)
                response.raise_for_status()
            except requests.exceptions.RequestException as exc:
                _safe_save(self._save_gather_error,
                    "Unable to get content for URL: {0}: {1!r}".format(url, exc),
                    harvest_job,
                )
                return None

            results = response.json()
            for result in results.get("results", []):
                if result.get("type") not in TYPES:
                    continue
                if result.get("id"):
                    new_metadata[result["id"]] = result

            start = results.get("nextStart", -1)

        existing_guids = {}
        query = (
            model.Session.query(HarvestObject.guid, HarvestObjectExtra.value)
            .join(HarvestObjectExtra, HarvestObject.extras)
            .filter(HarvestObject.current == True)
            .filter(HarvestObjectExtra.key == "arcgis_modified_date")
            .filter(HarvestObject.harvest_source_id == harvest_job.source.id)
        )

        for guid, value in query:
            existing_guids[guid] = value

        harvest_objects = []

        for guid in (set(new_metadata) - set(existing_guids)):
            date = str(new_metadata[guid].get("modified", ""))
            obj = HarvestObject(
                job=harvest_job,
                content=json.dumps(new_metadata[guid]),
                extras=[
                    HarvestObjectExtra(key="arcgis_modified_date", value=date),
                    HarvestObjectExtra(key="format", value="arcgis_json"),
                    HarvestObjectExtra(key="status", value="new"),
                ],
                guid=guid,
            )
            obj.save()
            harvest_objects.append(obj.id)

        for guid in (set(existing_guids) - set(new_metadata)):
            obj = HarvestObject(
                job=harvest_job,
                extras=[HarvestObjectExtra(key="status", value="delete")],
                guid=guid,
            )
            obj.save()
            harvest_objects.append(obj.id)

        for guid in (set(existing_guids) & set(new_metadata)):
            date = str(new_metadata[guid].get("modified", ""))
            if date == existing_guids[guid]:
                continue
            obj = HarvestObject(
                job=harvest_job,
                content=json.dumps(new_metadata[guid]),
                extras=[
                    HarvestObjectExtra(key="arcgis_modified_date", value=date),
                    HarvestObjectExtra(key="format", value="arcgis_json"),
                    HarvestObjectExtra(key="status", value="changed"),
                ],
                guid=guid,
            )
            obj.save()
            harvest_objects.append(obj.id)

        return harvest_objects

    def fetch_stage(self, harvest_object):
        return True

    def _get_object_extra(self, harvest_object, key):
        for extra in harvest_object.extras:
            if extra.key == key:
                return extra.value
        return None

    def import_stage(self, harvest_object):
        log.debug("Import stage for harvest object: %s", harvest_object.id)

        if not harvest_object:
            log.error("No harvest object received")
            return False

        source_config = json.loads(harvest_object.source.config or "{}")
        status = self._get_object_extra(harvest_object, "status")

        previous_object = (
            model.Session.query(HarvestObject)
            .filter(HarvestObject.guid == harvest_object.guid)
            .filter(HarvestObject.current == True)
            .first()
        )

        if previous_object:
            previous_object.current = False
            harvest_object.package_id = previous_object.package_id
            previous_object.add()

        context = {
            "model": model,
            "session": model.Session,
            "ignore_auth": True,
            "user": self._get_user_name(),
            "api_version": 3,
            "extras_as_string": True,
        }

        if status == "delete":
            if harvest_object.package_id:
                self._get_action("package_delete")(context, {"id": harvest_object.package_id})
                log.info(
                    "Deleted package %s with guid %s",
                    harvest_object.package_id,
                    harvest_object.guid,
                )
            model.Session.commit()
            return True

        if harvest_object.content is None:
            _safe_save(self._save_object_error,
                "Empty content for object {0}".format(harvest_object.id),
                harvest_object,
                "Import",
            )
            return False

        content = json.loads(harvest_object.content)
        package_dict = self.make_package_dict(harvest_object, content)
        if not package_dict:
            return False

        if status == "new":
            package_schema = logic.schema.default_create_package_schema()
        else:
            package_schema = logic.schema.default_update_package_schema()

        package_schema["id"] = [unicode_safe]
        context["schema"] = package_schema

        harvest_object.current = True
        harvest_object.add()

        if status == "new":
            package_dict["id"] = str(uuid.uuid4())
            harvest_object.package_id = package_dict["id"]
            harvest_object.add()

            model.Session.execute(
                sa.text("SET CONSTRAINTS harvest_object_package_id_fkey DEFERRED")
            )
            model.Session.flush()

            package_dict["private"] = bool(source_config.get("private_datasets", False))

            try:
                package_id = self._get_action("package_create")(context, package_dict)
                log.info("Created new package %s with guid %s", package_id, harvest_object.guid)
            except ValidationError as exc:
                _safe_save(self._save_object_error,
                    "Validation Error: {0}".format(str(exc.error_summary)),
                    harvest_object,
                    "Import",
                )
                return False

        elif status == "changed":
            package_dict["id"] = harvest_object.package_id
            try:
                package_id = self._get_action("package_update")(context, package_dict)
                log.info("Updated package %s with guid %s", package_id, harvest_object.guid)
            except ValidationError as exc:
                _safe_save(self._save_object_error,
                    "Validation Error: {0}".format(str(exc.error_summary)),
                    harvest_object,
                    "Import",
                )
                return False

        model.Session.commit()
        return True

    def make_package_dict(self, harvest_object, content):
        name = _slugify(content.get("title") or content.get("item", ""))
        if not name or len(name) < 5:
            name = content.get("id", "")

        name = name[:60]
        existing_pkg = model.Package.get(name)
        if existing_pkg and existing_pkg.id != harvest_object.package_id:
            name = "{0}_{1}".format(name, content.get("id", ""))

        title = content.get("title")
        tag_list = [tag.strip('"').strip() for tag in content.get("tags", [])]
        tags = ",".join(tag_list)

        notes = strip_tags(content.get("description") or "")
        if not notes:
            notes = strip_tags(content.get("snippet") or "")

        extras = [
            {"key": "guid", "value": harvest_object.guid},
            {"key": "metadata_source", "value": "arcgis"},
            {"key": "metadata_type", "value": "geospatial"},
            {"key": "tags", "value": tags},
        ]

        extent = content.get("extent")
        if extent:
            extent_string = self.extent_template.substitute(
                minx=extent[0][0],
                miny=extent[0][1],
                maxx=extent[1][0],
                maxy=extent[1][1],
            )
            extras.append({"key": "spatial", "value": extent_string.strip()})

        source_url = harvest_object.source.url.rstrip("/") + "/"

        resources = []
        resource_url = content.get("url")
        if content.get("type") == "Map Service":
            resources.append(
                {
                    "url": resource_url,
                    "name": name,
                    "format": "ArcGIS Map Service",
                }
            )

        resource_format = (content.get("type") or "").upper()

        if content.get("type") == "Web Map":
            resource_url = urllib.parse.urljoin(
                source_url,
                "home/webmap/viewer.html?webmap=" + content.get("id", ""),
            )

        if content.get("type") == "Map Service":
            resource_url = urllib.parse.urljoin(
                source_url,
                "home/webmap/viewer.html?services=" + content.get("id", ""),
            )
            resource_format = "ArcGIS MAP Preview"

        if not resource_url:
            _safe_save(self._save_object_error,
                "Validation Error: url not in record",
                harvest_object,
                "Import",
            )
            return False

        if not resource_url.startswith("http"):
            resource_url = urllib.parse.urljoin(source_url, resource_url)

        if content.get("type") in ["Web Map", "Web Mapping Application"]:
            resource_format = "Web Map Application"

        resource = {
            "url": resource_url,
            "name": name,
            "format": resource_format,
        }
        resources.append(resource)

        pkg = model.Package.get(harvest_object.package_id)
        if pkg and pkg.resources:
            resource["id"] = pkg.resources[0].id

        package_dict = {
            "name": name.lower(),
            "title": title,
            "notes": notes,
            "extras": extras,
            "resources": resources,
        }

        source_dataset = model.Package.get(harvest_object.source.id)
        if source_dataset and source_dataset.owner_org:
            package_dict["owner_org"] = source_dataset.owner_org

        return package_dict


ArcGISHarvester = ArcGISHarvesterStrategy
