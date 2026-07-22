-- Price spread across Spain, daily, sliced two ways:
--   dimension = 'province': where is fuel cheap/expensive
--   dimension = 'brand':    which chains price systematically higher
-- Brand names come straight from the stations feed and are noisy; consumers
-- (notebook, web) should filter by n_stations to keep meaningful groups.
CREATE OR REPLACE VIEW mart_regional_spread AS
SELECT
    'province'                    AS dimension,
    p.attrs ->> 'province'        AS name,
    p.category                    AS category,
    ps.collected_at               AS price_date,
    round(avg(ps.price_eur), 3)   AS avg_price_eur,
    min(ps.price_eur)             AS min_price_eur,
    max(ps.price_eur)             AS max_price_eur,
    count(*)                      AS n_stations
FROM price_snapshots ps
JOIN products p ON p.id = ps.product_id
JOIN sources s  ON s.id = p.source_id
WHERE s.name = 'fuel_es'
GROUP BY p.attrs ->> 'province', p.category, ps.collected_at

UNION ALL

SELECT
    'brand',
    p.attrs ->> 'brand',
    p.category,
    ps.collected_at,
    round(avg(ps.price_eur), 3),
    min(ps.price_eur),
    max(ps.price_eur),
    count(*)
FROM price_snapshots ps
JOIN products p ON p.id = ps.product_id
JOIN sources s  ON s.id = p.source_id
WHERE s.name = 'fuel_es'
GROUP BY p.attrs ->> 'brand', p.category, ps.collected_at;
