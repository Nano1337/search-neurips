from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import pandas as pd
import time
from tqdm import tqdm

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
        time.sleep(2)  # Allow initial page load
        
        # Get format
        format_type = wait_for_element(driver, "h3.text-center")
        if not format_type:
            return None
        format_type = format_type.text
        
        # Get title
        title = wait_for_element(driver, ".card-title.main-title.text-center")
        if not title:
            return None
        title = title.text
        
        # Get authors
        authors = wait_for_element(driver, ".card-subtitle.mb-2.text-muted.text-center")
        if not authors:
            return None
        authors = authors.text
        
        # Try to find and click abstract button with better state handling
        try:
            # Wait for the abstract button in collapsed state
            wait = WebDriverWait(driver, 10)
            abstract_button = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                    'a.card-link[data-bs-toggle="collapse"][href="#abstract_details"]'))
            )
            
            if abstract_button:
                # Scroll to button to ensure it's clickable
                driver.execute_script("arguments[0].scrollIntoView(true);", abstract_button)
                time.sleep(1)
                
                # Click using JavaScript
                driver.execute_script("arguments[0].click();", abstract_button)
                time.sleep(1)  # Wait for click to register
                
                # Wait for collapse animation
                try:
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "collapsing")))
                except TimeoutException:
                    pass  # It's okay if we miss the collapsing state
                
                # Wait for expanded state
                abstract_div = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                        '#abstract_details.collapse.show'))
                )
                
                # Try multiple selectors for the abstract text
                abstract_text = None
                selectors = [
                    'p.card-text',
                    '.card-body p',
                    '#abstractExample',
                    'p'
                ]
                
                for selector in selectors:
                    try:
                        abstract_element = abstract_div.find_element(By.CSS_SELECTOR, selector)
                        if abstract_element and abstract_element.text.strip():
                            abstract_text = abstract_element.text.strip()
                            break
                    except:
                        continue
                
                abstract = abstract_text if abstract_text else "Abstract text not found"
            else:
                abstract = "Abstract button not found"
                
        except Exception as e:
            print(f"Error with abstract button: {e}")
            abstract = "Error retrieving abstract"
        
        return {
            'format': format_type,
            'title': title,
            'authors': authors,
            'abstract': abstract,
            'url': url
        }
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
        return None

def main():
    # Read the CSV file with paper URLs
    df_papers = pd.read_csv('neurips_2024_papers.csv')
    
    # Initialize the driver
    driver = setup_driver()
    
    # List to store results
    results = []
    
    # Process each URL with a progress bar
    for url in tqdm(df_papers['URL'], desc="Scraping papers"):
        paper_details = scrape_paper_details(url, driver)
        if paper_details:
            results.append(paper_details)
        
        # Add a small delay to avoid overwhelming the server
        time.sleep(2)
    
    # Create DataFrame and save to CSV
    df_results = pd.DataFrame(results)
    df_results.to_csv('neurips_2024_papers_details.csv', index=False)
    
    # Cleanup
    driver.quit()
    
    print(f"Successfully scraped {len(results)} papers")
    print("\nFirst few entries:")
    print(df_results.head())
if __name__ == "__main__":
    # main()

    # test with a single url first
    url = "https://nips.cc/virtual/2024/poster/93870"
    
    # Initialize the driver
    driver = setup_driver()
    
    # Test with single URL
    paper_details = scrape_paper_details(url, driver)
    
    if paper_details:
        print("\nTest paper details:")
        for key, value in paper_details.items():
            print(f"{key}: {value}")
    
    # Cleanup
    driver.quit()
