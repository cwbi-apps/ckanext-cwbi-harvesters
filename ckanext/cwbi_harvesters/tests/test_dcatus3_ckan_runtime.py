import pytest


pytest.importorskip("ckan")
pytest.importorskip("ckanext.harvest")

from ckan import model
from ckan.plugins import toolkit
from ckanext.harvest.model import HarvestGatherError
from ckanext.harvest.model import HarvestJob
from ckanext.harvest.model import HarvestSource

import ckanext.cwbi_harvesters.harvesters.dcatus3 as dcatus3_module
from ckanext.cwbi_harvesters.harvesters.dcatus3 import DcatUs3TransformHarvesterStrategy


@pytest.mark.ckan_config(
    "ckan.plugins",
    "harvest cwbi_harvesters dcat_us_3_transform",
)
@pytest.mark.usefixtures("with_plugins", "clean_db", "clean_index")
def test_failed_gather_is_finished_and_reported_in_ckan_runtime(monkeypatch):
    context = {
        "model": model,
        "session": model.Session,
        "user": "tester",
        "ignore_auth": True,
    }
    source_dict = toolkit.get_action("harvest_source_create")(
        context,
        {
            "name": "dcat-runtime-failure-source",
            "title": "DCAT runtime failure source",
            "url": "https://example.mil/catalog",
            "source_type": "dcat_us_3_transform",
            "frequency": "MANUAL",
            "config": "{}",
        },
    )
    source = HarvestSource.get(source_dict["id"])
    job = HarvestJob(source=source, status="Running")
    job.save()

    strategy = DcatUs3TransformHarvesterStrategy()
    strategy._owner_org_for_source = lambda source: "test-org"
    ssl_error = dcatus3_module.requests.exceptions.SSLError(
        "certificate verify failed: self-signed certificate in certificate chain"
    )
    monkeypatch.setattr(
        dcatus3_module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(ssl_error),
    )

    assert strategy.gather_stage(job) == []
    model.Session.commit()

    persisted_job = HarvestJob.get(job.id)
    gather_errors = (
        model.Session.query(HarvestGatherError)
        .filter(HarvestGatherError.harvest_job_id == job.id)
        .all()
    )
    report = toolkit.get_action("harvest_job_report")(
        context,
        {"id": job.id},
    )
    source_status = toolkit.get_action("harvest_source_show_status")(
        context,
        {"id": source.id},
    )

    assert persisted_job.status == "Finished"
    assert persisted_job.gather_finished is not None
    assert persisted_job.finished is not None
    assert len(gather_errors) == 1
    assert "https://example.mil/catalog" in gather_errors[0].message
    assert "TLS certificate verification failed" in gather_errors[0].message
    assert any(
        error["message"] == gather_errors[0].message
        for error in report["gather_errors"]
    )
    assert source_status["last_job"]["id"] == job.id
    assert source_status["last_job"]["status"] == "Finished"
