-- Average fuel price over time, both sources in one view:
--   series = 'es_stations':  Spain, daily, averaged across ~11.5k stations
--   series = 'eu_bulletin':  per country, weekly, as published by the EC
CREATE OR REPLACE VIEW mart_price_history AS
SELECT
    'es_stations'                 AS series,
    'ES'                          AS country,
    p.category                    AS category,
    ps.collected_at               AS price_date,
    round(avg(ps.price_eur), 3)   AS price_eur,
    NULL::numeric(10, 3)          AS price_pre_tax_eur,
    count(*)                      AS n_products
FROM price_snapshots ps
JOIN products p ON p.id = ps.product_id
JOIN sources s  ON s.id = p.source_id
WHERE s.name = 'fuel_es'
GROUP BY p.category, ps.collected_at

UNION ALL

SELECT
    'eu_bulletin'                 AS series,
    p.attrs ->> 'country'         AS country,
    p.category                    AS category,
    ps.collected_at               AS price_date,
    ps.price_eur                  AS price_eur,
    ps.price_pre_tax_eur          AS price_pre_tax_eur,
    1                             AS n_products
FROM price_snapshots ps
JOIN products p ON p.id = ps.product_id
JOIN sources s  ON s.id = p.source_id
WHERE s.name = 'eu_bulletin';
