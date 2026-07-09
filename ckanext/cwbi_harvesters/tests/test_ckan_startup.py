import pytest

import ckan.plugins as plugins
from ckan.config.declaration import Declaration
from ckan.config.declaration import Key


@pytest.mark.ckan_config(
    "ckan.plugins",
    "harvest cwbi_harvesters cwbi_esri dcat_us_3_transform",
)
@pytest.mark.usefixtures("with_plugins")
def test_ckan_config_declarations_do_not_redeclare_existing_options():
    assert plugins.plugin_loaded("cwbi_harvesters")
    assert plugins.plugin_loaded("cwbi_esri")
    assert plugins.plugin_loaded("dcat_us_3_transform")

    declaration_plugins = list(
        plugins.PluginImplementations(plugins.IConfigDeclaration)
    )

    declaration = Declaration()
    declaration.load_core_declaration()
    if "lang" not in declaration:
        declaration.declare("lang", "")

    for plugin in declaration_plugins:
        plugin.declare_config_options(declaration, Key())