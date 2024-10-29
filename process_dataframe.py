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
import json
from pathlib import Path

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

def load_checkpoint():
    checkpoint_file = Path('scraping_checkpoint.json')
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return {'completed_indices': [], 'last_save': 0}

def save_checkpoint(completed_indices, df_papers, last_save):
    # Save checkpoint data
    checkpoint_data = {
        'completed_indices': completed_indices,
        'last_save': last_save
    }
    with open('scraping_checkpoint.json', 'w') as f:
        json.dump(checkpoint_data, f)
    
    # Save partial results
    output_file = 'nips_2024_with_abstracts_partial.csv'
    df_papers.to_csv(output_file, index=False)
    print(f"\nCheckpoint saved: {len(completed_indices)} abstracts processed")

def main():
    # Add argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Run in test mode with only 4 samples')
    parser.add_argument('--checkpoint-freq', type=int, default=128, 
                       help='Number of abstracts to process before saving checkpoint (default: 128)')
    args = parser.parse_args()

    # Read the JSON file
    df_papers = pd.read_json('nips_2024.json')
    
    # Apply test mode if specified
    if args.test:
        df_papers = df_papers.head(64)
        max_workers = 32
        print("Running in test mode with first 64 samples...")
    else:
        max_workers = min(32, os.cpu_count() * 4)
    
    # Load checkpoint
    checkpoint = load_checkpoint()
    completed_indices = checkpoint['completed_indices']
    last_save = checkpoint['last_save']
    
    # Filter out already processed URLs
    remaining_urls = [
        (i, url) for i, url in enumerate(df_papers['site'])
        if i not in completed_indices
    ]
    
    print(f"Resuming from {len(completed_indices)} completed abstracts...")
    print(f"Starting scraping with {max_workers} workers...")
    
    # Initialize results dictionary with existing results
    abstracts = {i: "Previously scraped" for i in completed_indices}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(process_single_url, url): i 
            for i, url in remaining_urls
        }
        
        # Process completed futures with progress bar
        with tqdm(total=len(remaining_urls), desc="Scraping abstracts") as pbar:
            for future in as_completed(future_to_url):
                index = future_to_url[future]
                try:
                    abstract = future.result()
                    abstracts[index] = abstract
                    completed_indices.append(index)
                    
                    # Save checkpoint every args.checkpoint_freq abstracts
                    if len(completed_indices) - last_save >= args.checkpoint_freq:
                        # Update partial results in dataframe
                        ordered_abstracts = [
                            abstracts.get(i, "") for i in range(len(df_papers))
                        ]
                        df_papers['abstract'] = ordered_abstracts
                        save_checkpoint(completed_indices, df_papers, len(completed_indices))
                        last_save = len(completed_indices)
                        
                except Exception as e:
                    print(f"Error processing URL at index {index}: {str(e)}")
                    abstracts[index] = "Error retrieving abstract"
                pbar.update(1)
    
    # Convert results dictionary to list in correct order
    ordered_abstracts = [abstracts.get(i, "") for i in range(len(df_papers))]
    
    # Add abstracts to dataframe
    df_papers['abstract'] = ordered_abstracts
    
    # Save final results
    output_file = 'nips_2024_with_abstracts_test.csv' if args.test else 'nips_2024_with_abstracts.csv'
    df_papers.to_csv(output_file, index=False)
    
    # Clean up checkpoint file
    if os.path.exists('scraping_checkpoint.json'):
        os.remove('scraping_checkpoint.json')
    
    print(f"\nSuccessfully scraped {len(completed_indices)} abstracts")
    print(f"Results saved to: {output_file}")
    print("\nFirst few entries:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print(df_papers.head())

if __name__ == "__main__":
    main()
