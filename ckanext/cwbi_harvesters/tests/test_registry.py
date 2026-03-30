from ckanext.cwbi_harvesters.harvesters.extensible import CwbiHarvesters
from ckanext.cwbi_harvesters.harvesters.extensible import CwbiEsriHarvester
import ckanext.cwbi_harvesters.harvesters.registry as registry_module
from ckanext.cwbi_harvesters.harvesters.registry import available_harvesters
from ckanext.cwbi_harvesters.harvesters.registry import describe_harvesters
from ckanext.cwbi_harvesters.harvesters.registry import get_harvester_alias
from ckanext.cwbi_harvesters.harvesters.registry import resolve_harvester_class


def test_available_harvesters_contains_cwbi_esri():
    assert available_harvesters()["cwbi_esri"]


def test_get_harvester_alias_defaults_to_cwbi_esri():
    assert get_harvester_alias(None) == "cwbi_esri"


def test_get_harvester_alias_reads_harvester_key():
    assert get_harvester_alias('{"harvester": "cwbi_esri"}') == "cwbi_esri"


def test_cwbi_harvesters_info_reports_plugin_name():
    info = CwbiHarvesters().info()

    assert info["name"] == "cwbi_harvesters"
    assert info["title"] == "CWBI Harvesters"
    assert info["form_config_interface"] == "Text"


def test_cwbi_esri_harvester_info_reports_esri_type():
    info = CwbiEsriHarvester().info()

    assert info["title"] in {"ESRI Harvester", "CWBI Harvesters"}
    assert "description" in info
    assert info["form_config_interface"] == "Text"


def test_resolve_harvester_class_accepts_import_path():
    resolved_class = resolve_harvester_class(
        "ckanext.cwbi_harvesters.harvesters.example:ExampleHarvesterStrategy"
    )
    assert resolved_class.__name__ == "ExampleHarvesterStrategy"


def test_describe_harvesters_reports_mapped_strategy(monkeypatch):
    monkeypatch.setattr(
        registry_module,
        "LOCAL_HARVESTERS",
        {
            "cwbi_rest": "ckanext.cwbi_harvesters.harvesters.example:ExampleHarvesterStrategy",
        },
    )

    descriptions = describe_harvesters()
    by_alias = {item["alias"]: item for item in descriptions}

    assert "cwbi_rest" in by_alias
    assert by_alias["cwbi_rest"]["class_name"] == "ExampleHarvesterStrategy"
