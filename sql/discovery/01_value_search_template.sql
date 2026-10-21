-- Template: search descriptive columns of an instrument/contract master for freight terms.
-- Replace <TABLE> and <DESC_COL>/<CODE_COL> after step 2 identifies the master table.
SELECT <CODE_COL>, <DESC_COL>, COUNT(*) AS n
FROM <TABLE>
WHERE <DESC_COL> ILIKE ANY ('%TD3C%','%TD2 %','%TD15%','%TD20%','%TD22%','%TD25%','%TD6%',
                            '%TC2%','%TC14%','%TC7%','%TC12%','%freight%','%tanker%',
                            '%VLCC%','%suezmax%','%aframax%','%worldscale%','%baltic%')
GROUP BY 1, 2
ORDER BY 2
LIMIT 500;
