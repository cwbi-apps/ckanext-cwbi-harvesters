# this is a namespace package
try:
    import pkg_resources
    pkg_resources.declare_namespace(__name__)
except ImportError:
    import pkgutil
    __path__ = pkgutil.extend_path(__path__, __name__)

from ckanext.cwbi_harvesters.harvesters.base import CWBIHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.base import CWBICSWHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.base import CWBIWAFHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.base import CWBIDocHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.base import CWBIGeoportalHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.waf_collection import WAFCollectionHarvester  # NOQA F401
from ckanext.cwbi_harvesters.harvesters.arcgis import ArcGISHarvester  # NOQA F401
