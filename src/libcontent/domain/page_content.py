import datetime
import json
import logging
import os
from datetime import timedelta
from typing import List

from jinja2 import Environment

from libcontent import engine as engine_content
from libcontent.models.objects import WidgetAsset
from libutil import util
from libutil.async_utils import cached, asql

jenv = Environment()

widget_parameters = {
    'bannerModuleStrip': ['type', 'widgetCode', 'numPerRow', 'moduleHeader', 'banners'],
    'bannerSlider': ['type', 'widgetCode', 'numPerRow', 'moduleHeader', 'banners'],
    'bannerModule': ['type', 'widgetCode', 'numPerRow', 'moduleHeader', 'banners'],
    'productCarousel': ['type', 'widgetCode', 'productUrl', 'moduleHeader'],
    'bannerModuleCarousel': ['type', 'widgetCode', 'numPerRow', 'productUrl', 'moduleHeader', 'banners'],
    'productList': ['type', 'widgetCode', 'productUrl', 'moduleHeader', 'showAllURL', 'initialNum'],
}

CMS_CDN_HOST = os.getenv('CMS_CDN_HOST')
logger = logging.getLogger(__name__)


class PageContent(util.NoonBaseModel):
    page_code: str
    country_code: str
    platform: str
    content_type: str
    lang: str
    user_group: str

    @staticmethod
    @cached(ttl=60 * 5)
    async def get_widget_assets(page_code, country_code, platform, content_type, lang) -> List[WidgetAsset]:
        rows = (
            await asql(
                engine_content,
                f'''
                SELECT
                    w.code as widget_code,
                    w.type as widget_type,
                    COALESCE(w.title_{lang}, w.title_en) as widget_title,
                    w.num_per_row,
                    w.position as widget_position,
                    title_color,
                    product_url,
                    build_ge,
                    w.misc as widget_misc,
                    a.code as asset_code,
                    a.position as asset_position,
                    link as link,
                    criteria,
                    COALESCE(a.image_{lang}, a.image_en) as image,
                    start_date,
                    end_date
                FROM page p
                LEFT JOIN widget w ON (p.code = w.page_code)
                LEFT JOIN asset a ON (w.code = a.widget_code)
                WHERE
                    p.code = :page_code
                    AND (
                        (p.country_code = :country_code
                        AND p.platform = :platform
                        AND p.content_type = :content_type
                        AND w.is_active = 1
                        AND a.is_active = 1)
                            OR
                        (a.code is NULL)
                        )
            ''',
                page_code=page_code,
                country_code=country_code,
                platform=platform,
                content_type=content_type,
            )
        ).dicts()

        assets = []
        for row in rows:
            asset = WidgetAsset(**row)
            if asset.criteria:
                try:
                    asset.criteria = jenv.compile_expression(asset.criteria)
                except Exception as ex:
                    logger.warning(
                        f"an error happened when trying to compile expression ({asset.criteria}) the error: {ex}"
                    )
                    asset.criteria = jenv.compile_expression("1 == 2")
            assets.append(asset)
        return assets

    async def get_widgets(self):
        assets = await self.get_widget_assets(
            self.page_code, self.country_code, self.platform, self.content_type, self.lang
        )
        widgets = {}
        for asset in assets:
            if asset.start_date and datetime.datetime.now() < asset.start_date:
                continue
            if asset.end_date and asset.end_date < datetime.datetime.now():
                continue
            if asset.widget_type not in widget_parameters:  # invalid type
                continue
            if asset.criteria:
                try:
                    if not asset['criteria'](
                        user_group=self.user_group,
                        time=lambda time_str: datetime.datetime.strptime(time_str, "%H:%M").time(),
                        time_now=(datetime.datetime.now() + timedelta(hours=4)).time(),
                    ):  # evaluate expression criteria here
                        continue
                except:
                    continue

            if asset.widget_code not in widgets:
                widgets[asset.widget_code] = {
                    'type': asset.widget_type,
                    'moduleHeader': {'titleText': asset.widget_title, 'titleColor': asset.title_color},
                    'widgetCode': asset.widget_code,
                    'numPerRow': asset.num_per_row,
                    'position': asset.widget_position,
                    'productUrl': (asset.product_url + "&productsOnly=1" if asset.product_url is not None else None),
                    'banners': [],
                }
                if asset.widget_type in ('productCarousel', 'bannerModuleCarousel'):
                    widgets[asset.widget_code]['moduleHeader']['linkUrl'] = asset.product_url
                if asset.widget_type in ('productList'):
                    widgets[asset.widget_code]['initialNum'] = 20
                    widgets[asset.widget_code]['showAllURL'] = asset.product_url
                if asset.widget_type in ('productCarousel'):
                    if self.lang.lower() == 'en':
                        widgets[asset.widget_code]['moduleHeader']['linkText'] = "VIEW ALL"
                    else:
                        widgets[asset.widget_code]['moduleHeader']['linkText'] = "عرض الكل"
                widgets[asset.widget_code] = {
                    param: widgets[asset.widget_code][param]
                    for param in (widget_parameters[widgets[asset.widget_code]['type']] + ['position'])
                    if param in widgets[asset.widget_code]
                }
                try:
                    widgets[asset.widget_code].update(json.loads(asset.widget_misc))
                except:
                    pass
            if asset.asset_code:
                widgets[asset.widget_code]['banners'].append(
                    {
                        'code': asset.asset_code,
                        'position': asset.asset_position,
                        'linkUrl': asset.link,
                        'imageUrl': CMS_CDN_HOST + (asset.image if asset.image else ""),
                    }
                )
            try:
                widgets[asset.widget_code].banners[-1].update(json.loads(asset.widget_misc))
            except:
                pass
        for widget_code in list(widgets.keys()):
            if 'banners' in widgets[widget_code] and len(widgets[widget_code]['banners']) == 0:
                widgets.pop(widget_code)
                continue
            if 'banners' in widgets[widget_code]:
                widgets[widget_code]['banners'].sort(key=lambda a: a['position'])
                for asset in widgets[widget_code]['banners']:
                    asset.pop('position')
        widgets = list(widgets.values())
        widgets.sort(key=lambda a: a['position'])
        for widget in widgets:
            widget.pop('position')
        return widgets
