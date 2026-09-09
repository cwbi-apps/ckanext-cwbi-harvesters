from types import SimpleNamespace

from ckanext.cwbi_harvesters.harvesters.extensible import CwbiHarvesters
from ckanext.cwbi_harvesters.harvesters.extensible import CwbiEsriHarvester
from ckanext.cwbi_harvesters.harvesters.extensible import CwbiEsriRestHarvester
from ckanext.cwbi_harvesters.harvesters.extensible import DcatUs3TransformHarvester
import ckanext.cwbi_harvesters.harvesters.registry as registry_module
from ckanext.cwbi_harvesters.harvesters.registry import available_harvesters
from ckanext.cwbi_harvesters.harvesters.registry import describe_harvesters
from ckanext.cwbi_harvesters.harvesters.registry import get_harvester_alias
from ckanext.cwbi_harvesters.harvesters.registry import resolve_harvester_class


def test_available_harvesters_contains_local_aliases():
    harvesters = available_harvesters()

    assert harvesters["cwbi_esri"]
    assert harvesters["cwbi_esri_rest"]
    assert harvesters["dcat_us_3_transform"]


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


def test_cwbi_esri_rest_harvester_info_reports_rest_services_type():
    info = CwbiEsriRestHarvester().info()

    assert info["name"] == "cwbi_esri_rest"
    assert info["title"] == "ArcGIS REST Services"
    assert info["form_config_interface"] == "Text"


def test_cwbi_esri_rest_registers_ckan_visible_report_actions():
    actions = CwbiEsriRestHarvester().get_actions()

    assert set(actions) == {"harvest_job_show", "harvest_source_show_status"}


def test_cwbi_esri_rest_job_report_action_adds_complete_report():
    plugin = CwbiEsriRestHarvester()
    job = SimpleNamespace(source=SimpleNamespace(type="cwbi_esri_rest"))
    native_action = lambda context, data: {
        "id": data["id"],
        "stats": {"added": 1, "updated": 2, "not modified": 3, "errored": 4},
    }
    plugin._job_for_report = lambda job_id: job

    result = plugin.harvest_job_show(native_action, {}, {"id": "job-id"})

    assert result["arcgis_rest_report"] == {
        "discovered": 10,
        "created": 1,
        "updated": 2,
        "skipped": 3,
        "failed": 4,
    }


def test_cwbi_esri_rest_source_status_action_decorates_last_job():
    plugin = CwbiEsriRestHarvester()
    source = SimpleNamespace(type="cwbi_esri_rest")
    job = SimpleNamespace(source=source)
    native_action = lambda context, data: {
        "last_job": {
            "id": "job-id",
            "stats": {"added": 2, "updated": 1, "not modified": 0, "errored": 0},
        }
    }
    plugin._source_for_report = lambda source_id: source
    plugin._job_for_report = lambda job_id: job

    result = plugin.harvest_source_show_status(native_action, {}, {"id": "source-id"})

    assert result["last_job"]["arcgis_rest_report"] == {
        "discovered": 3,
        "created": 2,
        "updated": 1,
        "skipped": 0,
        "failed": 0,
    }


def test_cwbi_esri_rest_report_action_leaves_other_harvests_unchanged():
    plugin = CwbiEsriRestHarvester()
    job = SimpleNamespace(source=SimpleNamespace(type="other_harvester"))
    result = {"stats": {"added": 1}}

    assert plugin._decorate_report(result, job) == result


def test_dcat_us_3_transform_harvester_info_reports_source_type():
    info = DcatUs3TransformHarvester().info()

    assert info["name"] == "dcat_us_3_transform"
    assert info["title"] == "DCAT-US 3 Transform"
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
