from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd
import time
from tqdm import tqdm
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')  # Set window size
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    return webdriver.Chrome(options=options)

def wait_for_element(driver, selector, by=By.CSS_SELECTOR, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return element
    except TimeoutException:
        print(f"Timeout waiting for element: {selector}")
        return None

def scrape_paper_details(url, driver):
    try:
        driver.get(url)
        
        # Only need abstract-related selectors now
        SELECTORS = {
            'abstract_button': 'a.card-link[data-bs-toggle="collapse"][href="#abstract_details"]',
            'abstract_div': '#abstract_details.collapse.show'
        }
        
        wait = WebDriverWait(driver, 10)
        
        # Handle abstract
        try:
            abstract_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTORS['abstract_button']))
            )
            
            driver.execute_script("""
                arguments[0].scrollIntoView(true);
                arguments[0].click();
            """, abstract_button)
            
            abstract_div = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS['abstract_div']))
            )
            
            abstract_text = None
            for selector in ['p.card-text', '#abstractExample', '.card-body p', 'p']:
                found_elements = abstract_div.find_elements(By.CSS_SELECTOR, selector)
                if found_elements and found_elements[0].text.strip():
                    abstract_text = found_elements[0].text.strip()
                    break
            
            return abstract_text.replace('Abstract:', '', 1).strip() if abstract_text else "Abstract text not found"
            
        except Exception as e:
            print(f"Error with abstract: {str(e)}")
            return "Error retrieving abstract"
        
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
        return None

def process_single_url(url):
    """Helper function to process a single URL with its own driver"""
    driver = setup_driver()
    try:
        abstract = scrape_paper_details(url, driver)
        return abstract
    finally:
        driver.quit()

def main():
    # Add argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Run in test mode with only 4 samples')
    args = parser.parse_args()

    # Read the JSON file
    df_papers = pd.read_json('nips_2024.json')
    
    # Apply test mode if specified
    if args.test:
        df_papers = df_papers.head(64)
        max_workers = 32  # Limit workers in test mode
        print("Running in test mode with first 4 samples...")
    else:
        max_workers = min(32, os.cpu_count() * 4)  # Limit to 32 workers maximum
    
    print(f"Starting scraping with {max_workers} workers...")
    
    # Initialize results dictionary to maintain order
    abstracts = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks and store futures
        future_to_url = {
            executor.submit(process_single_url, url): i 
            for i, url in enumerate(df_papers['site'])
        }
        
        # Process completed futures with progress bar
        with tqdm(total=len(df_papers), desc="Scraping abstracts") as pbar:
            for future in as_completed(future_to_url):
                index = future_to_url[future]
                try:
                    abstract = future.result()
                    abstracts[index] = abstract
                except Exception as e:
                    print(f"Error processing URL at index {index}: {str(e)}")
                    abstracts[index] = "Error retrieving abstract"
                pbar.update(1)
    
    # Convert results dictionary to list in correct order
    ordered_abstracts = [abstracts[i] for i in range(len(df_papers))]
    
    # Add abstracts to dataframe
    df_papers['abstract'] = ordered_abstracts
    
    # Save to CSV with appropriate name
    output_file = 'nips_2024_with_abstracts_test.csv' if args.test else 'nips_2024_with_abstracts.csv'
    df_papers.to_csv(output_file, index=False)
    
    print(f"\nSuccessfully scraped {len(ordered_abstracts)} abstracts")
    print(f"Results saved to: {output_file}")
    print("\nFirst few entries:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print(df_papers.head())

if __name__ == "__main__":
    main()
