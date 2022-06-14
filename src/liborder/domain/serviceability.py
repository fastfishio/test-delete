import logging
import os

import fastkml
from jsql import sql
from noonutil.v1 import miscutil, storageutil
from shapely.geometry import Point

from liborder import ctx, engine
from liborder.domain import helpers
from libutil import util

logger = logging.getLogger(__name__)


class ServiceabilityResponse(util.NoonBaseModel):
    serviceable: bool


def get_servicability(lat, lng, country_code):
    if not (lat and lng):
        return ServiceabilityResponse(serviceable=False)

    assert miscutil.safe_int(lat) and miscutil.safe_int(lng), "Lat and Lng must be integers"

    serviceable_geo_str_tree = get_serviceable_geo_str_tree(country_code)
    ulng = util.latlng_from_int(lng)
    ulat = util.latlng_from_int(lat)
    pt = Point(ulng, ulat)

    valid_places = serviceable_geo_str_tree.query(pt)
    if not valid_places:
        return ServiceabilityResponse(serviceable=False)
    verified_places = [place for place in valid_places if place.contains(pt)]  # Verify its not a false positive
    if not verified_places:
        return ServiceabilityResponse(serviceable=False)

    warehouses = helpers.get_warehouses_for_country(country_code)
    if not warehouses:
        logger.warning(f"serviceable country in KML does not have any warehouse mapped")
        return ServiceabilityResponse(serviceable=False)
    return ServiceabilityResponse(serviceable=True)


def load_kml_from_gcs(file_name, bucket):
    k = fastkml.KML()
    file_content = storageutil.read_from_gcloud(file_name, bucket).decode('utf-8')
    k.from_string(file_content)
    places = list(list(k.features())[0].features())
    return places


@miscutil.cached(ttl=60 * 60 * 12)
def get_serviceable_geo_str_tree(country):
    """
    Fetch a list of polygons that are serviceable
    from a KML file that is pushed from logistics
    """
    from shapely.strtree import STRtree

    file_name = f"country_zone_kml/{country.lower()}_serviceable.kml"
    bucket = os.getenv(f'KML_SERVICABLITY_BUCKET_BOILERPLATE')
    places = load_kml_from_gcs(file_name, bucket)

    try:
        polygons = list()
        for place in places:
            place_shape = place.geometry
            polygons.append(place_shape)
        return STRtree(polygons)
    except Exception as ex:
        logger.exception(f'Error loading serviceable geo for {country}. places: {places} - {ex}')


class GetServiceability(util.NoonBaseModel):
    @staticmethod
    def execute():
        assert ctx.lat and ctx.lng, "Location lat/long must be set"
        return get_servicability(ctx.lat, ctx.lng, ctx.country_code)


@miscutil.cached(ttl=60 * 60)
def get_wh_code_to_country_code_map():
    # not using ctx.conn here since it is called in before_request of catalog APIs which doesn't have ctx
    return sql(
        engine,
        '''
                    SELECT wh_code, country_code
                    FROM warehouse
                    WHERE is_active = 1
                ''',
    ).kv_map()
