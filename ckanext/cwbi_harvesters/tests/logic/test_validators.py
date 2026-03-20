"""Tests for validators.py."""

import pytest

import ckan.plugins.toolkit as tk

from ckanext.cwbi_harvesters.logic import validators


def test_cwbi_harvesters_reauired_with_valid_value():
    assert validators.cwbi_harvesters_required("value") == "value"


def test_cwbi_harvesters_reauired_with_invalid_value():
    with pytest.raises(tk.Invalid):
        validators.cwbi_harvesters_required(None)
