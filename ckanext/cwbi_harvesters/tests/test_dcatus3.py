import copy
import json
import re

import ckanext.cwbi_harvesters.harvesters.dcatus3 as dcatus3_module
from ckanext.cwbi_harvesters.harvesters.dcatus3 import DcatUs3TransformHarvesterStrategy
from ckanext.cwbi_harvesters.harvesters.dcatus3_importer import import_package
from ckanext.cwbi_harvesters.harvesters.dcatus3_transform import sanitize_package_name
from ckanext.cwbi_harvesters.harvesters.dcatus3_transform import sanitize_tag
from ckanext.cwbi_harvesters.harvesters.dcatus3_transform import transform_catalog


def package_identifier(package):
    for extra in package.get("extras", []):
        if extra.get("key") == "identifier":
            return extra.get("value")
    return ""


class FakeCkanActions:
    def __init__(self):
        self.packages = {}
        self.created = []
        self.updated = []
        self.next_id = 1
        self.next_resource_id = 1
        self.solr_prefix_matching = False

    def __call__(self, action_name, data):
        if action_name == "package_show":
            package = self.packages.get(data["id"])
            if package:
                return package
            for package in self.packages.values():
                if package.get("id") == data["id"]:
                    return package
            return None
        if action_name == "package_search":
            return self.package_search(data)
        if action_name == "package_create":
            return self.package_create(data)
        if action_name == "package_update":
            return self.package_update(data)
        raise AssertionError("unexpected action {}".format(action_name))

    def package_search(self, data):
        match = re.search(r'extras_identifier:"(.*)"', data["fq"])
        identifier = match.group(1).replace('\\"', '"').replace("\\\\", "\\") if match else ""
        results = [
            package
            for package in self.packages.values()
            if (
                package_identifier(package).startswith(identifier)
                if self.solr_prefix_matching
                else package_identifier(package) == identifier
            )
        ]
        return {"count": len(results), "results": results[: data.get("rows", len(results))]}

    def package_create(self, data):
        payload = copy.deepcopy(data)
        payload["id"] = "package-{}".format(self.next_id)
        self.next_id += 1
        for resource in payload.get("resources", []):
            resource["id"] = "resource-{}".format(self.next_resource_id)
            self.next_resource_id += 1
        self.packages[payload["name"]] = payload
        self.created.append(payload)
        return payload

    def package_update(self, data):
        payload = copy.deepcopy(data)
        for resource in payload.get("resources", []):
            if not resource.get("id"):
                resource["id"] = "resource-{}".format(self.next_resource_id)
                self.next_resource_id += 1
        self.packages[payload["name"]] = payload
        self.updated.append(payload)
        return payload


def test_transform_catalog_imports_service_and_metadata_only_dataset():
    result = transform_catalog({
        "dataset": [{
            "@type": "dcat:Dataset",
            "identifier": "dataset-record",
            "title": "Dataset Record",
        }],
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "service-record",
            "title": "Service Record",
            "description": "Service description",
            "accessLevel": "non-public",
            "endpointURL": ["https://example.mil/service"],
            "keyword": ["P&V", "valid-tag"],
        }],
    }, "test-org")

    assert result["summary"]["source_service_record_count"] == 1
    assert result["summary"]["accepted_service_record_count"] == 1
    assert result["summary"]["source_dataset_record_count"] == 1
    assert result["summary"]["accepted_dataset_record_count"] == 1
    assert result["summary"]["endpoint_resource_payload_count"] == 1
    assert result["summary"]["distribution_resource_payload_count"] == 0
    assert result["summary"]["datasets_without_usable_distribution_count"] == 1
    assert result["summary"]["visibility_counts"] == {"shared": 0, "private": 2}
    assert len(result["records_without_usable_url"]) == 0
    assert len(result["tag_sanitization_changes"]) == 1

    package = result["packages"][0]
    assert package["name"] == "service-record"
    assert package["owner_org"] == "test-org"
    assert package["private"] is True
    assert package_identifier(package) == "service-record"
    assert package["resources"][0]["url"] == "https://example.mil/service"


def test_sanitizes_names_and_tags():
    assert sanitize_package_name("HTTP://Example.com/Some Path/?q=1") == "http-example-com-some-path-q-1"
    assert sanitize_package_name("x") == "dcat-x"
    assert sanitize_tag("  P&V / HQ  ") == "p v hq"
    assert sanitize_tag("  ") is None


def test_transform_catalog_blocks_duplicate_generated_package_names():
    try:
        transform_catalog({
            "service": [
                {
                    "@type": "dcat:DataService",
                    "identifier": "a/b",
                    "title": "Slash Service",
                    "endpointURL": ["https://example.mil/slash"],
                },
                {
                    "@type": "dcat:DataService",
                    "identifier": "a b",
                    "title": "Space Service",
                    "endpointURL": ["https://example.mil/space"],
                },
            ]
        }, "test-org")
    except ValueError as exc:
        message = str(exc)
        assert "duplicate CKAN package name a-b" in message
        assert "a/b" in message
        assert "a b" in message
    else:
        raise AssertionError("expected duplicate generated CKAN package names to block transform")


def test_import_package_is_idempotent_by_identifier_and_resource_url():
    transformed = transform_catalog({
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "stable-service",
            "title": "Stable Service",
            "endpointURL": ["https://example.mil/stable"],
        }]
    }, "test-org")
    package = transformed["packages"][0]
    actions = FakeCkanActions()

    first = import_package(actions, package)
    second = import_package(actions, package)

    assert first["action"] == "created"
    assert second["action"] == "updated"
    assert first["package_id"] == actions.created[0]["id"]
    assert second["package_id"] == actions.created[0]["id"]
    assert first["resource_created_count"] == 1
    assert second["resource_created_count"] == 0
    assert second["resource_updated_count"] == 1
    assert len(actions.packages) == 1
    assert actions.updated[0]["resources"][0]["id"] == actions.created[0]["resources"][0]["id"]


def test_identifier_search_filters_tokenized_prefix_false_positives():
    transformed = transform_catalog({
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "cwbi-pal",
            "title": "Planning Associates Library",
            "endpointURL": ["https://example.mil/pal"],
        }]
    }, "test-org")
    package = transformed["packages"][0]
    actions = FakeCkanActions()
    actions.solr_prefix_matching = True
    actions.packages["cwbi-pal-eco"] = {
        "id": "eco-id",
        "name": "cwbi-pal-eco",
        "extras": [{"key": "identifier", "value": "cwbi-pal-eco"}],
        "resources": [],
    }
    actions.packages["cwbi-pal-iwr"] = {
        "id": "iwr-id",
        "name": "cwbi-pal-iwr",
        "extras": [{"key": "identifier", "value": "cwbi-pal-iwr"}],
        "resources": [],
    }

    result = import_package(actions, package)

    assert result["action"] == "created"
    assert result["identifier"] == "cwbi-pal"
    assert "cwbi-pal" in actions.packages


def test_duplicate_existing_identifier_blocks_import():
    transformed = transform_catalog({
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "duplicate-service",
            "title": "Duplicate Service",
            "endpointURL": ["https://example.mil/service"],
        }]
    }, "test-org")
    package = transformed["packages"][0]
    actions = FakeCkanActions()
    first = copy.deepcopy(package)
    second = copy.deepcopy(package)
    first["id"] = "package-a"
    second["id"] = "package-b"
    second["name"] = "duplicate-service-copy"
    actions.packages[first["name"]] = first
    actions.packages[second["name"]] = second

    try:
        import_package(actions, package)
    except ValueError as exc:
        assert "multiple CKAN packages" in str(exc)
    else:
        raise AssertionError("expected duplicate identifier to block import")

def test_action_runner_uses_toolkit_get_action_without_harvesterbase_helper():
    calls = []

    class FakeSession:
        pass

    class FakeModel:
        Session = FakeSession

    class FakeToolkit:
        class ObjectNotFound(Exception):
            pass

        @staticmethod
        def get_action(action_name):
            if action_name == "get_site_user":
                def get_site_user(context, data):
                    calls.append(("get_site_user", context, data))
                    assert context["model"] is FakeModel
                    assert context["session"] is FakeSession
                    assert context["ignore_auth"] is True
                    assert context["defer_commit"] is True
                    return {"name": "site-user"}
                return get_site_user

            def action(context, data):
                calls.append((action_name, context["user"], data))
                return {"ok": True}
            return action

    original_model = dcatus3_module.model
    original_toolkit = dcatus3_module.toolkit
    try:
        dcatus3_module.model = FakeModel
        dcatus3_module.toolkit = FakeToolkit
        result = DcatUs3TransformHarvesterStrategy()._action_runner("package_show", {"id": "source-id"})
    finally:
        dcatus3_module.model = original_model
        dcatus3_module.toolkit = original_toolkit

    assert result == {"ok": True}
    assert calls[0][0] == "get_site_user"
    assert calls[1] == ("package_show", "site-user", {"id": "source-id"})

def test_import_stage_marks_harvest_object_current_with_package_id():
    calls = []

    class FakeHarvestObject:
        def __init__(self):
            self.id = "object-id"
            self.guid = "stable-service"
            self.content = '{"package": {"name": "stable-service"}}'
            self.current = False
            self.package_id = None
            self.add_count = 0

        def add(self):
            self.add_count += 1

    def fake_import_package(action_runner, package):
        calls.append(package)
        return {
            "action": "updated",
            "identifier": "stable-service",
            "package_id": "package-1",
            "resource_created_count": 0,
            "resource_updated_count": 1,
        }

    harvest_object = FakeHarvestObject()
    original_import_package = dcatus3_module.import_package
    original_model = dcatus3_module.model
    try:
        dcatus3_module.import_package = fake_import_package
        dcatus3_module.model = None
        result = DcatUs3TransformHarvesterStrategy().import_stage(harvest_object)
    finally:
        dcatus3_module.import_package = original_import_package
        dcatus3_module.model = original_model

    assert result is True
    assert calls == [{"name": "stable-service"}]
    assert harvest_object.current is True
    assert harvest_object.package_id == "package-1"
    assert harvest_object.add_count == 1


def test_transform_catalog_imports_dataset_distribution_as_resource():
    result = transform_catalog({
        "dataset": [{
            "@type": "dcat:Dataset",
            "identifier": "dataset-record",
            "title": "Dataset Record",
            "description": "Dataset description",
            "distribution": [{
                "title": "Download",
                "format": "CSV",
                "accessURL": "https://example.mil/dataset.csv",
            }],
        }],
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "service-record",
            "title": "Service Record",
            "endpointURL": ["https://example.mil/service"],
        }],
    }, "test-org")

    assert result["summary"]["source_service_record_count"] == 1
    assert result["summary"]["source_dataset_record_count"] == 1
    assert result["summary"]["accepted_service_record_count"] == 1
    assert result["summary"]["accepted_dataset_record_count"] == 1
    assert result["summary"]["package_payload_count"] == 2
    assert result["summary"]["endpoint_resource_payload_count"] == 1
    assert result["summary"]["distribution_resource_payload_count"] == 1
    assert len(result["datasets_without_usable_distribution"]) == 0

    dataset_package = next(
        package for package in result["packages"]
        if package_identifier(package) == "dataset-record"
    )
    assert dataset_package["resources"] == [{
        "name": "Download",
        "url": "https://example.mil/dataset.csv",
        "format": "CSV",
        "description": "Dataset description",
    }]


def test_transform_catalog_keeps_dataset_without_distribution_as_package():
    result = transform_catalog({
        "dataset": [{
            "@type": "dcat:Dataset",
            "identifier": "metadata-only-dataset",
            "title": "Metadata-only Dataset",
        }],
    }, "test-org")

    assert result["summary"]["accepted_dataset_record_count"] == 1
    assert result["summary"]["package_payload_count"] == 1
    assert result["summary"]["distribution_resource_payload_count"] == 0
    assert result["summary"]["datasets_without_usable_distribution_count"] == 1
    assert result["packages"][0]["resources"] == []
    assert result["datasets_without_usable_distribution"] == [{
        "identifier": "metadata-only-dataset",
        "title": "Metadata-only Dataset",
        "dcatType": "dcat:Dataset",
    }]


def test_access_rights_controls_visibility_and_is_preserved():
    cases = [
        (None, "Public", False),
        (None, "USACE Internal, authentication required", True),
        (None, "CAC Authentication, Keycloak Roles", True),
        (None, None, True),
        (None, "Unrecognized access policy", True),
        ("public", "Internal", True),
        ("public", "Public", False),
        ("non-public", "Public", True),
    ]

    for index, (access_level, access_rights, expected_private) in enumerate(cases):
        record = {
            "@type": "dcat:DataService",
            "identifier": "visibility-{}".format(index),
            "title": "Visibility {}".format(index),
        }
        if access_level is not None:
            record["accessLevel"] = access_level
        if access_rights is not None:
            record["accessRights"] = access_rights

        package = transform_catalog({"service": [record]}, "test-org")["packages"][0]
        extras = {extra["key"]: extra["value"] for extra in package["extras"]}

        assert package["private"] is expected_private
        if access_rights is None:
            assert "accessRights" not in extras
        else:
            assert extras["accessRights"] == access_rights

def test_transform_catalog_preserves_array_contact_points():
    contact_points = [
        "not-a-contact",
        {
            "@type": "vcard:Kind",
            "fn": "Primary Contact",
            "hasEmail": "mailto:primary@example.mil",
        },
        {
            "@type": "vcard:Kind",
            "fn": "Secondary Contact",
            "hasEmail": "mailto:secondary@example.mil",
        },
    ]
    package = transform_catalog({
        "service": [{
            "@type": "dcat:DataService",
            "identifier": "array-contact-point",
            "title": "Array Contact Point",
            "contactPoint": contact_points,
        }],
    }, "test-org")["packages"][0]
    extras = {extra["key"]: extra["value"] for extra in package["extras"]}

    assert json.loads(extras["contactPoint"]) == contact_points
    assert package["maintainer"] == "Primary Contact"
    assert package["maintainer_email"] == "primary@example.mil"
