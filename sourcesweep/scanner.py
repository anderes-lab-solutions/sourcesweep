#!/usr/bin/env python3
"""SourceSweep: US + EU trials, PubMed, preprints, SEC filings, trade press and news
for a set of search keywords. Standard library only, so the same file runs inside a Claude skill.

Copyright (C) 2026 Tegan Anderes / Anderes Lab Solutions.
Licensed under the GNU Affero General Public License v3.0 only (AGPL-3.0-only); see LICENSE and NOTICE.
https://github.com/anderes-lab-solutions/sourcesweep

  python3 sourcesweep.py check
  python3 sourcesweep.py scan --config cfg.json --days 60 --out DIR
  python3 sourcesweep.py show --out DIR S3 S12
  python3 sourcesweep.py render --out DIR [--hub https://claude.ai/...]   # writes DIR/report.html
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import os
from pathlib import Path

__version__ = "1.0.0"
UA_NAME = "sourcesweep"
REPO_URL = "https://github.com/anderes-lab-solutions/sourcesweep"


def contact(cfg):
    """Contact address sent to NCBI and SEC, which ask API users to identify themselves."""
    return cfg.get("email") or os.environ.get("SOURCESWEEP_EMAIL") or "contact@example.com"

HOSTS = {"trials": "https://clinicaltrials.gov/api/v2/studies?pageSize=1",
         "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?retmode=json",
         "preprints": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=test&format=json&pageSize=1",
         "news": "https://news.google.com/rss/search?q=test",
         "eu_trials": "https://euclinicaltrials.eu/ctis-public-api/search",
         "sec": "https://efts.sec.gov/LATEST/search-index?q=%22CDK2%22"}
PRESS_SITES = ["fiercebiotech.com", "endpts.com", "biospace.com", "statnews.com", "biopharmadive.com",
               "globenewswire.com", "businesswire.com", "prnewswire.com"]
ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}
TAG = re.compile(r"<[^>]+>")


def get(url, params=None, data=None, timeout=60, json_body=None, ua=f"{UA_NAME}/{__version__}"):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"User-Agent": ua}
    if json_body is not None:
        body = json.dumps(json_body).encode(); headers["Content-Type"] = "application/json"
    else:
        body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == 2 or (code and code < 500 and code != 429):
                raise
            time.sleep(3 * (attempt + 1))


def normalize_keywords(cfg):
    """A profile is a flat keyword list. Older profiles with targets/drugs/mechanisms are merged into it."""
    out = []
    for k in (cfg.get("keywords") or []) + (cfg.get("targets") or []) + (cfg.get("drugs") or []) + (cfg.get("mechanisms") or []):
        k = str(k).strip()
        if k and k.lower() not in {x.lower() for x in out}:
            out.append(k)
    return out


def q(t):
    return f'"{t}"' if re.search(r"[\s\-/+]", t) else t


def txt(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def clean(s):
    return re.sub(r"\s+", " ", TAG.sub(" ", s or "")).strip()


# ------------------------------------------------------------------ sources

def trials(cfg, start):
    cond = cfg.get("restrict", {}).get("condition")
    kw = cfg["keywords"]
    queries = [{"query.term": " OR ".join(q(x) for x in kw[i:i + 5]), **({"query.cond": cond} if cond else {})}
               for i in range(0, len(kw), 5)]
    out = {}
    for params in queries:
        token = None
        while True:
            p = {**params, "pageSize": 100, "format": "json", **({"pageToken": token} if token else {})}
            data = json.loads(get("https://clinicaltrials.gov/api/v2/studies", p))
            for s in data.get("studies", []):
                ps = s.get("protocolSection", {})
                st, ident, des = ps.get("statusModule", {}), ps.get("identificationModule", {}), ps.get("designModule", {})
                nct, updated = ident.get("nctId"), st.get("lastUpdatePostDateStruct", {}).get("date", "")
                if not nct or not (st.get("overallStatus") in ACTIVE or updated >= start):
                    continue
                out[nct] = {
                    "kind": "trial", "id": nct, "url": f"https://clinicaltrials.gov/study/{nct}",
                    "title": ident.get("briefTitle", nct), "date": updated,
                    "venue": ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", ""),
                    "abstract": (ps.get("descriptionModule", {}).get("briefSummary") or "").strip(),
                    "status": st.get("overallStatus", ""), "phases": des.get("phases", []) or [],
                    "enrollment": des.get("enrollmentInfo", {}).get("count"),
                    "start": st.get("startDateStruct", {}).get("date", ""),
                    "primary_completion": st.get("primaryCompletionDateStruct", {}).get("date", ""),
                    "conditions": ps.get("conditionsModule", {}).get("conditions", []) or [],
                    "interventions": [f"{i.get('type', '')}: {i.get('name', '')}" for i in
                                      ps.get("armsInterventionsModule", {}).get("interventions", []) or []],
                    "endpoints": [o.get("measure", "") for o in ps.get("outcomesModule", {}).get("primaryOutcomes", []) or []],
                }
            token = data.get("nextPageToken")
            if not token:
                break
    return list(out.values())


def pubmed(cfg, days):
    base, email = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", contact(cfg)
    text = cfg.get("restrict", {}).get("text")
    kw = cfg["keywords"]
    queries = ["(" + " OR ".join(f"{q(x)}[tiab]" for x in kw[i:i + 8]) + ")" + (f" AND {q(text)}[tiab]" if text else "")
               for i in range(0, len(kw), 8)]
    ids = []
    for term in queries:
        r = json.loads(get(f"{base}/esearch.fcgi", {"db": "pubmed", "term": term, "reldate": days, "datetype": "edat",
                                                     "retmax": 300, "retmode": "json", "tool": UA_NAME, "email": email}))
        ids += [i for i in r["esearchresult"].get("idlist", []) if i not in ids]
        time.sleep(0.4)
    papers = []
    for i in range(0, len(ids), 100):
        root = ET.fromstring(get(f"{base}/efetch.fcgi", data={"db": "pubmed", "id": ",".join(ids[i:i + 100]),
                                                              "retmode": "xml", "tool": UA_NAME, "email": email}))
        for art in root.iter("PubmedArticle"):
            mc = art.find("MedlineCitation"); a = mc.find("Article"); pmid = txt(mc.find("PMID"))
            abstract = "\n".join((f"{ab.get('Label')}: " if ab.get("Label") else "") + txt(ab) for ab in a.findall("Abstract/AbstractText"))
            au = a.findall("AuthorList/Author")
            first = (txt(au[0].find("LastName")) + " " + txt(au[0].find("Initials"))).strip() if au else ""
            pd = a.find("Journal/JournalIssue/PubDate")
            doi = next((txt(x) for x in art.findall("PubmedData/ArticleIdList/ArticleId") if x.get("IdType") == "doi"), "")
            papers.append({"kind": "paper", "id": pmid, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                           "title": txt(a.find("ArticleTitle")).rstrip("."), "abstract": abstract,
                           "authors": first + (" et al." if len(au) > 1 else ""), "doi": doi,
                           "venue": txt(a.find("Journal/ISOAbbreviation")) or txt(a.find("Journal/Title")),
                           "date": " ".join(x for x in (txt(pd.find("Year")), txt(pd.find("Month"))) if x) if pd is not None else "",
                           "types": [txt(x) for x in a.findall("PublicationTypeList/PublicationType") if txt(x) != "Journal Article"]})
        time.sleep(0.4)
    return papers


def preprints(cfg, start, end):
    terms = cfg["keywords"]
    query = "(" + " OR ".join(f'TITLE:"{x}" OR ABSTRACT:"{x}"' for x in terms) + ")"
    if cfg.get("restrict", {}).get("text"):
        t = cfg["restrict"]["text"]; query += f' AND (TITLE:"{t}" OR ABSTRACT:"{t}")'
    query += f" AND SRC:PPR AND FIRST_PDATE:[{start} TO {end}]"
    out, cursor = [], "*"
    while len(out) < 300:
        d = json.loads(get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                           {"query": query, "format": "json", "resultType": "core", "pageSize": 100, "cursorMark": cursor}))
        res = d.get("resultList", {}).get("result", [])
        for r in res:
            doi, names = r.get("doi", ""), [n for n in r.get("authorString", "").rstrip(".").split(", ") if n]
            out.append({"kind": "preprint", "id": r.get("id", ""), "title": clean(r.get("title", "")).rstrip("."),
                        "abstract": clean(r.get("abstractText", "")), "doi": doi, "date": r.get("firstPublicationDate", ""),
                        "venue": (r.get("bookOrReportDetails") or {}).get("publisher", "Preprint"),
                        "authors": (names[0] + (" et al." if len(names) > 1 else "")) if names else "",
                        "url": f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/PPR/{r.get('id', '')}"})
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor:
            break
        cursor = nxt
    return out


def news(cfg, days):
    terms = cfg["keywords"]
    kws = [k.lower() for k in terms]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items, seen = [], set()
    for i in range(0, len(terms), 5):
        qs = " OR ".join(f'"{x}"' for x in terms[i:i + 5])
        if cfg.get("restrict", {}).get("text"):
            qs = f'({qs}) {cfg["restrict"]["text"]}'
        root = ET.fromstring(get("https://news.google.com/rss/search", {"q": qs, "hl": "en-US", "gl": "US", "ceid": "US:en"}))
        for it in root.iter("item"):
            title = clean(txt(it.find("title")))
            if kws and not any(k in title.lower() for k in kws):
                continue
            try:
                when = parsedate_to_datetime(txt(it.find("pubDate")))
            except (TypeError, ValueError):
                when = None
            if when and when < cutoff:
                continue
            key = news_key(title)
            if key in seen:
                continue
            seen.add(key)
            items.append({"kind": "news", "id": txt(it.find("link")), "url": txt(it.find("link")), "title": title,
                          "venue": txt(it.find("source")), "date": when.strftime("%Y-%m-%d") if when else "", "abstract": ""})
    return items


def eu_trials(cfg, start):
    """EU Clinical Trials Information System (CTIS) public search. Returns every hit; date = last update."""
    terms = cfg["keywords"]
    out, page = [], 1
    while page <= 5:
        d = json.loads(get("https://euclinicaltrials.eu/ctis-public-api/search", json_body={
            "pagination": {"page": page, "size": 100}, "sort": {"property": "decisionDate", "direction": "DESC"},
            "searchCriteria": {"containAny": ", ".join(terms)}}))
        for t in d.get("data", []):
            dmy = lambda s: "-".join(reversed(s.split("/"))) if s and s.count("/") == 2 else (s or "")
            ct = t.get("ctNumber", "")
            out.append({"kind": "eu_trial", "id": ct, "title": clean(t.get("ctTitle", ct)),
                        "url": f"https://euclinicaltrials.eu/search-for-clinical-trials/?lang=en&EUCT={ct}",
                        "date": dmy(t.get("lastUpdated")), "venue": t.get("sponsor", ""),
                        "abstract": clean(t.get("endPoint") or t.get("primaryEndPoint") or ""),
                        "phase": t.get("trialPhase", ""), "decision": dmy(t.get("decisionDateOverall")),
                        "start": dmy(t.get("startDateEU")), "countries": t.get("trialCountries", []) or [],
                        "conditions": [clean(t.get("conditions", ""))], "interventions": [clean(t.get("product") or "")],
                        "status_code": t.get("ctStatus")})
        if not d.get("pagination", {}).get("nextPage"):
            break
        page += 1
    return out


def sec_filings(cfg, start, end):
    """SEC EDGAR full-text search: 8-K, 10-Q, 10-K, S-1 etc. that mention any profile term in the window."""
    ua = f"{UA_NAME} {contact(cfg)}"
    hits = {}
    for term in cfg["keywords"]:
        frm = 0
        while frm < 300:
            d = json.loads(get("https://efts.sec.gov/LATEST/search-index", {
                "q": f'"{term}"', "dateRange": "custom", "startdt": start, "enddt": end, "from": frm}, ua=ua))
            batch = d.get("hits", {}).get("hits", [])
            for h in batch:
                src = h["_source"]; adsh, _, fname = h["_id"].partition(":")
                cik = (src.get("ciks") or ["0"])[0]
                company = re.sub(r"\s+\(CIK.*$", "", (src.get("display_names") or ["?"])[0]).strip()
                company = re.sub(r"\s+", " ", company)
                it = hits.setdefault(h["_id"], {
                    "kind": "sec", "id": h["_id"], "date": src.get("file_date", ""), "venue": company,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fname}",
                    "title": f"{company}: {src.get('form', '')} {src.get('file_description') or src.get('file_type') or ''}".strip(),
                    "form": src.get("form", ""), "terms": []})
                if term not in it["terms"]:
                    it["terms"].append(term)
            frm += len(batch)
            if len(batch) < 100 or frm >= d.get("hits", {}).get("total", {}).get("value", 0):
                break
            time.sleep(0.2)
        time.sleep(0.2)
    latest = {}  # collapse repeat amendments/exhibits of the same company + form, keeping the newest
    for it in sorted(hits.values(), key=lambda x: x["date"], reverse=True):
        desc = re.sub(r"\bNO\.?\s*\d+\b", "", it["title"].split(":", 1)[-1], flags=re.I).split()
        k = (it["venue"], it["form"].replace("/A", ""), desc[-1].upper() if desc else "")
        if k in latest:
            latest[k]["terms"] = sorted(set(latest[k]["terms"]) | set(it["terms"]))
            latest[k].setdefault("also", []).append(it["date"])
        else:
            latest[k] = it
    for it in latest.values():
        terms = it.pop("terms")
        it["abstract"] = "Filing text mentions: " + ", ".join(terms)
        try:  # pull short excerpts around the first mentions so the filing can be screened without opening it
            body = clean(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", get(it["url"], ua=ua, timeout=90).decode("utf-8", "replace")))
            body = body.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
            snips, spans = [], []
            for t in terms:
                for m in re.finditer(re.escape(t), body, re.I):
                    if len(snips) >= 4 or any(abs(m.start() - x) < 500 for x in spans):
                        continue
                    spans.append(m.start()); snips.append("..." + body[max(0, m.start() - 250): m.end() + 350].strip() + "...")
                    break
            if snips:
                it["abstract"] += "\n" + "\n".join(snips)
        except Exception as e:
            it["abstract"] += f" (excerpt unavailable: {type(e).__name__})"
        time.sleep(0.2)
        if it.get("also"):
            it["abstract"] += f" · {len(it['also'])} earlier similar filing(s) in window: " + ", ".join(sorted(it.pop("also")))
    return list(latest.values())


def trade_press(cfg, days):
    """Trade press and press-release wires via a site-restricted Google News search (article text, not just titles)."""
    terms = cfg["keywords"]
    sites = " OR ".join(f"site:{s}" for s in cfg.get("press_sites") or PRESS_SITES)
    items, seen = [], set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for i in range(0, len(terms), 6):
        qs = "(" + " OR ".join(f'"{x}"' for x in terms[i:i + 6]) + f") ({sites}) when:{days}d"
        if cfg.get("restrict", {}).get("text"):
            qs += f' {cfg["restrict"]["text"]}'
        root = ET.fromstring(get("https://news.google.com/rss/search", {"q": qs, "hl": "en-US", "gl": "US", "ceid": "US:en"}))
        for it in root.iter("item"):
            title = clean(txt(it.find("title")))
            key = news_key(title)
            if key in seen:
                continue
            seen.add(key)
            try:
                dt = parsedate_to_datetime(txt(it.find("pubDate")))
            except (TypeError, ValueError):
                dt = None
            if dt is None or dt < cutoff:  # Google ignores when: alongside site: filters, so enforce the window here
                continue
            when = dt.strftime("%Y-%m-%d")
            items.append({"kind": "press", "id": txt(it.find("link")), "url": txt(it.find("link")), "title": title,
                          "venue": txt(it.find("source")), "date": when, "abstract": ""})
        time.sleep(0.5)
    return items


def news_key(title):
    return re.sub(r"\W+", " ", re.sub(r"\s+-\s+[^-]+$", "", title).lower()).strip()


# ------------------------------------------------------------------ matching & output

def matched(cfg, item):
    text = " ".join([item["title"], item.get("abstract", "")] + item.get("conditions", []) + item.get("interventions", []))
    hit = lambda t: re.search(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", text, re.I)
    return [t for t in cfg["keywords"] if hit(t)]


def label(item):
    fallback = {"trial": "(registry fields)", "eu_trial": "(registry fields)", "press": "(in article text)"}
    return ", ".join(item["matched"]) or fallback.get(item["kind"], "(none in text)")


def write(cfg, items, status, start, end, out):
    out.mkdir(parents=True, exist_ok=True)
    kind_order = {"trial": 0, "eu_trial": 1, "paper": 2, "preprint": 3, "sec": 4, "press": 5, "news": 6}
    items.sort(key=lambda i: (kind_order[i["kind"]], -len(i["matched"]), i["title"]))
    for n, it in enumerate(items, 1):
        it["sid"] = f"S{n}"
    head = f"{cfg['name']} · {start} to {end}"
    idx = [f"# Index: {head}", f"Source status: {status}", "",
           "| ID | Type | Date | Matched terms | Title | Sponsor/venue |", "|---|---|---|---|---|---|"]
    for i in items:
        extra = (f" [{', '.join(i['phases'])} · {i['status']}]" if i["kind"] == "trial"
                 else f" [{i['phase']}]" if i["kind"] == "eu_trial" else "")
        idx.append(f"| {i['sid']} | {i['kind']} | {i['date']} | {label(i)} | {i['title'].replace('|', '/')}{extra} | {i.get('venue', '')} |")
    (out / "index.md").write_text("\n".join(idx) + "\n")
    L = [f"# Source pack: {cfg['name']}", f"Window: {start} to {end} · generated {date.today()}", "",
         "## How to use this file",
         "Pre-screened US/EU clinical trials, papers, preprints, SEC filings, trade press and news with abstracts and links. Answer only from these "
         "sources and cite IDs like [S12]. Abstracts belong to their publishers; follow links for full text.", "",
         "## Scope", cfg.get("context", ""), "", f"## Sources ({len(items)})"]
    for i in items:
        L += ["", f"### [{i['sid']}] {i['title']}",
              f"- Type: {i['kind']}" + "".join(f" · {x}" for x in (i.get("venue"), i.get("date"), i.get("authors")) if x),
              f"- Link: {i['url']}" + (f" · DOI: {i['doi']}" if i.get("doi") else ""), f"- Matched terms: {label(i)}"]
        if i["kind"] == "trial":
            L += [f"- Trial: {i['id']} · {', '.join(i['phases']) or 'phase n/a'} · {i['status']} · n={i['enrollment'] or '?'} · "
                  f"start {i['start'] or '?'} · primary completion {i['primary_completion'] or '?'}",
                  f"- Conditions: {'; '.join(i['conditions'])}", f"- Interventions: {'; '.join(i['interventions'])}",
                  f"- Primary endpoints: {'; '.join(i['endpoints'])}"]
        if i["kind"] == "eu_trial":
            L += [f"- EU trial: {i['id']} · {i['phase'] or 'phase n/a'} · CTIS status code {i['status_code']} · "
                  f"decision {i['decision'] or '?'} · EU start {i['start'] or '?'} · last updated {i['date'] or '?'}",
                  f"- Countries: {', '.join(i['countries'])}", f"- Conditions: {'; '.join(i['conditions'])}",
                  f"- Product: {'; '.join(i['interventions'])}"]
        if i.get("abstract"):
            L += ["", "> " + i["abstract"].strip().replace("\n", "\n> ")]
    (out / "sources.md").write_text("\n".join(L) + "\n")
    (out / "sources.json").write_text(json.dumps({"config": cfg, "window": [start, end], "status": status,
                                                  "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items}, indent=1))


# ------------------------------------------------------------------ HTML report

def md_inline(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    def cite(m):
        ids = re.findall(r"S\d+(?:\s*[–-]\s*S?\d+)?", m.group(1))
        out = []
        for x in ids:
            r = re.match(r"S(\d+)\s*[–-]\s*S?(\d+)", x)
            out += [f"S{n}" for n in range(int(r.group(1)), int(r.group(2)) + 1)] if r else [x]
        return '<span class="cites">' + "".join(f'<a class="cite" href="#{x}" data-s="{x}">{x}</a>' for x in out) + "</span>"
    return re.sub(r"\[(S\d+(?:\s*[–-]\s*S?\d+)?(?:,\s*S\d+(?:\s*[–-]\s*S?\d+)?)*)\]", cite, s)


def table_csv_rows(head, body, urls):
    """Plain rows for CSV export: citations moved to a Sources column, Last mention split into date / source / link."""
    strip = lambda c: re.sub(r"\s*\[(S\d+[^\]]*)\]", "", c).replace("**", "").strip()
    lm = next((n for n, h in enumerate(head) if h.strip().lower() == "last mention"), None)
    cols = [h for n, h in enumerate(head) if n != lm] + ["Sources", "Source links"]
    if lm is not None:
        cols += ["Last mention date", "Last mention source", "Last mention link"]
    out = [cols]
    for r in body:
        r = r + [""] * (len(head) - len(r))
        ids = list(dict.fromkeys(cited_ids(" ".join(c for n, c in enumerate(r) if n != lm))))
        row = [strip(c) for n, c in enumerate(r) if n != lm] + ["; ".join(ids), " ".join(urls.get(i, "") for i in ids).strip()]
        if lm is not None:
            m = re.match(r"\s*(\S+)\s*\[(S\d+)\]", r[lm])
            row += [m.group(1), m.group(2), urls.get(m.group(2), "")] if m else ["", "", ""]
        out.append(row)
    return out


def md_to_html(md, urls=None, tables=None):
    """Small Markdown subset for briefings: headings, paragraphs, bullet and numbered lists, bold, [S#] citations.
    Stops at '## Screened sources', which the report shows as its interactive source list instead."""
    html, para, lst, tbl = [], [], None, []
    def flush_table():
        nonlocal tbl
        rows = [r for r in tbl if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
        if rows:
            head, body = rows[0], rows[1:]
            if tables is not None:
                tables.append(table_csv_rows(head, body, urls or {}))
                n = len(tables) - 1
                html.append(f'<div class="tbar"><button type="button" class="tbtn" data-csv="{n}">Download CSV</button>'
                            f'<button type="button" class="tbtn" data-copycsv="{n}">Copy CSV</button></div>')
            html.append('<div class="scroll"><table class="stack"><thead><tr>' + "".join(f"<th>{md_inline(h)}</th>" for h in head) +
                        "</tr></thead><tbody>" + "".join("<tr>" + "".join(
                            f'<td data-l="{md_inline(head[n]) if n < len(head) else ""}">{md_inline(c)}</td>' for n, c in enumerate(r)) + "</tr>" for r in body) +
                        "</tbody></table></div>")
        tbl = []
    def flush():
        nonlocal para, lst
        if tbl:
            flush_table()
        if para:
            html.append("<p>" + md_inline(" ".join(para)) + "</p>"); para = []
        if lst:
            html.append(f"</{lst}>"); lst = None
    for line in md.splitlines():
        t = line.strip()
        if re.match(r"^#{1,3}\s+screened sources", t, re.I):
            break
        if not t:
            flush(); continue
        h = re.match(r"^(#{1,3})\s+(.*)", t)
        if h:
            flush()
            if len(h.group(1)) > 1:
                html.append(f"<h{len(h.group(1)) + 1}>{md_inline(h.group(2))}</h{len(h.group(1)) + 1}>")
            continue
        b = re.match(r"^([-*]|\d+\.)\s+(.*)", t)
        if b:
            kind = "ol" if b.group(1)[0].isdigit() else "ul"
            if para:
                html.append("<p>" + md_inline(" ".join(para)) + "</p>"); para = []
            if lst != kind:
                if lst:
                    html.append(f"</{lst}>")
                html.append(f"<{kind}>"); lst = kind
            html.append("<li>" + md_inline(b.group(2)) + "</li>"); continue
        if t.startswith("|"):
            if lst or para:
                flush()
            tbl.append([c.strip() for c in t.strip("|").split("|")]); continue
        if tbl:
            flush_table()
        if re.match(r"^(window|source status):", t, re.I):
            continue
        if lst:
            html.append(f"</{lst}>"); lst = None
        para.append(t)
    flush()
    return "\n".join(html)


def screening_from_briefing(md):
    """Fallback when screening.json is missing: read ID / Rel. / Note from the briefing's screened-sources table."""
    scr, cols = {}, None
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols is None and "ID" in cells:
            cols = {c.lower().rstrip("."): n for n, c in enumerate(cells)}; continue
        if cols and re.match(r"^S\d+$", cells[0]):
            rel = cells[cols["rel"]] if "rel" in cols and cols["rel"] < len(cells) else ""
            note = cells[cols["note"]] if "note" in cols and cols["note"] < len(cells) else ""
            scr[cells[0]] = {"rel": int(rel) if rel.isdigit() else None, "note": note}
    return scr


def norm_date(d):
    """'2026-11-20' stays; '2026 Nov' becomes '2026-11'; '2026' stays. Sorts as text."""
    d = (d or "").strip()
    m = re.match(r"^(\d{4})\s+([A-Za-z]{3})", d)
    if m:
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        return f"{m.group(1)}-{mon.index(m.group(2).lower()) + 1:02d}" if m.group(2).lower() in mon else m.group(1)
    return d[:10]


def cited_ids(text):
    out = []
    for grp in re.findall(r"\[(S\d+(?:\s*[–-]\s*S?\d+)?(?:,\s*S\d+(?:\s*[–-]\s*S?\d+)?)*)\]", text):
        for x in re.findall(r"S\d+(?:\s*[–-]\s*S?\d+)?", grp):
            r = re.match(r"S(\d+)\s*[–-]\s*S?(\d+)", x)
            out += [f"S{n}" for n in range(int(r.group(1)), int(r.group(2)) + 1)] if r else [x]
    return out


def fill_last_mention(md, items):
    """In any briefing table with a 'Last mention' column, write the date and ID of the newest source the row cites."""
    dates = {i["sid"]: norm_date(i.get("date", "")) for i in items}
    lines, col = md.splitlines(), None
    for n, line in enumerate(lines):
        t = line.strip()
        if not t.startswith("|"):
            col = None; continue
        cells = [c.strip() for c in t.strip("|").split("|")]
        if col is None:
            low = [c.lower() for c in cells]
            col = low.index("last mention") if "last mention" in low else -1
            continue
        if col < 0 or all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        ids = [x for x in cited_ids(" ".join(c for k, c in enumerate(cells) if k != col)) if dates.get(x)]
        if ids:
            best = max(ids, key=lambda x: (dates[x], -int(x[1:])))
            while len(cells) <= col:
                cells.append("")
            cells[col] = f"{dates[best]} [{best}]"
            lines[n] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if md.endswith("\n") else "")


def render(out, hub="", title="", abstracts=True):
    """Write out/report.html. abstracts=False leaves publisher abstracts out, e.g. for a page posted publicly."""
    data = json.loads((out / "sources.json").read_text())
    cfg, items = data["config"], data["items"]
    cfg["keywords"] = normalize_keywords(cfg)
    for i in items:  # scans made before profiles became flat keyword lists stored matches by group
        if isinstance(i.get("matched"), dict):
            i["matched"] = [t for g in ("targets", "drugs", "mechanisms") for t in i["matched"].get(g, [])]
    brief = (out / "briefing.md").read_text() if (out / "briefing.md").exists() else ""
    if brief:
        filled = fill_last_mention(brief, items)
        if filled != brief:
            (out / "briefing.md").write_text(filled); brief = filled
    scr = json.loads((out / "screening.json").read_text()) if (out / "screening.json").exists() else screening_from_briefing(brief)
    rows = []
    for i in items:
        sc = scr.get(i["sid"], {})
        rel = sc.get("rel")
        meta = ""
        if i["kind"] == "trial":
            meta = f"{i['id']} · {', '.join(i['phases']) or 'phase n/a'} · {i['status'].replace('_', ' ').lower()} · n={i['enrollment'] or '?'}"
        elif i["kind"] == "eu_trial":
            meta = f"{i['id']} · {i['phase']}"
        elif i.get("authors"):
            meta = i["authors"]
        rows.append({"s": i["sid"], "k": i["kind"], "d": i.get("date", ""), "t": i["title"], "u": i["url"],
                     "v": i.get("venue", ""), "m": label(i), "r": rel if rel is not None else (0 if scr else None),
                     "n": sc.get("note", ""), "a": i.get("abstract", "")[:6000] if abstracts else "", "x": meta})
    payload = {"name": cfg.get("name", "Landscape scan"), "window": data["window"], "status": data["status"],
               "keywords": cfg["keywords"], "hub": hub if hub.startswith("https://") else "", "rows": rows,
               "screened": bool(scr), "generated": date.today().isoformat(), "repo": REPO_URL,
               "ran_at": data.get("generated_at") or datetime.fromtimestamp((out / "sources.json").stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
               "days": (date.fromisoformat(data["window"][1]) - date.fromisoformat(data["window"][0])).days}
    page = REPORT_HTML.replace("<title>__TITLE__ report</title>", "<title>" + md_inline(title or cfg.get("name", "Landscape scan") + " report") + "</title>")
    page = page.replace("__TITLE__", md_inline(cfg.get("name", "Landscape scan")))
    tables = []
    brief_html = md_to_html(brief, {i["sid"]: i["url"] for i in items}, tables) if brief else "<p class=quiet>No briefing was written for this scan.</p>"
    payload["tables"] = tables
    payload["slug"] = cfg.get("slug") or re.sub(r"[^a-z0-9]+", "-", cfg.get("name", "scan").lower()).strip("-")
    page = page.replace("__BRIEF__", brief_html)
    page = page.replace("__DATA__", json.dumps(payload).replace("<", "\\u003c"))
    (out / "report.html").write_text(page)
    return out / "report.html"


REPORT_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ report</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@300;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* VOICE work: an analyst's desk brief, dense and calm
   IDEA a night-desk wire monitor: findings up top, every source one row on the tape
   PICTURE the source tape: one stacked bar per source type, coloured by relevance
   COLOUR plum-black ground, white ink, rose for directly relevant, dusk for context
   TYPE Inter Tight 300 large titles + Inter text
   LAYOUT title and key figures, tape full width, briefing, then filterable source list */
:root{color-scheme:dark;--bg:#1a0f1f;--panel:#24162b;--line:#3a2843;--ink:#f6f0f7;--mute:#bfaec6;--rose:#ff8fa3;--dusk:#8f7aa8;--faint:#4a3654}
*{box-sizing:border-box;min-width:0}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font:16px/1.55 Inter,system-ui,sans-serif;overflow-x:clip}
a{color:var(--rose)}
.band{padding:clamp(24px,4vw,56px) max(5vw,16px)}
.wrap{max-width:1240px;margin:0 auto}
h1{font:300 clamp(32px,5vw,52px)/1.05 "Inter Tight",Inter,sans-serif;letter-spacing:-.02em;margin:0 0 10px;text-wrap:balance}
h2,h3{font:600 22px/1.2 "Inter Tight",Inter,sans-serif;margin:28px 0 10px}
h4{font:600 17px/1.3 Inter,sans-serif;margin:20px 0 6px}
.sub{color:var(--mute);margin:0}
.kw{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 0;padding:0;list-style:none}
.kw li{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--mute)}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(9em,1fr));gap:12px;margin:26px 0 8px}
.fig b{display:block;font:300 clamp(30px,4vw,44px)/1 "Inter Tight",sans-serif}
.fig span{color:var(--mute);font-size:14px}
.tape{margin-top:22px;display:grid;gap:8px}
.tr{display:grid;grid-template-columns:7.5em minmax(0,1fr) 3em;gap:12px;align-items:center;font-size:14px}
.tr button{all:unset;cursor:pointer;color:var(--mute);border-radius:4px}
.tr button:hover,.tr button:focus-visible{color:var(--ink);outline:2px solid var(--dusk);outline-offset:2px}
.bar{display:flex;height:18px;border-radius:3px;overflow:hidden;background:var(--faint)}
.bar i{display:block;height:100%}
.r3{background:var(--rose)}.r2{background:var(--dusk)}.r1{background:#6b5577}.r0{background:var(--faint)}
.tr .c{text-align:right;font-variant-numeric:tabular-nums}
.key{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:13px;color:var(--mute)}
.key i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.light{background:#fff;color:#1a0f1f;--ink:#1a0f1f;--mute:#5e4f66;--line:#e4dbe8;--faint:#d6cadb;--dusk:#8f7aa8;color-scheme:light}
.light a{color:#b8325a}
.brief{border-top:1px solid var(--line)}
.brief .wrap{max-width:1040px}
.brief p,.brief li{color:var(--ink);max-width:72ch}
.brief table{width:100%;border-collapse:collapse;font-size:15px;margin:6px 0 10px}
.brief th{text-align:left;font-weight:600;color:var(--mute);font-size:13px;border-bottom:2px solid var(--ink);padding:8px 10px 6px;vertical-align:bottom}
.brief td{border-bottom:1px solid var(--line);padding:10px;vertical-align:top}
.brief td:first-child{font-weight:600}
.brief td:last-child{white-space:nowrap}
.scroll{overflow-x:auto}
.tbar{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 8px}
.tbtn{font:500 14px Inter,sans-serif;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:6px;min-height:36px;padding:0 12px;cursor:pointer}
.tbtn:hover{border-color:var(--mute)}
.tbtn:focus-visible{outline:2px solid var(--rose);outline-offset:2px}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#1a0f1f;color:#fff;padding:10px 16px;border-radius:8px;font:500 15px Inter,sans-serif;opacity:0;pointer-events:none;transition:opacity .2s;max-width:calc(100% - 32px);z-index:5}
.toast.on{opacity:1}
.brief li{margin:6px 0}
.cites{white-space:nowrap}
.cite{display:inline-block;font-size:12px;font-weight:600;text-decoration:none;color:#1a0f1f;background:var(--rose);border-radius:4px;padding:0 5px;margin-left:3px;line-height:18px}
.cite:hover,.cite:focus-visible{background:#1a0f1f;color:#fff;outline:none}
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:4px 0 18px}
.tools input{flex:1 1 220px;font:16px Inter,sans-serif;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px 12px;min-height:44px}
.tools input:focus-visible,.chip:focus-visible,select:focus-visible{outline:2px solid var(--rose);outline-offset:2px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:500 14px Inter,sans-serif;color:var(--mute);background:transparent;border:1px solid var(--line);border-radius:999px;padding:8px 14px;min-height:40px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
select{font:15px Inter,sans-serif;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:9px 10px;min-height:44px}
.count{color:var(--mute);font-size:14px;margin:0 0 10px}
.src{border-top:1px solid var(--line);padding:14px 0;display:grid;grid-template-columns:9em minmax(0,1fr);gap:4px 14px;scroll-margin-top:20px}
.src:target{background:linear-gradient(90deg,#ff8fa322,transparent)}
.sid{font:600 14px Inter,sans-serif;color:var(--mute)}
.sid em{display:block;font-style:normal;font-weight:500;font-size:12px;margin-top:4px;padding:1px 6px;border-radius:3px;width:max-content}
.t{font-weight:600;font-size:16px;text-decoration:none;color:var(--ink)}
.t:hover,.t:focus-visible{color:var(--rose);text-decoration:underline}
.t::after{content:" ↗";color:var(--mute);font-weight:400}
.meta{color:var(--mute);font-size:14px;margin-top:2px}
.note{margin-top:6px;font-size:15px}
.mt{font-size:13px;color:var(--mute);margin-top:4px}
details{margin-top:6px}
summary{cursor:pointer;color:var(--mute);font-size:14px;min-height:28px}
details p{white-space:pre-wrap;font-size:14px;color:#ddd0e2;margin:6px 0 0;overflow-wrap:anywhere}
.quiet{color:var(--mute)}
footer{color:var(--mute);font-size:13px}
@media(max-width:600px){.brief table{font-size:14px}.stack thead{display:none}.stack tr{display:grid;padding-block:10px;border-bottom:1px solid var(--line)}.stack td{display:block;position:relative;border:0;padding:2px 0 2px 7.5em;white-space:normal!important}.stack td::before{content:attr(data-l);position:absolute;left:0;width:7em;color:var(--mute);font-weight:500}.tr{grid-template-columns:6em minmax(0,1fr) 2.5em}.src{grid-template-columns:minmax(0,1fr)}.sid{display:flex;gap:8px;align-items:center}.sid em{margin:0}}
@media(prefers-reduced-motion:no-preference){.bar i{transition:flex-grow .4s}}
</style></head><body>
<div class="light">
<header class="band"><div class="wrap">
<h1 id="title">__TITLE__</h1>
<p class="sub" id="window"></p>
<ul class="kw" id="kw" aria-label="Keywords searched"></ul>
<div class="figs" id="figs"></div>
<div class="tape" id="tape" aria-label="Sources by type and relevance"></div>
<div class="key" id="key"></div>
</div></header>
<section class="band brief"><div class="wrap">
<h2 style="margin-top:0">Briefing</h2>
__BRIEF__
</div></section>
</div>
<section class="band"><div class="wrap">
<h2 style="margin-top:0">Sources</h2>
<div class="tools">
<input id="q" type="search" placeholder="Search titles, companies, notes, abstracts" aria-label="Search sources">
<select id="rel" aria-label="Relevance"><option value="2">Relevant (2–3)</option><option value="3">Directly relevant (3)</option><option value="0">All sources</option></select>
<select id="sort" aria-label="Sort"><option value="id">By source ID</option><option value="date">Newest first</option><option value="rel">Most relevant first</option></select>
</div>
<div class="chips" id="types" role="group" aria-label="Source types"></div>
<p class="count" id="count"></p>
<div id="list"></div>
</div></section>
<footer class="band"><div class="wrap" id="foot"></div></footer>
<div class="toast" id="toast" role="status"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
{
const D = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safe = u => /^https:\/\//.test(u || "") ? u : "";
const KIND = {trial:"US trial", eu_trial:"EU trial", paper:"Paper", preprint:"Preprint", sec:"SEC filing", press:"Trade press", news:"News"};
const REL = {3:"Directly relevant", 2:"Context", 1:"Tangential", 0:"Off-topic"};
const kinds = Object.keys(KIND).filter(k => D.rows.some(r => r.k === k));
const rows = D.rows;
const st = {types:new Set(kinds), q:"", rel:D.screened ? 2 : 0, sort:"id"};
try { const saved = JSON.parse(localStorage.getItem("lw-filter") || "null"); if (saved) { st.rel = saved.rel ?? st.rel; st.sort = saved.sort || st.sort; } } catch (e) {}
document.getElementById("rel").value = String(st.rel);
document.getElementById("sort").value = st.sort;
if (!D.screened) document.getElementById("rel").disabled = true;

const when = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}); };
document.getElementById("window").textContent = `Scan window ${D.window[0]} to ${D.window[1]} (${D.days} days) · ${rows.length} sources` + (when(D.ran_at) ? ` · run ${when(D.ran_at)}` : "");
document.getElementById("kw").innerHTML = D.keywords.map(k => `<li>${esc(k)}</li>`).join("");
const n3 = rows.filter(r => r.r === 3).length, n2 = rows.filter(r => r.r === 2).length;
const failed = Object.entries(D.status).filter(([k, v]) => !/^ok|^skipped/.test(v)).map(([k]) => k);
const figs = [[rows.length, "sources screened"], [n3, "directly relevant"], [n2, "context"], [kinds.length, "source types" + (failed.length ? ` (${failed.join(", ")} failed)` : "")]];
document.getElementById("figs").innerHTML = figs.map(([v, l]) => `<div class="fig"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join("");

const max = Math.max(1, ...kinds.map(k => rows.filter(r => r.k === k).length));
document.getElementById("tape").innerHTML = kinds.map(k => {
  const rs = rows.filter(r => r.k === k);
  const seg = [3, 2, 1, 0].map(v => [v, rs.filter(r => (r.r ?? 0) === v).length]).filter(([, c]) => c);
  return `<div class="tr"><button type="button" data-only="${k}" title="Show only ${KIND[k]}">${KIND[k]}</button>
    <div class="bar" style="width:${(rs.length / max * 100).toFixed(1)}%">${seg.map(([v, c]) => `<i class="r${v}" style="flex-grow:${c}" title="${c} ${REL[v].toLowerCase()}"></i>`).join("")}</div>
    <span class="c">${rs.length}</span></div>`;
}).join("");
document.getElementById("key").innerHTML = D.screened ? [3, 2, 1].map(v => `<span><i class="r${v}"></i>${REL[v]}</span>`).join("") + `<span><i class="r0"></i>Off-topic</span>` : `<span>Not yet screened for relevance</span>`;

const tchips = document.getElementById("types");
tchips.innerHTML = kinds.map(k => `<button type="button" class="chip" data-k="${k}" aria-pressed="true">${KIND[k]}</button>`).join("");

function card(r) {
  const u = safe(r.u), relTag = r.r != null && D.screened ? `<em class="r${r.r}" style="color:${r.r >= 2 ? "var(--bg)" : "var(--ink)"}">${REL[r.r]}</em>` : "";
  const title = u ? `<a class="t" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(r.t)}</a>` : `<span class="t">${esc(r.t)}</span>`;
  const meta = [KIND[r.k], r.v, r.d, r.x].filter(Boolean).map(esc).join(" · ");
  return `<article class="src" id="${esc(r.s)}"><div class="sid">${esc(r.s)}${relTag}</div><div>${title}
    <div class="meta">${meta}</div>${r.n ? `<div class="note">${esc(r.n)}</div>` : ""}
    <div class="mt">Matched: ${esc(r.m)}</div>${r.a ? `<details><summary>${r.k === "sec" ? "Filing excerpts" : r.k.includes("trial") ? "Summary" : "Abstract"}</summary><p>${esc(r.a)}</p></details>` : ""}</div></article>`;
}

function draw() {
  const q = st.q.toLowerCase();
  let list = rows.filter(r => st.types.has(r.k) && (st.rel === 0 || (r.r ?? 0) >= st.rel) &&
    (!q || [r.t, r.v, r.n, r.a, r.m, r.s].join(" ").toLowerCase().includes(q)));
  const num = s => +s.slice(1);
  if (st.sort === "date") list = list.slice().sort((a, b) => (b.d || "").localeCompare(a.d || "") || num(a.s) - num(b.s));
  if (st.sort === "rel") list = list.slice().sort((a, b) => (b.r ?? 0) - (a.r ?? 0) || num(a.s) - num(b.s));
  document.getElementById("count").textContent = `Showing ${list.length} of ${rows.length} sources`;
  document.getElementById("list").innerHTML = list.length ? list.map(card).join("") : `<p class="quiet">No sources match these filters.</p>`;
  for (const b of tchips.querySelectorAll(".chip")) b.setAttribute("aria-pressed", String(st.types.has(b.dataset.k)));
  try { localStorage.setItem("lw-filter", JSON.stringify({rel: st.rel, sort: st.sort})); } catch (e) {}
}

function reveal(id) {
  const r = rows.find(x => x.s === id);
  if (!r) return;
  if (!document.getElementById(id)) { st.types.add(r.k); st.rel = 0; st.q = ""; document.getElementById("q").value = ""; document.getElementById("rel").value = "0"; draw(); }
  const el = document.getElementById(id);
  if (el) { el.scrollIntoView({block:"start"}); const d = el.querySelector("details"); if (d) d.open = true; }
}

tchips.addEventListener("click", e => { const b = e.target.closest(".chip"); if (!b) return;
  st.types.has(b.dataset.k) && st.types.size > 1 ? st.types.delete(b.dataset.k) : st.types.add(b.dataset.k); draw(); });
document.getElementById("tape").addEventListener("click", e => { const b = e.target.closest("[data-only]"); if (!b) return;
  st.types = new Set([b.dataset.only]); draw(); document.getElementById("types").scrollIntoView({block:"start"}); });
document.getElementById("q").addEventListener("input", e => { st.q = e.target.value; draw(); });
document.getElementById("rel").addEventListener("change", e => { st.rel = +e.target.value; draw(); });
document.getElementById("sort").addEventListener("change", e => { st.sort = e.target.value; draw(); });
document.addEventListener("click", e => { const a = e.target.closest("a.cite"); if (!a) return; e.preventDefault(); reveal(a.dataset.s); try { history.replaceState(null, "", "#" + a.dataset.s); } catch (err) {} });
window.addEventListener("hashchange", () => reveal(location.hash.slice(1)));

document.getElementById("foot").innerHTML = `Scan run ${esc(when(D.ran_at) || D.generated)} by <a href="${esc(D.repo)}">SourceSweep™</a>, built by Tegan Anderes / Anderes Lab Solutions. Source status: ${Object.entries(D.status).map(([k, v]) => esc(k + " " + v)).join(" · ")}.` +
  (safe(D.hub) ? ` <a href="${esc(D.hub)}">Edit profiles and see past scans</a>.` : "");
const toCSV = t => t.map(r => r.map(c => /[",\n]/.test(String(c)) ? `"${String(c).replace(/"/g, '""')}"` : String(c)).join(",")).join("\r\n") + "\r\n";
const toast = m => { const t = document.getElementById("toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("on"), 2400); };
let dl = null;
(async () => { try { dl = await window.claude?.use?.("downloads"); } catch (e) { dl = null; } })();
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-csv],[data-copycsv]"); if (!b) return;
  const n = +(b.dataset.csv ?? b.dataset.copycsv), csv = toCSV(D.tables[n] || []);
  const name = `${D.slug || "landscape"}_assets_${D.window[1]}.csv`;
  if (b.dataset.copycsv !== undefined) {
    try { await navigator.clipboard.writeText(csv); toast("CSV copied. Paste it into Excel or Google Sheets"); } catch (err) { toast("Copying isn't allowed here. Use Download CSV"); }
    return;
  }
  if (dl) {
    try { await dl.save({filename: name, data: "\ufeff" + csv}); toast("CSV saved"); }
    catch (err) { if (err?.code !== "declined") toast("Download isn't available here. Use Copy CSV"); }
    return;
  }
  try {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["\ufeff" + csv], {type: "text/csv"})); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  } catch (err) { toast("Download isn't available here. Use Copy CSV"); }
});
draw();
if (/^#S\d+$/.test(location.hash)) reveal(location.hash.slice(1));
}
</script></body></html>
"""



def scan(cfg, days, out, log=None):
    """Search every source for cfg["keywords"] over the last `days` days and write index.md,
    sources.md and sources.json to `out`. Returns a summary dict. A failing source is recorded, not raised."""
    log = log or (lambda m: print(m, file=sys.stderr))
    cfg = dict(cfg); cfg["keywords"] = normalize_keywords(cfg)
    if not cfg["keywords"]:
        raise ValueError("config has no keywords")
    end = date.today().isoformat(); start = (date.today() - timedelta(days=days)).isoformat()
    items, status = [], {}
    sources = {"trials": lambda: trials(cfg, start), "eu_trials": lambda: eu_trials(cfg, start),
               "pubmed": lambda: pubmed(cfg, days), "preprints": lambda: preprints(cfg, start, end),
               "sec": lambda: sec_filings(cfg, start, end), "press": lambda: trade_press(cfg, days),
               "news": lambda: news(cfg, days)}
    skip = set(cfg.get("skip_sources") or [])
    for name, fn in sources.items():
        if name in skip:
            status[name] = "skipped"; continue
        try:
            got = fn(); items += got; status[name] = f"ok ({len(got)})"
        except Exception as e:
            status[name] = f"FAILED: {type(e).__name__}: {str(e)[:120]}"
        log(f"{name}: {status[name]}")
    press_keys = {news_key(i["title"]) for i in items if i["kind"] == "press"}
    items = [i for i in items if not (i["kind"] == "news" and news_key(i["title"]) in press_keys)]
    for it in items:
        it["matched"] = matched(cfg, it)
    write(cfg, items, status, start, end, Path(out))
    return {"out": str(out), "window": [start, end], "status": status, "total": len(items),
            "with_keyword_in_text": sum(1 for i in items if i["matched"])}

def main(argv=None):
    ap = argparse.ArgumentParser(prog="sourcesweep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("scan"); s.add_argument("--config", required=True); s.add_argument("--days", type=int, default=60)
    s.add_argument("--out", required=True)
    sh = sub.add_parser("show"); sh.add_argument("--out", required=True); sh.add_argument("ids", nargs="+")
    rd = sub.add_parser("render"); rd.add_argument("--out", required=True); rd.add_argument("--hub", default=""); rd.add_argument("--title", default="")
    rd.add_argument("--no-abstracts", action="store_true", help="leave publisher abstracts out of the page")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        res = {}
        for name, url in HOSTS.items():
            try:
                if name == "eu_trials":
                    get(url, timeout=20, json_body={"pagination": {"page": 1, "size": 1}, "searchCriteria": {"containAll": "cancer"}})
                else:
                    get(url, timeout=20, ua=f"{UA_NAME} check@example.com")
                res[name] = "ok"
            except Exception as e:
                res[name] = f"BLOCKED ({type(e).__name__}: {str(e)[:80]})"
        print(json.dumps(res, indent=1))
        sys.exit(0 if all(v == "ok" for v in res.values()) else 1)

    if a.cmd == "show":
        want = {x.strip(",").upper() for x in a.ids}
        text = (Path(a.out) / "sources.md").read_text()
        for block in text.split("\n### ")[1:]:
            if block.split("]")[0].lstrip("[") in want:
                print("### " + block.strip() + "\n")
        return

    if a.cmd == "render":
        print(render(Path(a.out), a.hub, a.title, abstracts=not a.no_abstracts)); return

    cfg = json.loads(Path(a.config).read_text())
    print(json.dumps(scan(cfg, a.days, Path(a.out)), indent=1))


if __name__ == "__main__":
    main()