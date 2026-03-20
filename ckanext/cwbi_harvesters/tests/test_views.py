"""Tests for views.py."""

import pytest

import ckanext.cwbi_harvesters.validators as validators


import ckan.plugins.toolkit as tk


@pytest.mark.ckan_config("ckan.plugins", "cwbi_harvesters")
@pytest.mark.usefixtures("with_plugins")
def test_cwbi_harvesters_blueprint(app, reset_db):
    resp = app.get(tk.h.url_for("cwbi_harvesters.page"))
    assert resp.status_code == 200
    assert resp.body == "Hello, cwbi_harvesters!"
