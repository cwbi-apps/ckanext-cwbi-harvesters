"""Tests for helpers.py."""

import ckanext.cwbi_harvesters.helpers as helpers


def test_cwbi_harvesters_hello():
    assert helpers.cwbi_harvesters_hello() == "Hello, cwbi_harvesters!"
