import os
import json
import asyncio
from urllib.parse import quote
import requests
from playwright.async_api import async_playwright, Error as PlaywrightError

# ─── CONFIG ────────────────────────────────────────────────────────────────────
OUTPUT_BASE = r"C:\Users\singl\PycharmProjects\WebScrape\FileStore"
YEARS         = list(range(2013, 2014))
REPORT_TYPE   = 3          # Apportionment
ORG_TYPE_ID   = 2          # District (CCDDD)
REPORT_SLUGS  = ["safs"]

BASE     = "https://ospi.k12.wa.us"
PROXY    = BASE + "/modules/custom/ospi_reports/cors_proxy.php"
GET_DOCS = BASE + "/modules/custom/ospi_reports/get_documents.php"

session = requests.Session()

def proxy_get_json(target_url):
    proxy_url = f"{PROXY}?action=cors_proxy&uri={quote(target_url, safe='')}"
    r = session.get(proxy_url, headers={"X-Requested-With":"XMLHttpRequest"}, timeout=30)
    r.raise_for_status()
    data = json.loads(r.text.strip())
    if isinstance(data, str):
        data = json.loads(data)
    return data


def fetch_document_list(year, org_id, slug):
    resp = session.post(
        GET_DOCS,
        data={
            "uri": "https://hostedreports.ospi.k12.wa.us/api/0/Document/Search",
            "year": year,
            "report_type": REPORT_TYPE,
            "org": org_id,
            "org_type": ORG_TYPE_ID,
            "report": slug
        },
        timeout=30
    )
    resp.raise_for_status()
    docs = resp.json()
    if isinstance(docs, str):
        docs = json.loads(docs)
    return docs

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Referer": "https://ospi.k12.wa.us/policy-funding/school-apportionment/safs-report"
            }
        )

        for year in YEARS:
            orgs_api = (
                f"https://hostedreports.ospi.k12.wa.us/api/0/Document/Organizations/{year}/SubCategory/{REPORT_TYPE}"
            )
            all_orgs = proxy_get_json(orgs_api)
            districts = [o for o in all_orgs if o.get("typeId") == ORG_TYPE_ID]

            for org in districts:
                org_id   = org["organizationId"]
                org_name = org["name"].replace("/", "-")

                for slug in REPORT_SLUGS:
                    docs = fetch_document_list(year, org_id, slug)
                    if not docs:
                        continue

                    out_dir = os.path.join(OUTPUT_BASE, str(year), org_name, slug)
                    os.makedirs(out_dir, exist_ok=True)

                    for doc in docs:
                        doc_id = doc["documentId"]
                        pretty = doc["title"].replace(" ", "_").replace("/", "-") + ".pdf"
                        dest   = os.path.join(out_dir, pretty)
                        download_url = f"https://hostedreports.ospi.k12.wa.us/api/0/Document/Download/{doc_id}"

                        # Drive browser download
                        page = await ctx.new_page()
                        async with page.expect_download() as download_info:
                            try:
                                await page.goto(download_url)
                            except PlaywrightError as e:
                                # Ignore aborted navigation triggered by download
                                if 'net::ERR_ABORTED' not in str(e):
                                    raise
                        download = await download_info.value
                        await download.save_as(dest)
                        print(f"✔ {year}/{org_name}/{slug} → {pretty}")
                        await page.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
