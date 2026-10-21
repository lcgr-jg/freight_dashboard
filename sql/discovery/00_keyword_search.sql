-- Starter: find freight-relevant tables/columns by keyword across a database.
-- Note (2026-10-05): table-name search is weak for freight — ICE/Platts hide terms in
-- LONG_NAME / DESCRIPTION. Prefer run_steps_1_2.py + run_value_search_lean.py.
-- Avoid bare %WS% / %ICE% (noisy). Run per database (replace <DB>).
ALTER SESSION SET QUERY_TAG = 'freight-agent:discovery-keywords';

SELECT table_catalog, table_schema, table_name, row_count, bytes, last_altered, comment
FROM <DB>.INFORMATION_SCHEMA.TABLES
WHERE table_name ILIKE ANY ('%FREIGHT%','%TANKER%','%BALTIC%','%WORLDSCALE%','%FFA%',
                            '%BUNKER%','%FIXTURE%','%CHARTER%','%TONNAGE%','%KPLER%')
   OR comment ILIKE ANY ('%freight%','%tanker%','%baltic%','%worldscale%','%bunker%')
ORDER BY table_schema, table_name;

SELECT table_schema, table_name, column_name, data_type, comment
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE column_name ILIKE ANY ('%FREIGHT%','%WORLDSCALE%','%TCE%','%FLAT_RATE%','%FLATRATE%',
                             '%BUNKER%','%VLSFO%','%LAYCAN%','%CHARTER%','%TON_MILE%')
ORDER BY table_schema, table_name, ordinal_position;
