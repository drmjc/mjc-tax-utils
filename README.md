README for the project

Usage examples and notes.

CBA statement extraction
------------------------

The `cba/statement2tsv.py` script converts a Commonwealth Bank (CBA) PDF statement
into a TSV. The script now always outputs a signed `Amount` column (positive for
credits, negative for debits) with the columns:

- `Date`, `Transaction`, `Amount`, `Balance`

Usage:

```bash
python3 cba/statement2tsv.py path/to/Statement.pdf
```

By default the script writes the TSV next to the input PDF, replacing the
`.pdf` extension with `.tsv`. You can override the output path with:

```bash
python3 cba/statement2tsv.py path/to/Statement.pdf --out /tmp/out.tsv
```

Notes:
- `PyMuPDF` (package name `pymupdf`) is used for positional parsing. See
	`requirements.txt` for the runtime/test dependencies.
- The script previously offered a `--signed` flag; this behaviour is now the
	default and the flag was removed.
# tax-utils
Some hopefully useful utilities to help with preparing Australian tax returns, such as 
1. tracking work-related travel (google maps + RTA eToll statements)
2. Bunnings expenses
3. renaming monthly banking statements based on their dates
4. that's it for now...

# future ideas
It would be great to parse
1. Online Woolworths/coles orders
2. Supercheap auto
3. invoices that go through flybuys?

# about me / why this repo
I have a primary job as a scientist, but I also live on a small farm, rent out a cottage through Airbnb, and have a very long commute. That means lots of tax-deductible expenses for DIY, car, farm and cottage maintenance. These scripts aim to make life easier to collate all the data at the end of the year

Mark
