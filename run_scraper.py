# run_scraper.py
import os
import time
import random
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import pandas as pd
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
INPUT_CSV = "temp2.csv"       
OUTPUT_CSV = "airbnb_prices_extracted.csv"
URL_COLUMN_NAME = "listing_url"                 
BATCH_SIZE = 4                          # Save progress every 5 URLs to disk

# Target Date Parameters
TARGET_CHECK_IN = "2027-02-01"
TARGET_CHECK_OUT = "2027-02-06"

def update_url_dates(url, check_in, check_out):
    """Parses incoming URL, strips old date queries, and forces target dates."""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        # Inject target conditions while retaining static structure elements
        query_params['check_in'] = [check_in]
        query_params['check_out'] = [check_out]
        query_params['guests'] = ['1']
        query_params['adults'] = ['1']
        
        # Flatten query parameters back down
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query))
    except Exception:
        return url

def main():
    # 1. Resume Checkpoint Management
    processed_urls = set()
    if os.path.exists(OUTPUT_CSV):
        try:
            progress_df = pd.read_csv(OUTPUT_CSV, usecols=["Original_URL"])
            processed_urls = set(progress_df["Original_URL"].dropna().tolist())
            print(f"-> Resuming crawl. Skipping {len(processed_urls)} processed items.")
        except Exception:
            pass 

    # 2. File and Column Verification
    if not os.path.exists(INPUT_CSV):
        print(f"❌ Error: Cannot discover input file '{INPUT_CSV}' in this folder.")
        return
        
    df_all = pd.read_csv(INPUT_CSV)
    all_urls = df_all[URL_COLUMN_NAME].dropna().unique().tolist()
    urls_to_process = [u for u in all_urls if u not in processed_urls]
    total_tasks = len(urls_to_process)
    
    if total_tasks == 0:
        print("✅ Scale processing complete! No remaining URLs to scan.")
        return

    print(f"-> Initiating automated extraction for {total_tasks} lines...")
    
    # 3. Persistent Stealthed Browser Context
    with sync_playwright() as p:
        print("-> Opening human-simulated browser window...")
        browser = p.chromium.launch(headless=False) # View live to clear captchas manually
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US"
        )
        page = context.new_page()
        batch_results = []
        
        # 4. Processing Loop
        for index, orig_url in enumerate(urls_to_process, start=1):
            # Transform url format to target dates
            target_url = update_url_dates(orig_url, TARGET_CHECK_IN, TARGET_CHECK_OUT)
            result = {"Original_URL": orig_url, "Target_URL": target_url, "Price_Per_Night": "Error", "Status": "Failed"}
            
            print(f"[{index}/{total_tasks}] Navigating target timeframe...")
            try:
                # Randomized rhythm delay to simulate manual clicking
                time.sleep(random.uniform(2.0, 4.0))
                
                # Fetch page structure
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.mouse.wheel(0, 350) # Scroll slightly to invoke dynamic prices
                
                # Robust array of current selectors targeting price fields
                price_selectors = [
                    '[data-testid="book-it-default"] span._1y74zjx', 
                    '[data-testid="price-element"] span._1y74zjx',
                    'span._1y74zjx',
                    'span._ty6r37',
                    'div[data-testid="book-it-sidebar"] span._11v8d7'
                ]
                
                resolved_selector = None
                for selector in price_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                        resolved_selector = selector
                        break
                    except:
                        continue
                
                if resolved_selector:
                    price_raw = page.query_selector(resolved_selector).inner_text()
                    result["Price_Per_Night"] = price_raw.strip()
                    result["Status"] = "Success"
                    print(f"   ✨ Collected Rate: {price_raw.strip()}")
                else:
                    # Page successfully loaded but dates may be blocked/booked out
                    result["Price_Per_Night"] = "Unavailable/Booked"
                    result["Status"] = "No Availability"
                    print("   ⚠️ Booking box found, but exact pricing text is absent.")
                    
            except Exception as e:
                result["Price_Per_Night"] = "Timeout/Verification Block"
                result["Status"] = f"Error: {type(e).__name__}"
                print(f"   ❌ Access Interrupted: {type(e).__name__}")
                
            batch_results.append(result)
            
            # 5. Flush batch to file system
            if len(batch_results) >= BATCH_SIZE or index == total_tasks:
                batch_df = pd.DataFrame(batch_results)
                file_exists = os.path.exists(OUTPUT_CSV)
                batch_df.to_csv(OUTPUT_CSV, mode='a', header=not file_exists, index=False)
                batch_results.clear()
                print(f"   [Disk Partition] Saved checkpoint state to {OUTPUT_CSV}")
                
        context.close()
        browser.close()
        print("\n🎉 Core dataset pass concluded.")

if __name__ == "__main__":
    main()
