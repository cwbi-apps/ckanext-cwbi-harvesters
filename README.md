# ckanext-cwbi-harvesters


[![Tests](https://github.com/cwbi/ckanext-cwbi-harvesters/actions/workflows/test.yml/badge.svg)](https://github.com/cwbi/ckanext-cwbi-harvesters/actions)


Ckanext-cwbi-harvesters is a [CKAN](https://github.com/ckan/ckan) extension focused on reusable harvesting workflows.

This fork is focused on harvesting only.

This extension is currently supported in CKAN 2.10 and CKAN 2.11.

> [!IMPORTANT]
> Read the repository documentation for setup details:
> https://github.com/cwbi/ckanext-cwbi-harvesters


## Overview

In terms of CKAN features, this fork offers:

* A single base harvester plugin (`cwbi_harvesters`) that delegates to local harvester strategy classes in this package.
* A built-in ArcGIS REST implementation (`cwbi_esri`) based on the ArcGIS harvesting logic.


These are implemented internally using:

* A base delegation model that routes the harvest lifecycle to local strategy classes.
* An ArcGIS strategy that gathers, diffs and imports datasets from ArcGIS REST endpoints.

## Base Harvester

Use `cwbi_harvesters` as the CKAN harvester plugin, then select an implementation in the harvest source config:

```json
{
    "harvester": "cwbi_esri"
}
```

Supported built-in values:

* `cwbi_esri`

To add a new harvester in this package:

1. Add a new strategy class in `ckanext/cwbi_harvesters/harvesters/`.
2. Register the alias in `LOCAL_HARVESTERS` in `ckanext/cwbi_harvesters/harvesters/registry.py` (for example `"cwbi_rest": "ckanext.cwbi_harvesters.harvesters.rest:RestHarvesterStrategy"`).
3. Use that alias in the harvest source config.

Example source config:

```json
{
    "harvester": "cwbi_rest"
}
```




## Running the Tests

To run tests locally:

    pytest --ckan-ini=test.ini ckanext/cwbi_harvesters/tests

Docker-based test run:

    docker compose -f docker/docker-compose.test.yml build ckan-test
    docker compose -f docker/docker-compose.test.yml run --rm ckan-test

Normal CKAN UI run:

    docker compose -f docker/docker-compose.test.yml up --build ckan-app

Then open the normal CKAN app and log in with:

    username: ckan_admin
    password: test1234

The `ckan-app` service now uses CKAN's standard startup script (`/srv/app/start_ckan.sh`), which runs `prerun.py` and creates the sysadmin from environment variables on startup.

If the configured sysadmin already exists, CKAN startup does not overwrite that account.

Useful URLs:

    http://localhost:5000/user/login
    http://localhost:5000/harvest
    http://localhost:5000/harvest/new

On the harvest source form, check that the harvester type includes the `cwbi_harvesters` plugin and use a source config like:

    {"harvester": "cwbi_esri", "private_datasets": true}

Run a subset by overriding `TEST_PATH`:

    TEST_PATH=ckanext/cwbi_harvesters/tests docker compose -f docker/docker-compose.test.yml run --rm ckan-test

The packaged runtime depends on [ckanext-harvest](https://github.com/ckan/ckanext-harvest). The Docker test image installs the required CKAN-side dependencies automatically.

## Releases

To create a new release, follow these steps:

* Determine new release number based on the rules of [semantic versioning](http://semver.org)
* Update the version number in `pyproject.toml`
* Create a new release on GitHub with release notes describing the changes in that release

## Acknowledgements

Work on cwbi-harvesters has been made possible in part by:

* the Government of Sweden and Vinnova, as part of work on [Öppnadata.se](http://oppnadata.se), the Swedish Open Data Portal.
* [FIWARE](https://www.fiware.org), a project funded by the European Commission to integrate different technologies to offer connected cloud services from a single platform.

If you can fund new developments or contribute please get in touch.


## Copying and License

This material is copyright (c) Open Knowledge.

It is open and licensed under the GNU Affero General Public License (AGPL) v3.0 whose full text may be found at:

http://www.fsf.org/licensing/licenses/agpl-3.0.html
