from types import SimpleNamespace
from unittest.mock import patch

from ckanext.cwbi_harvesters.harvesters.arcgis import ArcGISHarvesterStrategy


def test_make_package_dict_includes_harvest_linkage_extras():
    harvester = ArcGISHarvesterStrategy()
    harvest_source = SimpleNamespace(
        id="source-id",
        title="Source Title",
        name="source-name",
        url="https://example.com/arcgis",
    )
    harvest_object = SimpleNamespace(
        id="object-id",
        guid="guid-123",
        package_id="package-id",
        source=harvest_source,
    )
    content = {
        "id": "record-id",
        "title": "Sample dataset",
        "description": "Sample description",
        "url": "https://example.com/resource",
        "type": "Web Map",
        "tags": ["transport"],
    }

    with patch("ckanext.cwbi_harvesters.harvesters.arcgis.model.Package.get", return_value=None):
        package_dict = harvester.make_package_dict(harvest_object, content)

    extras = {extra["key"]: extra["value"] for extra in package_dict["extras"]}

    assert extras["harvest_source_id"] == "source-id"
    assert extras["harvest_object_id"] == "object-id"
    assert extras["harvest_source_title"] == "Source Title"
    assert extras["harvest_source_name"] == "source-name"
