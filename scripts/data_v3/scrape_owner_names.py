"""
Async scraper: visits each yarn-store website (derived from email domain) and
tries to extract the owner / founder first+last name from the About / Contact
page. Writes results back into the CSV.

Run:
    python scripts/data_v3/scrape_owner_names.py \
        Data/Data_v3/04_yarn_stores_international.csv

Idempotent: only fills rows where first_name is currently blank.
"""
from __future__ import annotations

import asyncio
import csv
import re
import sys
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "Data/Data_v3/04_yarn_stores_international.csv"
)

CONCURRENCY = 20
PER_REQUEST_TIMEOUT = 8
USER_AGENT = (
    "Mozilla/5.0 (compatible; HF-Outreach-Bot/1.0; "
    "+research enrichment for B2B outreach)"
)

ABOUT_PATHS = [
    "/pages/about-us",
    "/pages/about",
    "/pages/our-story",
    "/pages/meet-the-team",
    "/pages/meet",
    "/about-us/",
    "/about/",
    "/about-us",
    "/about",
    "/aboutus",
    "/about_us",
    "/our-story",
    "/story",
    "/meet-the-team",
    "/team",
    "/staff",
    "/owner",
    "/contact-us/",
    "/contact/",
    "/contact",
    "/contact-us",
    "/",
]

FREE_MAIL = {
    "gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com",
    "icloud.com", "me.com", "comcast.net", "sbcglobal.net", "att.net",
    "verizon.net", "cox.net", "charter.net", "msn.com", "live.com", "mac.com",
    "earthlink.net", "mtaonline.net", "gci.net", "arctic.net", "ymail.com",
    "rocketmail.com", "mindspring.com", "bellsouth.net", "optonline.net",
    "frontier.com", "windstream.net", "centurylink.net", "mchsi.com",
    "embarqmail.com", "rediffmail.com", "aim.com", "fastmail.com", "pm.me",
    "protonmail.com", "prodigy.net", "frontiernet.net", "myfairpoint.net",
    "wowway.com", "roadrunner.com", "rr.com", "twc.com", "googlemail.com",
    "duck.com", "duckmail.com", "pacbell.net", "yahoo.co.uk", "yahoo.ca",
    "example.com", "email.com",
}

GENERIC_LOCALS = {
    "info", "contact", "hello", "sales", "support", "shop", "customer",
    "service", "store", "office", "admin", "webmaster", "mail", "email",
    "help", "team", "orders", "inquiries",
}

# Compact common-first-name set (subset of standard US/UK first names)
COMMON_FIRSTS = set(
    """anna annie sandy sarah sara sue susan susie mary amy emma emily kate
katie katherine kathy jane janet jan julie lisa linda laura leslie kim
kimberly carol carolyn christine christina chris cheryl cathy catherine
cindy claire clare debbie deb deborah debra diane donna dorothy ellen elaine
elizabeth jen jennifer jenny jessica jessie jill joan joanne joanna joy
joyce judy judith karen kelly kelli kerry krista kristin kristen liz lori
lorrie lynn lynne margaret marge margie maria marilyn martha melissa
michelle mindy monica nancy natalie nicole pam pamela pat patricia patti
peggy rachel rebecca robin robyn rosanne rose ruth sally samantha sharon
sherry sheila shelley shelly shirley stephanie steph suzanne tammy teresa
theresa tina tracy tracey valerie vicki vicky wendy yvette yvonne abby
abigail ali alice alicia alison allison ann ashley barbara barb becky betsy
beth betty beverly bev brenda brittany candice caroline christy colleen
crystal cynthia dawn denise diana erin eve faye gail ginger gina gloria
grace heather helen holly jackie jacqueline janice jeanne jeanette jodi
jody june kara kathleen leah lillian lily loretta louise lucy madeline
megan meredith michele molly norma paige penny phyllis rita rhonda sabrina
sandra stacey stacy tania tanya terry terri trish wanda whitney willow
andrea angela aubrey audrey bonnie carla carmen cassie celeste charlotte
chloe claudia courtney dana danielle darlene edie eileen eleanor elinor
ella eloise eva evelyn florence frances gemma genevieve georgia hannah
harriet hazel ida ingrid irene iris isabel isabella ivy jaime jamie jasmine
jean jeanie joelle josephine julia leah leila lena leona lola lorraine
louisa lucinda maggie marcia margery margot marian marie marisa marjorie
marlene maureen maxine maya melinda miranda miriam mona nadia nadine nan
naomi nikki nina nora odette olga olivia paula pauline penelope phoebe
polly priscilla rae ramona regina renee rhoda rosa rosalie rosalind ruby
ruthie sage sabina selena serena shana shauna sherri sheryl sienna silvia
sondra sonia sonya sophia sophie stella sybil sylvia tabitha tamara tasha
tess tessa thelma tia tiffany tonia tonya tori trisha trudy ursula vanessa
vera veronica victoria viola violet virginia vivian wendi wilhelmina willa
wilma yolanda zoe maris marisol michaela josie loni constance susanna
sasha sammie noelle marina amelia kayla brittney annabelle bethany lauren
adam alan albert alex alexander alfred andrew andy anthony arthur barry
ben bernard bill bob brad brian bruce bryan carl charles charlie chris
christopher clarence clark colin craig curtis dale dan daniel darren dave
david dean dennis derek don donald douglas doug dwayne earl ed edward
edwin elliot eric ernest eugene evan fred frank franklin gary george
gerald gilbert glenn gordon greg gregory harry harvey henry herbert howard
ian isaac jack jacob james jamie jason jeff jeffrey jeremy jerome jerry
jesse jim jimmy joe joel john johnny jonathan jordan joseph josh joshua
justin keith kenneth ken kevin kirk kyle lance larry lawrence lee leo
leonard leroy leslie lewis lloyd logan louis luke mark martin matt matthew
maurice melvin michael mike milton mitchell mitch nathan neil nelson
nicholas nick norman oliver oscar owen patrick paul peter philip phillip
ralph randall randy raymond ray reginald richard rick robert rob rod
rodney roger ronald ron ross roy russell ryan sam samuel scott sean seth
shawn stan stanley stephen steve steven stuart ted terry thomas tim
timothy todd tom tony travis trevor tyler vernon victor vincent wade
walter warren wayne wesley william will willie wilson zachary""".split()
)

# Patterns for finding owner names. Order matters — earlier ones are
# higher confidence.
OWNER_KEYWORDS = re.compile(
    r"\b(owner|owned by|founder|founded by|proprietor|established by|"
    r"started by|opened by|run by|operated by|shop owner|store owner|"
    r"yarn shop owner|hi[,!]?\s+i'?m|i am|my name is|meet|introducing)\b",
    re.I,
)

NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{2,15})\s+([A-Z][a-z]{2,20}(?:[ '\-][A-Z][a-z]{2,20})?)\b"
)

GENERIC_LASTS_TO_REJECT = {
    "Yarn", "Yarns", "Knit", "Knitting", "Crochet", "Fiber", "Fibers",
    "Wool", "Wools", "Studio", "Shop", "Store", "Mill", "Threads", "Stitches",
    "Stitch", "Needles", "Crafts", "Craft", "Llc", "Inc", "Co", "Company",
    "And", "Or", "The", "A", "An", "Of", "In", "On", "At", "By", "From",
    "Welcome", "Hello", "Hi", "Greetings", "About", "Contact", "Home",
    "Page", "Site", "Website", "Online",
}


def domain_of(email: str) -> str:
    return email.split("@")[1].lower() if "@" in email else ""


def is_scrapeable_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    d = domain_of(email)
    return bool(d) and d not in FREE_MAIL


def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def find_owner_name(html: str) -> tuple[str, str] | None:
    """Return (first, last) if a high-confidence owner name is found."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None

    # Check meta tag author / og:* before stripping
    for meta_name in ("author", "twitter:creator", "article:author"):
        m = soup.find("meta", attrs={"name": meta_name}) or soup.find(
            "meta", attrs={"property": meta_name}
        )
        if m and m.get("content"):
            cand = m["content"].strip()
            nm = NAME_PATTERN.match(cand)
            if nm and nm.group(1).lower() in COMMON_FIRSTS:
                last = nm.group(2)
                if last not in GENERIC_LASTS_TO_REJECT:
                    return nm.group(1), last

    # Strip scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    if not text:
        return None

    # Look for owner-keyword + name patterns (window of 100 chars after match)
    for m in OWNER_KEYWORDS.finditer(text):
        window = text[max(0, m.start() - 80):m.end() + 100]
        for nm in NAME_PATTERN.finditer(window):
            first, last = nm.group(1), nm.group(2)
            if first.lower() not in COMMON_FIRSTS:
                continue
            if last in GENERIC_LASTS_TO_REJECT:
                continue
            if first.lower() == last.split()[-1].lower():
                continue
            return first, last

    # Pattern: "[Name], owner" or "[Name] is the owner"
    m = re.search(
        r"\b([A-Z][a-z]{2,15})\s+([A-Z][a-z]{2,20})\b[,]?\s+(?:the\s+)?"
        r"(?:owner|founder|proprietor|owner/operator|owner-operator)\b",
        text,
    )
    if m and m.group(1).lower() in COMMON_FIRSTS:
        last = m.group(2)
        if last not in GENERIC_LASTS_TO_REJECT:
            return m.group(1), last

    # Pattern: "Welcome to [Shop], I'm [Name]" / "Hi, I'm Sarah" / "I'm Annie"
    m = re.search(
        r"\b(?:hi[,!]?\s+i'?m|i'?m|my name is|welcome[,]?\s+i'?m)\s+"
        r"([A-Z][a-z]{2,15})(?:\s+([A-Z][a-z]{2,20}))?\b",
        text,
    )
    if m and m.group(1).lower() in COMMON_FIRSTS:
        last = m.group(2) or ""
        if last and last in GENERIC_LASTS_TO_REJECT:
            last = ""
        return m.group(1), last

    # Pattern: "Meet [Name]" header
    m = re.search(
        r"\bMeet\s+([A-Z][a-z]{2,15})\s+([A-Z][a-z]{2,20})\b", text
    )
    if m and m.group(1).lower() in COMMON_FIRSTS:
        last = m.group(2)
        if last not in GENERIC_LASTS_TO_REJECT:
            return m.group(1), last

    return None


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=PER_REQUEST_TIMEOUT),
            allow_redirects=True,
            ssl=False,
        ) as resp:
            if resp.status != 200:
                return None
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype.lower() and "text" not in ctype.lower():
                return None
            return await resp.text(errors="ignore")
    except Exception:
        return None


async def scrape_domain(
    session: aiohttp.ClientSession, domain: str, sem: asyncio.Semaphore
) -> tuple[str, str] | None:
    base = normalize_url(domain)
    async with sem:
        for path in ABOUT_PATHS:
            html = await fetch(session, base.rstrip("/") + path)
            if html:
                name = find_owner_name(html)
                if name:
                    return name
    return None


async def main() -> None:
    rows = list(csv.DictReader(open(CSV_PATH)))
    fieldnames = [
        "email", "phone", "first_name", "last_name", "company", "country",
        "category", "source_file",
    ]

    # Collect unique scrapeable domains paired with row indices
    domain_to_rows: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if r["first_name"].strip():
            continue
        if not is_scrapeable_email(r["email"]):
            continue
        d = domain_of(r["email"])
        domain_to_rows.setdefault(d, []).append(i)

    print(f"Domains to scrape: {len(domain_to_rows)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}

    found = {}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = {d: asyncio.create_task(scrape_domain(session, d, sem))
                 for d in domain_to_rows}
        done = 0
        for d, t in tasks.items():
            res = await t
            done += 1
            if res:
                found[d] = res
            if done % 25 == 0:
                print(f"  {done}/{len(tasks)} domains done, {len(found)} hits so far")

    print(f"\nDomains with owner name found: {len(found)} / {len(domain_to_rows)}")

    # Apply
    applied_first = 0
    applied_last = 0
    for d, idxs in domain_to_rows.items():
        if d not in found:
            continue
        first, last = found[d]
        for i in idxs:
            if not rows[i]["first_name"]:
                rows[i]["first_name"] = first
                applied_first += 1
            if last and not rows[i]["last_name"]:
                rows[i]["last_name"] = last
                applied_last += 1

    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"first_name applied: {applied_first}")
    print(f"last_name applied:  {applied_last}")


if __name__ == "__main__":
    asyncio.run(main())
