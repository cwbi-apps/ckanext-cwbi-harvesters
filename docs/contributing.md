As part of the CKAN ecosystem, ckanext-cwbi-harvesters is entirely open source and welcomes all forms of contributions from the community.
Besides the general guidance provided in the [CKAN documentation](https://docs.ckan.org/en/latest/contributing/index.html) follow these points:

* Format your code with [Black](https://github.com/psf/black).
* Make sure to include tests for your changes.
* It's better to submit a pull request early, even if in draft state, to get feedback and make sure the contribution will be accepted.

## Adding a harvester strategy

This fork is strategy-first. Contributions should generally extend harvesting behavior instead of reintroducing the removed DCAT runtime.

A contribution that adds a new harvester should include:

* A new strategy class under `ckanext/cwbi_harvesters/harvesters/`
* An alias registration in `ckanext/cwbi_harvesters/harvesters/registry.py`
* Tests covering alias selection or strategy behavior
* Documentation updates in `README.md` and `docs/harvester.md`

Keep the public surface small. If new functionality does not participate in the harvest lifecycle, it probably belongs in a separate extension.

