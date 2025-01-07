#!/bin/bash
# Combine several CSVs of Bunnings transactions into one master CSV file.
# It only keeps the header row from the first file, and sorts the transactions by date.
#
# Motivation
# I have lots of invoices from Bunnings over several years, some of these items will be tax deductable. 
# So I wanted to extract the transactions from several multi-page PDFs (see parse_bunnings_transactions_transactions.py),
# then combine all the CSVs into one master CSV (see combine_bunnings_transactions.sh), 
# then split the transactions into each financial year (see split_by_financial_year.sh).
# This script likely works well for any file that has the data in DD/MM/YYYY format in column 1.
#
# Usage
# ./combine_bunnings_transactions.sh bunnings_transaction_report_fy2021.csv bunnings_transaction_report_fy2022.csv bunnings_transaction_report_fy2023.csv
# ./combine_bunnings_transactions.sh bunnings*part*csv
#
# This is usually step 2 in a pipeline of processing transaction data
# for pdf in *pdf; do python3 parse_bunnings_transactions.py "${pdf}"; done
# ./combine_bunnings_transactions.sh bunnings*part*csv
# ./split_by_financial_year.sh bunnings_transaction_report.csv
#
# Limitations
# * It does not 'uniquify' the records, because within one invoice, you may have bought >1 of the same item. 
# However if you have downloaded the same invoice PDF more than once, then this will lead to enmasse duplicates
#
# Author
# Mark Cowley, 2025-01-07
#

# Check if at least one CSV file is provided as an argument
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <input_csv_file1> <input_csv_file2> ... <input_csv_fileN>"
    exit 1
fi

tmp=$(mktemp)
# Iterate over each input CSV file
for input_file in "$@"; do
    # Append the contents of the file, skipping the header
    tail -n +2 "$input_file" >> "$tmp"
done

output_file="bunnings_transaction_report.csv"
head -n 1 "$1" > "$output_file"
sort -t, -k1.7,1.10n -k1.4,1.5n -k1.1,1.2n -k6,6 "$tmp" >> "$output_file"
rm $tmp

echo "All CSV files have been merged into $output_file"
