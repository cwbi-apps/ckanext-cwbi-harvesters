import ckan.plugins.toolkit as tk


@tk.auth_allow_anonymous_access
def cwbi_harvesters_get_sum(context, data_dict):
    return {"success": True}


def get_auth_functions():
    return {
        "cwbi_harvesters_get_sum": cwbi_harvesters_get_sum,
    }
