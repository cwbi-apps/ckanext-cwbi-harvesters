import pytest


ckan = pytest.importorskip("ckan")

from ckan import model
from ckan import plugins
from ckan.tests import helpers
from ckan.tests import factories
from ckanext.harvest.model import HarvestGatherError
from ckanext.harvest.model import HarvestJob
from ckanext.harvest.model import HarvestObject
from ckanext.harvest.model import HarvestObjectError
from ckanext.harvest.model import HarvestSource


@pytest.mark.ckan_config(
    "ckan.plugins", "harvest cwbi_harvesters cwbi_esri_rest"
)
@pytest.mark.usefixtures("clean_db", "with_plugins")
def test_arcgis_rest_report_is_exposed_by_ckan_harvest_actions():
    source = HarvestSource(
        url="https://example.com/arcgis/rest/services/",
        type="cwbi_esri_rest",
        config="{}",
    )
    job = HarvestJob(source=source, status="Finished")
    HarvestObject(guid="created", job=job, report_status="added")
    HarvestObject(guid="updated", job=job, report_status="updated")
    HarvestObject(guid="unchanged", job=job, report_status="not modified")
    failed_object = HarvestObject(guid="failed", job=job, report_status="errored")
    HarvestGatherError(message="malformed entry", job=job)
    HarvestGatherError(message="duplicate endpoint", job=job)
    HarvestObjectError(message="service JSON failed", object=failed_object, stage="Fetch")

    model.Session.add(source)
    model.Session.add(job)
    model.Session.commit()

    context = {"ignore_auth": True}
    job_report = helpers.call_action(
        "harvest_job_show", context, id=job.id
    )
    source_report = helpers.call_action(
        "harvest_source_show_status", context, id=source.id
    )

    expected = {
        "discovered": 6,
        "created": 1,
        "updated": 1,
        "skipped": 1,
        "failed": 3,
    }
    assert job_report["arcgis_rest_report"] == expected
    assert source_report["last_job"]["arcgis_rest_report"] == expected
    assert job_report["stats"]["added"] == 1
    assert job_report["stats"]["updated"] == 1
    assert job_report["stats"]["not modified"] == 1
    assert job_report["stats"]["errored"] == 3


@pytest.mark.ckan_config(
    "ckan.plugins", "harvest cwbi_harvesters cwbi_esri_rest"
)
@pytest.mark.usefixtures("clean_db", "with_plugins")
def test_arcgis_report_actions_are_chained_and_side_effect_free():
    plugin = plugins.get_plugin("cwbi_esri_rest")
    actions = plugin.get_actions()

    assert getattr(actions["harvest_job_show"], "chained_action", False)
    assert getattr(actions["harvest_job_show"], "side_effect_free", False)
    assert getattr(
        actions["harvest_source_show_status"], "chained_action", False
    )
    assert getattr(
        actions["harvest_source_show_status"], "side_effect_free", False
    )


@pytest.mark.ckan_config(
    "ckan.plugins", "harvest cwbi_harvesters cwbi_esri_rest"
)
@pytest.mark.usefixtures("clean_db", "with_plugins")
def test_non_arcgis_job_uses_native_report_without_arcgis_projection():
    source = HarvestSource(
        url="https://example.com/feed",
        type="other_harvester",
        config="{}",
    )
    job = HarvestJob(source=source, status="Finished")
    HarvestObject(guid="other", job=job, report_status="added")
    model.Session.add(source)
    model.Session.add(job)
    model.Session.commit()

    report = helpers.call_action(
        "harvest_job_show", {"ignore_auth": True}, id=job.id
    )

    assert "arcgis_rest_report" not in report


@pytest.mark.ckan_config(
    "ckan.plugins", "harvest cwbi_harvesters cwbi_esri_rest"
)
@pytest.mark.usefixtures("clean_db", "with_plugins")
def test_arcgis_report_actions_are_available_over_get(app):
    sysadmin = factories.Sysadmin()
    context = {"ignore_auth": True, "user": sysadmin["name"]}
    source_package = helpers.call_action(
        "package_create",
        context,
        name="arcgis-report-source",
        title="ArcGIS report source",
        type="harvest",
    )
    source = HarvestSource(
        id=source_package["id"],
        url="https://example.com/arcgis/rest/services/",
        type="cwbi_esri_rest",
        config="{}",
    )
    job = HarvestJob(source=source, status="Finished")
    HarvestObject(guid="created", job=job, report_status="added")
    model.Session.add(source)
    model.Session.add(job)
    model.Session.commit()

    environ = {"REMOTE_USER": sysadmin["name"]}
    job_response = app.get(
        "/api/3/action/harvest_job_show?id={0}".format(job.id),
        extra_environ=environ,
    )
    source_response = app.get(
        "/api/3/action/harvest_source_show_status?id={0}".format(source.id),
        extra_environ=environ,
    )

    assert job_response.status_code == 200
    assert source_response.status_code == 200
    assert job_response.json["result"]["arcgis_rest_report"]["created"] == 1
    assert (
        source_response.json["result"]["last_job"]["arcgis_rest_report"]["created"]
        == 1
    )
