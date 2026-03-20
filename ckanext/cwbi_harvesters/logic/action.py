import ckan.plugins.toolkit as tk
import ckanext.cwbi_harvesters.logic.schema as schema


@tk.side_effect_free
def cwbi_harvesters_get_sum(context, data_dict):
    tk.check_access(
        "cwbi_harvesters_get_sum", context, data_dict)
    data, errors = tk.navl_validate(
        data_dict, schema.cwbi_harvesters_get_sum(), context)

    if errors:
        raise tk.ValidationError(errors)

    return {
        "left": data["left"],
        "right": data["right"],
        "sum": data["left"] + data["right"]
    }


def get_actions():
    return {
        'cwbi_harvesters_get_sum': cwbi_harvesters_get_sum,
    }
