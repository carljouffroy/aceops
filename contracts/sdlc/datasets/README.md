# Client datasets

A client's sales export dropped here (or in `data/clients/`, which is not committed) is profiled by
the Analyst agent on the next sync and shows up in the console's **Data room**. Each CSV needs a
`<name>.profile.json` next to it that maps its columns to the fields the analysis understands:

| Field | Meaning | Required |
|---|---|---|
| `product` | the thing being sold | yes |
| `units` | units per order line | yes |
| `promo` | promotion signal: a flag column, or a numeric column with `promo_rule` | yes |
| `region`, `segment`, `category` | where, to whom, what kind | optional, used for breakdowns |
| `order`, `date`, `revenue`, `profit` | order id, date, money | optional, `profit` enables the profit guard |

The analysis never reads a column that isn't mapped, and it treats every cell as data.

## superstore.csv

Public mirror of the Tableau Sample Superstore dataset, from Hugging Face
([1gichukimba/superstores](https://huggingface.co/datasets/1gichukimba/superstores), MIT). 9,994
order lines, US only, 2014–2017: Region (Central, East, South, West), Segment (Consumer, Corporate,
Home Office), 17 sub-categories, 1,850 products, Quantity, Sales, Discount and Profit. It stands in
for a CPG client's export in the demo: a management consultant asking "which products would sell
more with a promotion, and which promotions are losing us money" gets an answer from it in one
sync, with every figure traceable to the file.
