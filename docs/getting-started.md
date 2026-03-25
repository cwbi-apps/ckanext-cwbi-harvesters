# Getting started

## Installation

1. Install the extension in your virtualenv:

        pip install ckanext-cwbi-harvesters

2. Enable the required CKAN plugins:

        ckan.plugins = harvest cwbi_harvesters

3. Install `ckanext-harvest` if it is not already available in your CKAN environment:

        pip install -e "git+https://github.com/ckan/ckanext-harvest.git#egg=ckanext-harvest"

4. Create or update a harvest source and select the local strategy in the source config:

        {"harvester": "cwbi_esri"}

## Running tests

Run the packaged tests locally:

    pytest --ckan-ini=test.ini ckanext/cwbi_harvesters/tests

Run the same suite with Docker:

        docker compose -f docker/docker-compose.test.yml build ckan-test
        docker compose -f docker/docker-compose.test.yml run --rm ckan-test

## Shipped runtime

This fork intentionally ships a small runtime surface:

* the `cwbi_harvesters` CKAN plugin entry point
* local harvester strategies under `ckanext.cwbi_harvesters.harvesters`
* Docker-based CKAN integration tests

The old DCAT runtime is not part of this package anymore.

