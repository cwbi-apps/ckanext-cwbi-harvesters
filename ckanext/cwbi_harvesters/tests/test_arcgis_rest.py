import json
import copy
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ckanext.cwbi_harvesters.harvesters.arcgis_rest import (
    ArcGISRestHarvesterStrategy,
    arcgis_rest_report,
    canonical_service_url,
    resolve_service_url,
)


def test_resolve_service_url_removes_repeated_current_folder_prefix():
    directory = "https://example.com/arcgis/rest/services/Folder/"

    assert resolve_service_url(directory, "Folder/Roads", "FeatureServer") == (
        "https://example.com/arcgis/rest/services/Folder/Roads/FeatureServer"
    )


def test_resolve_service_url_preserves_current_directory_for_unqualified_name():
    directory = "https://example.com/arcgis/rest/services/Folder/"

    assert resolve_service_url(directory, "Roads", "FeatureServer") == (
        "https://example.com/arcgis/rest/services/Folder/Roads/FeatureServer"
    )


def test_resolve_service_url_rejects_missing_required_fields_even_with_explicit_url():
    directory = "https://example.com/arcgis/rest/services/"
    explicit = "https://example.com/custom/Roads/FeatureServer"

    assert resolve_service_url(directory, None, "FeatureServer", explicit) is None
    assert resolve_service_url(directory, "Roads", None, explicit) is None
    assert resolve_service_url(directory, " ", "FeatureServer", explicit) is None
    assert resolve_service_url(directory, "Roads", " ", explicit) is None


def test_canonical_service_url_removes_json_query_and_trailing_slash():
    assert canonical_service_url(
        "https://example.com/services/Roads/FeatureServer/?f=json"
    ) == "https://example.com/services/Roads/FeatureServer"


def test_canonical_service_url_preserves_non_format_query_parameters():
    assert canonical_service_url(
        "https://example.com/services/Roads/FeatureServer/?token=secret&f=json"
    ) == "https://example.com/services/Roads/FeatureServer?token=secret"


def test_gather_discovers_root_and_nested_services_with_stable_guids():
    responses = {
        "https://example.com/arcgis/rest/services/?f=json": {
            "services": [{"name": "Root", "type": "MapServer"}],
            "folders": ["Folder"],
        },
        "https://example.com/arcgis/rest/services/Folder/?f=json": {
            "services": [{"name": "Folder/Roads", "type": "FeatureServer"}],
            "folders": ["Nested"],
        },
        "https://example.com/arcgis/rest/services/Folder/Nested/?f=json": {
            "services": [
                {
                    "name": "Lakes",
                    "type": "FeatureServer",
                    "url": "https://example.com/custom/Lakes/FeatureServer/?f=json",
                }
            ]
        },
    }

    class HarvestObject:
        next_id = 1
        instances = []

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = HarvestObject.next_id
            HarvestObject.next_id += 1
            HarvestObject.instances.append(self)

        def save(self):
            return None

    def get(url, timeout):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = responses[url]
        return response

    job = SimpleNamespace(
        source=SimpleNamespace(
            url="https://example.com/arcgis/rest/services/",
            config="{}",
        )
    )

    with patch(
        "ckanext.cwbi_harvesters.harvesters.arcgis_rest.requests.get",
        side_effect=get,
    ), patch(
        "ckanext.cwbi_harvesters.harvesters.arcgis_rest.HarvestObject", HarvestObject
    ):
        object_ids = ArcGISRestHarvesterStrategy().gather_stage(job)

    assert len(object_ids) == 3
    assert {obj.guid for obj in HarvestObject.instances} == {
        "https://example.com/arcgis/rest/services/Root/MapServer",
        "https://example.com/arcgis/rest/services/Folder/Roads/FeatureServer",
        "https://example.com/custom/Lakes/FeatureServer",
    }


def test_fetch_stage_retrieves_service_json_and_optional_metadata():
    calls = []

    def get(url, timeout):
        calls.append(url)
        response = Mock()
        response.raise_for_status.return_value = None
        if url.endswith("?f=json"):
            response.json.return_value = {
                "serviceDescription": "Road service",
                "layers": [],
            }
        else:
            response.text = "<metadata />"
        return response

    harvest_object = SimpleNamespace(
        guid="https://example.com/Roads/FeatureServer",
        content=json.dumps(
            {
                "service": {
                    "name": "Roads",
                    "type": "FeatureServer",
                    "url": "https://example.com/Roads/FeatureServer",
                }
            }
        ),
    )

    with patch("ckanext.cwbi_harvesters.harvesters.arcgis_rest.requests.get", side_effect=get):
        assert ArcGISRestHarvesterStrategy().fetch_stage(harvest_object) is True

    assert calls == [
        "https://example.com/Roads/FeatureServer?f=json",
        "https://example.com/Roads/FeatureServer/info/metadata",
    ]
    fetched = json.loads(harvest_object.content)
    assert fetched["payload"]["serviceDescription"] == "Road service"


def test_make_package_dict_uses_endpoint_identity_and_service_title():
    harvester = ArcGISRestHarvesterStrategy()
    harvest_source = SimpleNamespace(
        id="source-id",
        title="Source Title",
        name="source-name",
        url="https://example.com/arcgis/rest/services/",
        owner_org="target-org",
    )
    harvest_object = SimpleNamespace(
        id="object-id",
        guid="https://example.com/Folder/Roads/FeatureServer",
        package_id=None,
        source=harvest_source,
    )
    content = {
        "service": {
            "name": "Folder/Roads",
            "type": "FeatureServer",
            "url": "https://example.com/Folder/Roads/FeatureServer",
        },
        "payload": {
            "serviceDescription": "Road service",
            "copyrightText": "Public domain",
        },
    }

    package = harvester.make_package_dict(harvest_object, content)

    extras = {extra["key"]: extra["value"] for extra in package["extras"]}
    assert package["title"] == "Folder/Roads"
    assert package["owner_org"] == "target-org"
    assert extras["identifier"] == "https://example.com/Folder/Roads/FeatureServer"
    assert extras["arcgis_service_type"] == "FeatureServer"
    assert package["resources"] == [
        {
            "url": "https://example.com/Folder/Roads/FeatureServer",
            "name": "Folder/Roads",
            "format": "FeatureServer",
        }
    ]


def test_arcgis_rest_report_projects_framework_statuses_to_complete_report():
    assert arcgis_rest_report(
        {"added": 2, "updated": 3, "not modified": 4, "errored": 5}
    ) == {
        "discovered": 14,
        "created": 2,
        "updated": 3,
        "skipped": 4,
        "failed": 5,
    }


def test_package_name_collision_uses_deterministic_endpoint_suffix():
    harvester = ArcGISRestHarvesterStrategy()
    endpoint = "https://example.com/other/Roads/FeatureServer"
    harvester._package_by_name = Mock(
        return_value=SimpleNamespace(
            extras=[SimpleNamespace(key="identifier", value="https://example.com/first")]
        )
    )

    name = harvester._package_name(
        "Roads",
        endpoint,
        SimpleNamespace(package_id=None),
    )

    suffix = hashlib.sha1(endpoint.encode("utf-8")).hexdigest()[:8]
    assert name == "roads-{}".format(suffix)
    assert len(name) <= 100


def test_fetch_stage_returns_false_when_service_json_is_unavailable():
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("service unavailable")
    harvest_object = SimpleNamespace(
        guid="https://example.com/Roads/FeatureServer",
        content=json.dumps({
            "service": {
                "name": "Roads",
                "type": "FeatureServer",
                "url": "https://example.com/Roads/FeatureServer",
            }
        }),
    )
    harvester = ArcGISRestHarvesterStrategy()
    harvester._save_object_error = Mock()

    with patch(
        "ckanext.cwbi_harvesters.harvesters.arcgis_rest.requests.get",
        return_value=response,
    ):
        assert harvester.fetch_stage(harvest_object) is False

    harvester._save_object_error.assert_called_once()


def test_fetch_stage_rejects_http_200_arcgis_error_payload():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"error": {"code": 499, "message": "Token required"}}
    harvest_object = SimpleNamespace(
        guid="https://example.com/Roads/FeatureServer",
        content=json.dumps({
            "service": {
                "name": "Roads",
                "type": "FeatureServer",
                "url": "https://example.com/Roads/FeatureServer",
            }
        }),
        save=Mock(),
    )
    harvester = ArcGISRestHarvesterStrategy()
    harvester._save_object_error = Mock()

    with patch(
        "ckanext.cwbi_harvesters.harvesters.arcgis_rest.requests.get",
        return_value=response,
    ):
        assert harvester.fetch_stage(harvest_object) is False

    assert harvest_object.report_status == "errored"
    harvester._save_object_error.assert_called_once()


def test_import_stage_rejects_missing_service_payload():
    harvest_object = SimpleNamespace(
        id="object-id",
        guid="https://example.com/Roads/FeatureServer",
        package_id=None,
        content=json.dumps({
            "service": {
                "name": "Roads",
                "type": "FeatureServer",
                "url": "https://example.com/Roads/FeatureServer",
            }
        }),
        add=Mock(),
        save=Mock(),
    )
    harvester = ArcGISRestHarvesterStrategy()
    harvester._action_runner = Mock()
    harvester._save_object_error = Mock()

    assert harvester.import_stage(harvest_object) is False

    assert harvest_object.report_status == "errored"
    harvester._action_runner.assert_not_called()
    harvester._save_object_error.assert_called_once()


def test_import_stage_updates_existing_package_by_endpoint_without_duplicate():
    class ActionRunner:
        def __init__(self):
            self.package = None
            self.created = 0
            self.updated = 0

        def __call__(self, action_name, data):
            if action_name == "package_search":
                if self.package is None:
                    return {"count": 0, "results": []}
                return {"count": 1, "results": [self.package]}
            if action_name == "package_show":
                return self.package
            if action_name == "package_create":
                self.created += 1
                self.package = copy.deepcopy(data)
                self.package["id"] = "package-1"
                self.package["resources"][0]["id"] = "resource-1"
                return self.package
            if action_name == "package_update":
                self.updated += 1
                self.package = copy.deepcopy(data)
                return self.package
            raise AssertionError("unexpected action {}".format(action_name))

    source = SimpleNamespace(
        id="source-id",
        title="Source",
        name="source",
        owner_org="target-org",
    )
    content = {
        "service": {
            "name": "Roads",
            "type": "FeatureServer",
            "url": "https://example.com/Roads/FeatureServer",
        },
        "payload": {"description": "Road service"},
    }
    first_object = SimpleNamespace(
        id="object-1",
        guid="https://example.com/Roads/FeatureServer",
        package_id=None,
        source=source,
        content=json.dumps(content),
        current=False,
        add=Mock(),
    )
    second_object = SimpleNamespace(
        id="object-2",
        guid="https://example.com/Roads/FeatureServer",
        package_id=None,
        source=source,
        content=json.dumps(dict(content, payload={"description": "Updated road service"})),
        current=False,
        add=Mock(),
    )
    harvester = ArcGISRestHarvesterStrategy()
    actions = ActionRunner()
    harvester._action_runner = actions

    assert harvester.import_stage(first_object) is True
    assert harvester.import_stage(second_object) is True
    assert actions.created == 1
    assert actions.updated == 1
    assert first_object.report_status == "added"
    assert second_object.report_status == "updated"
    assert second_object.package_id == "package-1"
    assert len(actions.package["resources"]) == 1


def test_import_stage_reports_unchanged_service_as_skipped():
    package = {
        "id": "package-1",
        "name": "roads",
        "extras": [],
        "resources": [],
    }
    source = SimpleNamespace(
        id="source-id", title="Source", name="source", owner_org="target-org"
    )
    content = {
        "service": {
            "name": "Roads",
            "type": "FeatureServer",
            "url": "https://example.com/Roads/FeatureServer",
        },
        "payload": {"description": "Road service"},
    }
    harvester = ArcGISRestHarvesterStrategy()
    harvester._action_runner = Mock(
        side_effect=lambda action_name, data: (
            {"count": 1, "results": [package]}
            if action_name == "package_search"
            else package
        )
    )
    package["extras"] = harvester.make_package_dict(
        SimpleNamespace(id="old-object", source=source, package_id=None), content
    )["extras"]
    harvest_object = SimpleNamespace(
        id="object-id",
        guid="https://example.com/Roads/FeatureServer",
        package_id=None,
        source=source,
        content=json.dumps(content),
        add=Mock(),
        save=Mock(),
    )

    assert harvester.import_stage(harvest_object) == "unchanged"
    assert harvest_object.report_status == "not modified"
    assert harvest_object.add.call_count == 0
