import ckan.plugins.toolkit as tk


def cwbi_harvesters_required(value):
    if not value or value is tk.missing:
        raise tk.Invalid(tk._("Required"))
    return value


def get_validators():
    return {
        "cwbi_harvesters_required": cwbi_harvesters_required,
    }
