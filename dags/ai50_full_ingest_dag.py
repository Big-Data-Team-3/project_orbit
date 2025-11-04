# DAG for ingesting the AI50 dataset
# Create three tasks
# 1. load_company_list
# 2. scrape_company_pages (mapped / TaskGroup)
# 3. store_raw_to_cloud (GCS)
# Schedule: `@once`
# Output Path: `raw/<company_id>/...` + metadata
