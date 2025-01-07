#!/bin/bash
#
# Split a CSV of transactions into each financial year.
# Column 1 must be the date of the transaction in DD/MM/YYYY format.
# 
# Motivation
# I have lots of invoices from Bunnings over several years, some of these items will be tax deductable. 
# So I wanted to extract the transactions from several multi-page PDFs (see parse_bunnings_transactions_transactions.py),
# then combine all the CSVs into one master CSV (see combine_bunnings_transactions.sh), 
# then split the transactions into each financial year (see split_by_financial_year.sh).
#
# Usage
# ./split_by_financial_year.sh bunnings_transaction_report.csv
#
# This is usually step 3 in a pipeline of processing transaction data
# for pdf in *pdf; do python3 parse_bunnings_transactions.py "${pdf}"; done
# ./combine_bunnings_transactions.sh bunnings*part*csv
# rm bunnings_transaction_report_fy202?.csv # needed if this is not the first time running the script.
# ./split_by_financial_year.sh bunnings_transaction_report.csv
#
# Output
# one CSV and XLSX file of transactions for each year, named as such:
# from this input file: bunnings_transaction_report.csv, the following result files will be created:
# bunnings_transaction_report_fy2021.csv
# bunnings_transaction_report_fy2021.xlsx
# bunnings_transaction_report_fy2022.csv
# bunnings_transaction_report_fy2022.xlsx
# ...
#
# Limitations
# * It doesn't check if the fq csv files already exist, so by default it will append new entries onto old files.
#
# Author
# Mark Cowley, 2025-01-07
#

# Check if the filename is provided as an argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <input_csv_file>"
    exit 1
fi

input_file="$1"
header=$(head -n 1 "$input_file")
base_name=$(basename "$input_file" .csv)

# Read the CSV file line by line
tail -n +2 "$input_file" | while IFS=, read -r date rest; do
    # Extract the day, month, and year from the date
    day=$(echo "$date" | cut -d'/' -f1)
    month=$(echo "$date" | cut -d'/' -f2)
    year=$(echo "$date" | cut -d'/' -f3)

    # Determine the financial year
    if [ "$month" -ge 7 ]; then
        fin_year=$((year + 1))
    else
        fin_year=$year
    fi

    # Create a file for the financial year if it doesn't exist
    output_file="${base_name}_fy${fin_year}.csv"
    if [ ! -f "$output_file" ]; then
        echo "$header" > "$output_file"
    fi

    # Append the line to the appropriate financial year file
    echo "$date,$rest" >> "$output_file"
done


# Function to check if a Python package is installed
check_package_installed() {
    package=$1
    if ! python3 -c "import $package" &> /dev/null; then
        echo "Error: $package is not installed. Please install it using 'pip install $package'."
        exit 1
    fi
}

packages=("pandas" "openpyxl")
for package in "${packages[@]}"; do
    check_package_installed $package
done

# Python script to convert CSV files to XLSX
python3 - <<EOF
import pandas as pd
import glob

# Get all CSV files matching the pattern
csv_files = glob.glob("${base_name}_fy*.csv")

for csv_file in csv_files:
    # Read the CSV file
    df = pd.read_csv(csv_file)
    
    # Convert to Excel file
    excel_file = csv_file.replace('.csv', '.xlsx')
    df.to_excel(excel_file, index=False)

print("All CSV files have been converted to XLSX format.")
EOF
