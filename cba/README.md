
# bulk processing of many CBA statments
parallel --env PATH cba_auto2tsv {} ::: *.pdf
cba_aggregate_statements . --fy
