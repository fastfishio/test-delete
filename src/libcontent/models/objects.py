from datetime import datetime

from libutil import util


class WidgetAsset(util.NoonBaseModel):
    widget_code: str
    widget_type: str
    widget_title: str
    widget_position: int
    widget_misc: str | None
    num_per_row: str | None
    title_color: str | None
    product_url: str | None
    build_ge: str | None
    asset_code: str | None
    asset_position: int | None
    link: str | None
    image: str | None
    criteria: str | None
    start_date: datetime | None
    end_date: datetime | None
