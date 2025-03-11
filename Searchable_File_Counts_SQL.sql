-- How to Use:
-- Find out the consistency in file counts across data 
-- pipeline layers

-- Acquisition
-- To find out the files acquired we have more flexibility. 
-- You can put in 837 or 835 into the data_feed parameter to 
-- see all the files of those types, or enter a site code to 
-- get an idea on facilities. You can also just enter in a 
-- client name (not the entire trading partner id) into the 
-- trading_partner parameter.

-- Ingestion
-- If you do the broad (wildcard version) of the parameters, 
-- the ingestion file count won't work. Due to the data_feed 
-- and trading_partner being part of the table being called, 
-- there isn't any flexibility on names. If you want to see 
-- the table names available for the trading partner id go 
-- to the last cell in this notebook.

----Create Temp View for Acquisition Year and Month----
CREATE OR REPLACE TEMP VIEW temp_view_year_month AS
SELECT *, 
LEFT(src_last_modified, 7) AS year_month FROM prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history 
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

SELECT
    year_month,
    COUNT(DISTINCT file_path) AS unique_file_paths
FROM
    temp_view_year_month
WHERE year_month LIKE '2019%' OR
      year_month LIKE '2020%' OR
      year_month LIKE '2021%' OR
      year_month LIKE '2022%' OR 
      year_month LIKE '2023%' OR 
      year_month LIKE '2024%' OR 
      year_month LIKE '2025%' 
GROUP BY year_month
ORDER BY
    year_month;

----Create Temp View for Acquisition Year Only----
CREATE OR REPLACE TEMP VIEW temp_view_year AS
SELECT *, 
LEFT(src_last_modified, 4) AS year FROM prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history 
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%') 
AND (data_feed LIKE '%' || '${data_feed}' || '%');

SELECT
    year,
    COUNT(DISTINCT file_path) AS unique_file_paths
FROM
    temp_view_year
WHERE
    year IN ('2019', '2020', '2021', '2022', '2023', '2024', '2025')  
GROUP BY
    year
ORDER BY
    year;

----Create a temporary view for acquisition data with stripped file paths----
CREATE OR REPLACE TEMP VIEW temp_view_acquisition_year_month AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 7) AS src_last_modified_short
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

----Create a temporary view for ingestion data----
CREATE OR REPLACE TEMP VIEW temp_view_ingested AS
SELECT 
    SUBSTRING_INDEX(meta_lineage_source_name, '/', -1) AS stripped_meta_lineage_source_name
FROM 
    prd_data_platform.${trading_partner}__ingested.${data_feed}__history;

----Sort by Last Modified Date----
SELECT 
    a.src_last_modified_short,
    COUNT(DISTINCT stripped_meta_lineage_source_name) AS unique_file_paths
FROM 
    temp_view_acquisition_year_month a
JOIN 
    temp_view_ingested i ON a.stripped_file_path = REPLACE(i.stripped_meta_lineage_source_name, '.bz2', '')
GROUP BY a.src_last_modified_short
ORDER BY a.src_last_modified_short ASC;

----Create a temporary view for acquisition data year only----
CREATE OR REPLACE TEMP VIEW temp_view_acquisition_year AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 4) AS src_last_modified_short_year
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

----Create a temporary view for ingestion data----
CREATE OR REPLACE TEMP VIEW temp_view_ingestion_feed AS
SELECT 
    SUBSTRING_INDEX(meta_lineage_source_name, '/', -1) AS stripped_meta_lineage_source_name
FROM 
    prd_data_platform.${trading_partner}__ingested.${data_feed}__history;


SELECT 
    a.src_last_modified_short_year,
    COUNT(DISTINCT stripped_meta_lineage_source_name) AS unique_file_paths
FROM 
    temp_view_acquisition_year a
JOIN 
    temp_view_ingestion_feed i ON a.stripped_file_path = REPLACE(i.stripped_meta_lineage_source_name, '.bz2', '')
GROUP BY a.src_last_modified_short_year
ORDER BY a.src_last_modified_short_year ASC;

----Standardized Data Investigation Year and Month----
CREATE OR REPLACE TEMP VIEW temp_view_acquisition AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 7) AS src_last_modified_short
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

CREATE OR REPLACE TEMP VIEW temp_table_std_year_month_835 AS
SELECT *, 
       SUBSTRING_INDEX(meta_lineage_source_name, '/', -1) AS stripped_meta_lineage_source_name_std_835
FROM prd_data_platform.${trading_partner}__claims__standardized.835__claims_advice_payment__history;

SELECT 
    a.src_last_modified_short,
    COUNT(DISTINCT stripped_meta_lineage_source_name_std_835) AS unique_file_paths
FROM 
    temp_view_acquisition a
JOIN 
    temp_table_std_year_month_835 s_835 ON a.stripped_file_path = REPLACE(s_835.stripped_meta_lineage_source_name_std_835, '.bz2', '')
GROUP BY a.src_last_modified_short
ORDER BY a.src_last_modified_short ASC;

----Standardized Data Investigation Year----
CREATE OR REPLACE TEMP VIEW temp_view_acquisition AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 4) AS src_last_modified_year
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

-- create a temp view for 835 standardized data
CREATE OR REPLACE TEMP VIEW temp_table_std_year_month_835 AS
SELECT *, 
       SUBSTRING_INDEX(meta_lineage_source_name, '/', -1) AS stripped_meta_lineage_source_name_std_835
FROM prd_data_platform.${trading_partner}__claims__standardized.835__claims_advice_payment__history;

SELECT 
    a.src_last_modified_year,
    COUNT(DISTINCT s_835.stripped_meta_lineage_source_name_std_835) AS unique_file_paths
FROM 
    temp_view_acquisition a
JOIN 
    temp_table_std_year_month_835 s_835 ON a.stripped_file_path = REPLACE(s_835.stripped_meta_lineage_source_name_std_835, '.bz2', '')
GROUP BY a.src_last_modified_year
ORDER BY a.src_last_modified_year ASC;

----Shared Investigation Year----
-- Create a temporary view for acquisition data for year
CREATE OR REPLACE TEMP VIEW temp_view_acquisition AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 4) AS src_last_modified_year
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

-- create a temp view for 835 standardized data
CREATE OR REPLACE TEMP VIEW temp_table_std_year_shared AS
SELECT *, 
       SUBSTRING_INDEX(FileName, '/', -1) AS file_name
FROM prd_data_platform.${trading_partner}__claims__shared.clm02e;

SELECT 
    a.src_last_modified_year,
    COUNT(DISTINCT sh_835.file_name) AS unique_file_paths
FROM 
    temp_view_acquisition a
JOIN 
    temp_table_std_year_shared sh_835 ON a.stripped_file_path = REPLACE(sh_835.file_name, '.bz2', '')
GROUP BY a.src_last_modified_year
ORDER BY a.src_last_modified_year ASC;

----Shared layer investigation year and month----
-- Create a temporary view for acquisition data for year
CREATE OR REPLACE TEMP VIEW temp_view_acquisition AS
SELECT 
    CASE 
        WHEN RIGHT(file_path, 4) = '.bz2' THEN 
            SUBSTRING_INDEX(SUBSTRING_INDEX(file_path, '/', -1), '.bz2', 1)
        ELSE 
            SUBSTRING_INDEX(file_path, '/', -1)
    END AS stripped_file_path,
    LEFT(src_last_modified, 7) AS src_last_modified_year_month
FROM 
    prd_data_platform.r1_rcm__ingested.acquisition_db_ledger__history
WHERE (trading_partner LIKE '%' || '${trading_partner}' || '%')
AND (data_feed LIKE '%' || '${data_feed}' || '%');

-- create a temp view for 835 standardized data
CREATE OR REPLACE TEMP VIEW temp_table_std_year_shared AS
SELECT *, 
       SUBSTRING_INDEX(FileName, '/', -1) AS file_name
FROM prd_data_platform.${trading_partner}__claims__shared.clm02e;

SELECT 
    a.src_last_modified_year_month,
    COUNT(DISTINCT sh_835.file_name) AS unique_file_paths
FROM 
    temp_view_acquisition a
JOIN 
    temp_table_std_year_shared sh_835 ON a.stripped_file_path = REPLACE(sh_835.file_name, '.bz2', '')
GROUP BY a.src_last_modified_year_month
ORDER BY a.src_last_modified_year_month ASC;