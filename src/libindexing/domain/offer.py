from libutil.spanner_util import boilerplate_spanner


def get_product_and_offer_details_for(sku_wh_code_list):
    number_of_skus = len(sku_wh_code_list)
    if number_of_skus == 0:
        return []

    query = f'''
        SELECT
           p.sku,
           p.sku_config,
           o.wh_code,
           o.country_code, 
           o.offer_price,
           par.title as title_ar,
           pen.title as title_en,
           p.category_ids,
           pen.meta_keywords as meta_keywords_en,
           par.meta_keywords as meta_keywords_ar,
           par.brand as ar_brand,
           pen.brand as en_brand,
           p.category_ids,
           p.brand_code as brand_code,
           os.stock_net,
           p.family_code,
           p.brand_code,
           p.is_active,
           p.attributes,
           p.group_code
        FROM product p 
        JOIN product_en pen USING (sku) 
        JOIN product_ar par USING (sku) 
        JOIN offer o USING (sku) 
        JOIN offer_stock os ON (o.sku = os.sku AND o.wh_code = os.wh_code) 
        WHERE
           STRUCT <sku STRING,wh_code STRING> (o.sku, o.wh_code) in UNNEST(@sku_wh_code)
    '''

    return boilerplate_spanner().execute_query(query, sku_wh_code=list(sku_wh_code_list),
                                           key_order={"sku_wh_code": ("sku", "wh_code")}).dicts()


def get_in_stock_offers(sku_list):
    in_stock_offers_query = f'''
        SELECT
           p.sku,
           p.sku_config,
           o.wh_code,
           o.offer_price,
           os.country_code,
           par.title as title_ar,
           pen.title as title_en,
           pen.meta_keywords as meta_keywords_en,
           par.meta_keywords as meta_keywords_ar,
           par.brand as ar_brand,
           pen.brand as en_brand,
           p.category_ids,
           p.brand_code as brand_code,
           os.stock_net,
           p.family_code,
           p.brand_code,
           p.is_active,
           p.attributes,
           p.group_code
        FROM
           product p 
           JOIN
              product_en pen USING (sku) 
           JOIN
              product_ar par USING (sku) 
           JOIN
              offer o USING (sku) 
           JOIN
              offer_stock os ON (o.sku = os.sku AND o.wh_code = os.wh_code) 
        WHERE
           p.sku in UNNEST(@sku_list) 
           AND os.stock_net > 0
    '''
    return boilerplate_spanner().execute_query(in_stock_offers_query, sku_list=sku_list).dicts()
