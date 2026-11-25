# Data sources: coverage and terms

Every source is public and keyless, and is queried politely: one request at a time, with retries
and backoff, and with a contact address where the provider asks for one (`SOURCESWEEP_EMAIL`).
Coverage is best-effort. Providers change their APIs and limits without notice. A failing source
is reported in the report header and the rest of the scan continues.

| Source | Endpoint | What is searched | Notes |
|---|---|---|---|
| ClinicalTrials.gov | API v2 `/studies` | All fields, plus condition when `restrict.condition` is set | Keeps active trials and any updated in the window |
| EU CTIS | Public search API on euclinicaltrials.eu | Full-text contains | Date is the last update, so older records appear. Endpoint is undocumented and may change |
| PubMed | NCBI E-utilities `esearch` + `efetch` | Title/abstract, by entry date | NCBI asks for a tool name and email, and limits keyless use to 3 requests a second. An asterisk in a keyword (`HLA-A*02:01`) is read as a wildcard |
| Europe PMC | REST search, `SRC:PPR` | Title and abstract of preprints | bioRxiv, medRxiv, Research Square, Preprints.org and others |
| SEC EDGAR | Full-text search (`efts.sec.gov`) | Filing text, per keyword | The SEC requires a User-Agent with contact details and allows up to 10 requests a second. Amendments of the same filing are collapsed |
| Trade press | Google News RSS, `site:` restricted | Article text as indexed by Google News | Default sites: fiercebiotech.com, endpts.com, biospace.com, statnews.com, biopharmadive.com, globenewswire.com, businesswire.com, prnewswire.com. Headlines only, no article text |
| News | Google News RSS | Keyword must appear in the headline | Stories already found as trade press are dropped |

## Not covered

- **Patents.** No keyless official API. Scraping Google Patents is not allowed.
- **Conference abstracts.** No open API. Run a targeted web search around meeting dates.
- **WHO ICTRP.** No public API.
- **Full news articles.** Only headlines and links.

## Content ownership

Abstracts, filings and articles belong to their publishers. The source pack keeps their text so
you can work with it internally. Reports link to the originals. Don't republish source packs. The
`--no-abstracts` option and the public-repo workflow leave abstracts out of anything that is posted
publicly.
