-- Spain vs its neighbours and the EU average, weekly (EU Oil Bulletin).
-- tax_share = share of duties+taxes in the pump price; the bulletin publishes
-- both price kinds, which makes this a free extra cut.
CREATE OR REPLACE VIEW mart_spain_vs_eu AS
SELECT
    ps.collected_at               AS week,
    p.attrs ->> 'country'         AS country,
    p.category                    AS category,
    ps.price_eur                  AS price_eur,
    ps.price_pre_tax_eur          AS price_pre_tax_eur,
    round(
        (ps.price_eur - ps.price_pre_tax_eur) / nullif(ps.price_eur, 0), 3
    )                             AS tax_share
FROM price_snapshots ps
JOIN products p ON p.id = ps.product_id
JOIN sources s  ON s.id = p.source_id
WHERE s.name = 'eu_bulletin'
  AND p.attrs ->> 'country' IN ('ES', 'FR', 'PT', 'IT', 'DE', 'EU');
