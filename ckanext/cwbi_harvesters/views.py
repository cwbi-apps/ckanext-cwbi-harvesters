from flask import Blueprint


cwbi_harvesters = Blueprint(
    "cwbi_harvesters", __name__)


def page():
    return "Hello, cwbi_harvesters!"


cwbi_harvesters.add_url_rule(
    "/cwbi_harvesters/page", view_func=page)


def get_blueprints():
    return [cwbi_harvesters]
