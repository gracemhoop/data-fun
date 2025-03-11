import pandas as pd

# Verify active spark session
if 'spark' in globals():
    print("Spark session is active.")
else:
    print("Spark session is not active.")

# Verify active spark context
if 'sc' in globals():
    print("Spark context is active.")
else:
    print("Spark context is not active.")

# Search the catalog for schema within it and for tables that have 837 or 835 in the title
if 'spark' in globals():
    try:
        # Catalog
        catalog_name = "prd_data_platform"

        # All schemas in the catalog
        schemas = spark.sql(f"SHOW SCHEMAS IN {catalog_name}").collect()

        # Initialize empty list to store results from iteration
        result = []

        # Iterate through the schemas
        # namespace, databaseName, and tableName are from Spark, not user defined
        for schema in schemas:
            schema_name = schema['namespace'] if 'namespace' in schema else schema['databaseName']
            
            # Get all tables in the schema
            try:
                tables = spark.sql(f"SHOW TABLES IN {catalog_name}.{schema_name}").collect()

                # Check for tables containing '835' or '837' in their names by using the output
                # from the tables SQL query above and iterating through the names
                for table in tables:
                    table_name = table['tableName']
                    # Add the results to the empty result list and continue to do so
                    # as matches are found 
                    if '835' in table_name or '837' in table_name:
                        result.append((schema_name, table_name))

            # Debugging
            except Exception as e:
                print(f"Error processing schema {schema_name}: {e}")

        # Create pandas df which will be used later to join tables
        if result:
            df = pd.DataFrame(result, columns=['Schema', 'Table'])
            # display(df)
        else:
            print("No tables containing '835' or '837' found in any schema.")

    # Debugging
    except Exception as e:
        print(f"An error occurred: {e}")

# If the above condition is not met then the spark session is not active and this message will 
# be the output
else:
    print("Spark session is not active. Please ensure you are running this in a Databricks notebook with an active Spark session.")

# Create a copy of the df so as to not change it with alterations that will be made
schema_df = df

# Filter Ingested and Standardized DataFrame based on the presence of 3 keywords in the "Schema" column
# the terms in this are "Schema", which is the column name, and we are looking within the dataframe of 
# schemas to see if the words 'ingested' or 'standardized' appear in them. We then are splitting into
# two datframes called "ingested_df" and "standardized_df"
ingested_df = schema_df[schema_df['Schema'].str.contains('ingested', case=False)]
standardized_df = schema_df[schema_df['Schema'].str.contains('standardized', case=False)]

print("Data has been successfully split and tables have been created in Databricks.")

# Function to determine the new column value
# This is to simplify the output due to there being a large amount of tables within schemas that 
# have the names 835 or 837 repeated in them. If there is at least *one* table of the type we can
# assume the acquisition and ingestion has been completed so we don't need the specific table names
# and we want to simplify the dataframes
def determine_value(row):
    if '835' in row:
        return '835'
    elif '837' in row:
        return '837'
    else:
        return None

# Applying the function to create the new column and clean table
ingested_df['Table Type Ingested'] = ingested_df['Table'].apply(determine_value)
ingested_df['Base Schema'] = ingested_df['Schema'].str.split('__').str[0]
ingested_df = ingested_df[['Base Schema','Table Type Ingested']]
ingested_df = ingested_df.drop_duplicates()

# Applying to this table as well to create a new column which we will call "Table Type Standardized"
# We don't drop the "Table" column for this table because we want to see claims_account_crosswalk still for later use
standardized_df['Table Type Standardized'] = standardized_df['Table'].apply(determine_value)

print("New columns identifying table type has been successfully added to the ingested and standardized tables")

display(standardized_df)

import warnings

# Suppress all warnings
warnings.filterwarnings("ignore")

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, isnan, trim

# Filter rows where 'Table' contains '835' or '837' and 'crosswalk' in any order
# Create a df called crosswalk_tables that looks at the standardized_df in the "Table" column and pulls out anything that meets the criteria
# of having "crosswalk" in its name. 
crosswalk_tables = standardized_df[standardized_df['Table'].str.contains(r'(835|837).*crosswalk|crosswalk.*(835|837)', regex=True)]

# We can check if account linking has been completed by looking into the crosswalk tables in Standardized and seeing if the account_number is populated
# This function will then be applied later to the crosswalk_tables
def check_account_number_populated(schema, table):
    # Construct the full table path using Spark commands
    full_table_path = f"prd_data_platform.{schema}.{table}"
    
    # Load the table into a Spark DataFrame
    table_df = spark.table(full_table_path)
    
    # Check if 'account_number' column exists and is populated into the spark dataframe
    if 'account_number' in table_df.columns:
        # Filter out rows where 'account_number' is null, NaN, or blank
        populated_count = table_df.filter(
            col('account_number').isNotNull() & 
            ~isnan('account_number') & 
            (trim(col('account_number')) != '')
        ).count()
        
        # If there are any populated rows, return True, otherwise False
        # Question: Would it be possible for account linking to only half work? Or do we assume that if there is anything at all then it's fully functional?
        return populated_count > 0
    else:
        return False

# Apply the check to each row in the crosswalk_tables DataFrame using the function created above and create a new column in the df called "Account Number Populated"
crosswalk_tables['Account Number Populated'] = crosswalk_tables.apply(
    lambda row: check_account_number_populated(row['Schema'], row['Table']), axis=1
)
display(crosswalk_tables)
print("Crosswalk table made successfully to verify account linking")

# Convert the result to a Pandas DataFrame
crosswalk_tables_pandas = pd.DataFrame(crosswalk_tables, columns=['Schema', 'Table', 'Table Type Standardized', 'Account Number Populated'])
# Rename the columns for clarity
crosswalk_tables_pandas.rename(columns={'Account Number Populated': 'Account Linking Completed'}, inplace=True)

# Copy the table to not mess with the original
crosswalk_tables_pandas_copy = crosswalk_tables_pandas.copy()
# Drop the Table column in order to simplify the table
crosswalk_tables_pandas_copy.drop(columns=['Table'], inplace=True)
# Drop duplicates
crosswalk_tables_pandas_copy = crosswalk_tables_pandas_copy.drop_duplicates()
# Currently the "Account Linking Completed" column is a boolean, we want it to be a string for later use. Changing the format to str.
crosswalk_tables_pandas_copy['Account Linking Completed'] = crosswalk_tables_pandas_copy['Account Linking Completed'].astype(str)

# Display the result
#display(crosswalk_tables_pandas_copy)
#display(standardized_df)
print("Conversion to pandas and cleanup of crosswalk_tables completed")

std_crosswalk = crosswalk_tables_pandas_copy.merge(
    standardized_df,
    on=['Schema', 'Table Type Standardized'],
    how='inner'  
)
# Merge crosswalk table and standardized table

import re

# Now we need to create a separate table for shared using spark. This is necessary because the shared schema does not have any tables title 835 or 837
# Initialize Spark session
spark = SparkSession.builder.appName("CheckTablesInSchemas").getOrCreate()

# List all schemas in the catalog
schemas_df = spark.sql("SHOW SCHEMAS IN prd_data_platform")

# Convert the Spark DataFrame to a Pandas DataFrame
schemas_pd = schemas_df.toPandas()

# Inspect the DataFrame to understand its structure
# print(schemas_pd.head())

# Create an empty list to store results
results_v2 = []

# Iterate through the shared schemas that exist and check for the existance of ANY tables.
# If there are tables in the shared schema then we can assume (if standardized is completed) the Shared portion is completed.
for index, row in schemas_pd.iterrows():
    schema_name = row['databaseName'] 
    if 'shared' in schema_name:
        tables_df = spark.sql(f"SHOW TABLES IN prd_data_platform.{schema_name}")
        has_tables = tables_df.count() > 0

        results_v2.append({
            'Schema': schema_name,  
            'Has Shared Tables': has_tables
        })

# Create a pandas dataframe with the results from the loop
shared_status = pd.DataFrame(results_v2)
# Create a copy of the dataframe to not mess with the original
shared_status_copy = shared_status.copy()
# Change the name to the "base schema," that is without the __claims_shared portion
# This is necessary to do a merge between all the tables (i.e., "Base Schema" is the primary key)
shared_status_copy["Base Schema"] = shared_status_copy['Schema'].str.split('__').str[0]
# Change the table names and their format
shared_status_copy = shared_status_copy[['Base Schema',"Has Shared Tables"]]

print("Shared status copy made and cleaned")

##standardized_df_copy = standardized_df.copy()
standardized_df_copy = std_crosswalk.copy()
# Also need to change to "Base Schema" by removing everything after __
standardized_df_copy["Base Schema"] = standardized_df_copy['Schema'].str.split('__').str[0]
# Change the table names and their format
standardized_df_copy = standardized_df_copy[['Base Schema', 'Table Type Standardized','Account Linking Completed']]

print("Standardized DF copy made and cleaned")

# We want to verify if a trading partner has standardized schemas at all, separately from whether there are 837 or 835 tables within said schema
# List all schemas in the catalog with spark
schemas_std_df = spark.sql("SHOW SCHEMAS IN prd_data_platform")

# Convert the Spark DataFrame to a Pandas DataFrame
schemas_std_pd = schemas_std_df.toPandas()

# Create an empty list to store results
results_v3 = []

# Iterate through the shared schemas that exist and check for tables
for index, row in schemas_std_pd.iterrows():
    schema_name = row['databaseName'] 
    if 'standardized' in schema_name:
        tables_df = spark.sql(f"SHOW TABLES IN prd_data_platform.{schema_name}")
        has_tables = tables_df.count() > 0

        results_v3.append({
            'Schema Standard': schema_name,  
            'Has Tables': has_tables
        })

standardized_exists = pd.DataFrame(results_v3)
print("Standardized schemas exist table created successfully")
# display(standardized_exists)

# Ensure 'Account Linking Completed' is of string type in standardized_df_copy - this is necessary to be able to format the table nicely
# if it is a boolean (as it currently is prior to this change) then it will be lowercase and will not respond to str commands
standardized_df_copy['Account Linking Completed'] = standardized_df_copy['Account Linking Completed'].astype(str)

# Merge dataframes
# If a base schema does not exist in the shared or standardized schema tables then it will read "null"
result_df = (
    ingested_df
    .merge(shared_status_copy, on='Base Schema', how='left')
    .merge(standardized_df_copy, on='Base Schema', how='left')
)

# display(result_df)

# Apply fillna after merging to avoid type inconsistencies. This changes the `null` entries to read 'N/A'
result_df.fillna('N/A', inplace=True)

# Replace 'N/A' in specific columns 
result_df['Table Type Standardized'] = result_df['Table Type Standardized'].replace('N/A', 'No Standardized schemas exist')
result_df['Has Shared Tables'] = result_df['Has Shared Tables'].replace('N/A', 'No Shared schemas exist')

# Update 'Table Type Ingested not In Standardized' column
# This looks at the "Table Type Ingested" and "Table Type Standardized" and sees if the two match. If they don't then it returns that
# there isn't a match and that that specific table type has not been completed in standardized. This would happen if, say, there are only
# 837 table types in standardized but we have 835 ingested for the trading partner ID. 
result_df['Table Type Ingested not In Standardized'] = result_df.apply(
    lambda row: 'Std Schema doesn\'t have any corresponding table types' 
                if str(row['Table Type Ingested']) != str(row['Table Type Standardized']) 
                else 'Std Schema has corresponding Ingested table types',
    axis=1
)

# display(result_df)

# Formatting. Remove any leading or trailing whitespace from each string in the Base Schema column
result_df['Base Schema'] = result_df['Base Schema'].str.strip()

# Remove prefixes and suffixes from 'Schema Standard' in standardized_exists
standardized_exists['Schema Standard'] = standardized_exists['Schema Standard'].str.replace(r'^__|__.*$', '', regex=True).str.strip()

# Check if 'Base Schema' exists in 'standardized_exists'. If it does not exist then a corresponding standardized schema does not exist for the ingested one
# then the cell is correspondingly populated. If it exists then it leave the cell alone.
standardized_schemas = set(standardized_exists['Schema Standard'])
result_df['Table Type Standardized'] = result_df.apply(
    lambda row: 'Schema Exists - no 835/837 tables' 
                if row['Base Schema'] in standardized_schemas and row['Table Type Standardized'] == 'No Standardized schemas exist' 
                else row['Table Type Standardized'],
    axis=1
)

# Logic to check if 'Table Type Ingested' exists in 'standardized_df_copy' for the corresponding 'Base Schema'
def check_table_type_exists(row):
    base_schema = row['Base Schema']
    table_type_ingested = row['Table Type Ingested']
    
    if row['Table Type Standardized'] == 'No Standardized schemas exist':
        return 'No Standardized schemas exist'
    
    # Create a subset of standardized_df_copy that contains only the rows relevant to the current "Base Schema" being processed
    # This will then be used below for further checks (i.e., verifying if a specific ingested table type actually exists in Standardized Schema)
    corresponding_standardized = standardized_df_copy[standardized_df_copy['Base Schema'] == base_schema]
    
    # We need to see if there are corresponding 835 or 837 tables for each ingested. If there are then we can say that a corresponding table type exists
    # We do this by seeing if there is a table type of 835 or 837 for the base schema. For example, if we have a client that we have ingested both
    # 835s and 837s for, but we only see tables titled '837' in the standardized schema, then we would say that "Table type 835 does not exist - need to investigate"
    # If there are no 835 or 837 tables at all then we just say standardization is not completed
    if table_type_ingested in corresponding_standardized['Table Type Standardized'].values:
        return f"Table {table_type_ingested} type exists"
    else:
        return f"Table {table_type_ingested} type does not exist - need to investigate"

# Apply the created formula above to the result_df
result_df['Table Type Existence Check'] = result_df.apply(check_table_type_exists, axis=1)

# Drop the 'Table Type Standardized' column
result_df.drop(columns=['Table Type Standardized'], inplace=True)

# Rename columns
result_df.rename(columns={
    'Base Schema': 'Trading Partner ID',
    'Table Type Existence Check': 'Standardized Table Type Existence'
}, inplace=True)

# Reorder columns to match the steps of the process
result_df = result_df.reindex(columns=[
    'Trading Partner ID', 
    'Table Type Ingested', 
    'Standardized Table Type Existence', 
    'Has Shared Tables',
    'Account Linking Completed'
])

# Formatting the table to make it prettier
# Remove duplicates
result_df.drop_duplicates(inplace=True)

# Rename columns
result_df.rename(columns={
    'Standardized Table Type Existence': 'Standardized Completed',
    'Has Shared Tables': 'Shared Completed'
}, inplace=True)

# Ensure 'Shared Completed' column is treated as strings
result_df['Shared Completed'] = result_df['Shared Completed'].astype(str)

# Update the 'Shared Completed' column values
result_df['Shared Completed'] = result_df['Shared Completed'].apply(
    lambda x: 'True' if x == 'true' else ('False' if x == 'false' else x)
)

# Update the 'Standardized Completed' column values
result_df['Standardized Completed'] = result_df['Standardized Completed'].apply(
    lambda x: 'True' if x in ['Table 837 type exists', 'Table 835 type exists'] else x
)

# Update the 'Account Linking Completed' column values
result_df['Account Linking Completed'] = result_df['Account Linking Completed'].apply(
    lambda x: 'False' if x == 'N/A' else x
)

# Keep the row with 'False' in 'Account Linking Completed' if it exists
# This is necessary because it was throwing out incorrect False entries which was confirmed by the same trading partner id having account
# linking completed in another row - if it's true for one line it is true for all for the trading partner
def keep_false_row(group):
    false_rows = group[group['Account Linking Completed'] == 'False']
    if not false_rows.empty:
        return false_rows
    else:
        return group.head(1)

# Apply the function to each group
filtered_df = result_df.groupby(['Trading Partner ID', 'Table Type Ingested']).apply(keep_false_row).reset_index(drop=True)
# Ensure that the 'Shared Completed' column is set to `'False'` for any row where the 'Standardized Completed' column contains the string `'type does not exist - 
# need to #investigate'`. For all other rows, the 'Shared Completed' column retains its original value. 
filtered_df['Shared Completed'] = filtered_df.apply(
    lambda row: 'False' if 'type does not exist - need to investigate' in row['Standardized Completed'] else row['Shared Completed'],
    axis=1
)
# ensure that the 'Account Linking Completed' column is set to `'False'` for any row where the 'Standardized Completed' column contains the string 
# `'type does not exist - need to investigate'`. For all other rows, the 'Account Linking Completed' column retains its original value.
filtered_df['Account Linking Completed'] = filtered_df.apply(
    lambda row: 'False' if 'type does not exist - need to investigate' in row['Standardized Completed'] else row['Account Linking Completed'],
    axis=1
)

# Display the final DataFrame
display(filtered_df)

# Dashboard ideas: Total types of feed types ingested. Total type of ingested feeds that have standardization completed. Total feeds that
# have shared and standardization completed. Total types that have everything completed. 

import matplotlib.pyplot as plt
import seaborn as sns

filtered_df_copy = filtered_df.copy()

# Summarize Data
summary_df_ing = filtered_df_copy.groupby('Table Type Ingested').agg(
    Total_Records=('Trading Partner ID', 'count'),
).reset_index()
summary_df_ing.rename(columns={'Table Type Ingested':'Data Type'}, inplace=True)
summary_df_ing.rename(columns={'Total_Records':'Total Records'}, inplace=True)
# Display Summary
display(summary_df_ing)

# Filter rows where 'Account Linking Completed' is 'TRUE'
account_linking_summary = filtered_df_copy[filtered_df_copy['Account Linking Completed'] == 'True']

# Select only the relevant columns
account_linking_summary = account_linking_summary[['Trading Partner ID', 'Table Type Ingested', 'Account Linking Completed']]

# Print the new DataFrame
display(account_linking_summary)

account_linking_summary_grouped = account_linking_summary.groupby('Table Type Ingested').size().reset_index(name='Total Account Linked')
display(account_linking_summary_grouped)

# Filter rows where 'Account Linking Completed' is 'TRUE'
shared_summary = filtered_df_copy[filtered_df_copy['Shared Completed'] == 'True']

# Select only the relevant columns
shared_summary = shared_summary[['Trading Partner ID', 'Table Type Ingested', 'Shared Completed']]

# display(shared_summary)
# Create a combined key in both DataFrames
account_linking_summary['Combined Key'] = account_linking_summary['Trading Partner ID'] + '_' + account_linking_summary['Table Type Ingested']
shared_summary['Combined Key'] = shared_summary['Trading Partner ID'] + '_' + shared_summary['Table Type Ingested']

# Extract the combined keys that are in the account_linking_summary
account_linking_keys = account_linking_summary['Combined Key'].unique()

# Exclude rows where the combined key is in account_linking_keys
shared_summary_only = shared_summary[~shared_summary['Combined Key'].isin(account_linking_keys)].copy()

# Drop the Combined Key column as it's no longer needed
shared_summary_only.drop(columns=['Combined Key'], inplace=True)

# Print the new DataFrame
display(shared_summary_only)

shared_summary_only_grouped = shared_summary_only.groupby('Table Type Ingested').size().reset_index(name='Total Only Shared and Standardized')
display(shared_summary_only_grouped)

# Filter rows where 'Account Linking Completed' is 'TRUE'
standardized_summary = filtered_df_copy[filtered_df_copy['Standardized Completed'] == 'True']

# Select only the relevant columns
standardized_summary = standardized_summary[['Trading Partner ID', 'Table Type Ingested', 'Standardized Completed']]

display(standardized_summary)

# Filter rows where 'Standardized Completed' is not 'TRUE'
ingested_only = filtered_df_copy[filtered_df_copy['Standardized Completed'] != 'True']
ingested_only = ingested_only[['Trading Partner ID', 'Table Type Ingested']]

# Print the new DataFrame
display(ingested_only)

ingested_only_grouped = ingested_only.groupby('Table Type Ingested').size().reset_index(name='Total Only Ingested')
display(ingested_only_grouped)
display(ingested_only_grouped)