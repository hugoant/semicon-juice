from alpha_vantage.fundamentaldata import FundamentalData
import pandas as pd
import json

#api_key = "SSLCXMJFEXSSXMDO"
api_key = "XS1TD6D1K63MGJHB"
fd = FundamentalData(key=api_key, output_format='pandas')

companies = {
    'Nvidia': 'NVDA',
    'AMD': 'AMD',
    'Microchip': 'MCHP'
}

metrics = {
    'Revenue': 'totalRevenue',
    'Cost of Revenue': 'costOfRevenue',
    'R&D Expenses': 'researchAndDevelopment',
    'SG&A Expenses': 'sellingGeneralAndAdministrative',
    'CapEx': 'capitalExpenditures'
}

# If you need fiscal year offsets, adjust here
fiscal_year_starts = {
    'Nvidia': 2,
    'AMD': 1,
    'Microchip': 1
}

def get_fiscal_quarter_label(date, start_month):
    shifted_month = (date.month - start_month) % 12
    quarter = (shifted_month // 3) + 1
    fiscal_year = date.year
    if date.month < start_month:
        fiscal_year -= 1
    return f"Q{quarter}-{fiscal_year}"

data = {}

for company_name, symbol in companies.items():
    print(f"Fetching data for {company_name}...")
    income_statement, _ = fd.get_income_statement_quarterly(symbol)
    cash_flow, _ = fd.get_cash_flow_quarterly(symbol)
    
    # Convert dates and filter
    income_statement['fiscalDateEnding'] = pd.to_datetime(income_statement['fiscalDateEnding'], errors='coerce')
    income_statement = income_statement[income_statement['fiscalDateEnding'] >= '2020-01-01']
    
    cash_flow['fiscalDateEnding'] = pd.to_datetime(cash_flow['fiscalDateEnding'], errors='coerce')
    cash_flow = cash_flow[cash_flow['fiscalDateEnding'] >= '2020-01-01']

    # Ensure required income columns
    required_income_cols = ['fiscalDateEnding'] + [m for m in metrics.values() if m != 'capitalExpenditures']
    missing_inc_cols = set(required_income_cols) - set(income_statement.columns)
    if missing_inc_cols:
        print(f"Data missing for {company_name}: {missing_inc_cols}")
        continue
    
    # Ensure CapEx column
    if 'capitalExpenditures' not in cash_flow.columns:
        cash_flow['capitalExpenditures'] = None

    # Create main dataframe
    company_data = income_statement[required_income_cols].copy()
    company_data.set_index('fiscalDateEnding', inplace=True)

    # Merge CapEx data
    capex_data = cash_flow[['fiscalDateEnding', 'capitalExpenditures']].copy()
    capex_data.set_index('fiscalDateEnding', inplace=True)

    # Drop duplicate indices if any
    company_data = company_data[~company_data.index.duplicated(keep='first')]
    capex_data = capex_data[~capex_data.index.duplicated(keep='first')]

    company_data = company_data.join(capex_data, how='left')

    # Add quarter label
    fy_start = fiscal_year_starts.get(company_name, 1)
    company_data['Quarter'] = company_data.index.to_series().apply(lambda d: get_fiscal_quarter_label(d, fy_start))

    data[company_name] = company_data

# Convert to JSON
json_data = {company: df.reset_index().to_dict(orient='records') for company, df in data.items()}
with open('financial_data_v5.json', 'w') as f:
    json.dump(json_data, f, indent=4, default=str)

# Prepare for Excel
all_quarters = set()
for df_company in data.values():
    all_quarters.update(df_company['Quarter'])

# Sort quarter labels
def quarter_sort_key(q):
    q_part, year_part = q.split('-')
    quarter = int(q_part[1])
    year = int(year_part)
    return (year, quarter)

all_quarters = sorted(all_quarters, key=quarter_sort_key)

index = pd.MultiIndex.from_product([companies.keys(), metrics.keys()], names=['Company', 'Metric'])
df_excel = pd.DataFrame(index=index, columns=all_quarters)

for company, df_company in data.items():
    for metric_name, metric_column in metrics.items():
        # Ensure column exists
        if metric_column not in df_company.columns:
            continue
        for date in df_company.index:
            q_label = df_company.at[date, 'Quarter']
            # Retrieve scalar value
            val = df_company.at[date, metric_column]
            # Double check it's scalar
            if pd.api.types.is_list_like(val):
                # If for any reason val is not scalar, take first element or convert
                val = val[0] if len(val) > 0 else None
            # Assign with .at for a single cell
            if (company, metric_name) in df_excel.index and q_label in df_excel.columns:
                df_excel.at[(company, metric_name), q_label] = val

# Remove duplicate columns if any appear
df_excel = df_excel.loc[:, ~df_excel.columns.duplicated()]

df_excel.to_excel('financial_data_v5.xlsx')

print("Data including CapEx has been saved to 'financial_data.json' and 'financial_data.xlsx'.")