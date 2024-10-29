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
        
        # Define all selectors upfront for better maintainability
        SELECTORS = {
            'format': "h3.text-center",
            'title': ".card-title.main-title.text-center",
            'authors': ".card-subtitle.mb-2.text-muted.text-center",
            'abstract_button': 'a.card-link[data-bs-toggle="collapse"][href="#abstract_details"]',
            'abstract_div': '#abstract_details.collapse.show'
        }
        
        # Replace individual wait_for_element calls with batch collection
        wait = WebDriverWait(driver, 10)
        result_dict = {}
        
        # Collect basic elements (format, title, authors)
        for key in ['format', 'title', 'authors']:
            try:
                element_text = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS[key]))
                ).text
                
                # Special processing for authors
                if key == 'authors':
                    # Split by · (middle dot) and strip whitespace from each author
                    result_dict[key] = [author.strip() for author in element_text.split('·')]
                else:
                    result_dict[key] = element_text
                    
            except TimeoutException:
                print(f"Timeout waiting for {key}")
                return None
        
        # Handle abstract with improved error handling
        try:
            abstract_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTORS['abstract_button']))
            )
            
            # Combine scrolling and clicking
            driver.execute_script("""
                arguments[0].scrollIntoView(true);
                arguments[0].click();
            """, abstract_button)
            
            # More efficient abstract text extraction
            abstract_div = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS['abstract_div']))
            )
            
            # Optimized selector list with more specific selectors first
            abstract_text = None
            for selector in ['p.card-text', '#abstractExample', '.card-body p', 'p']:
                found_elements = abstract_div.find_elements(By.CSS_SELECTOR, selector)
                if found_elements and found_elements[0].text.strip():
                    abstract_text = found_elements[0].text.strip()
                    break
            
            if abstract_text:
                # Remove "Abstract:" prefix (case-insensitive)
                abstract_text = abstract_text.replace('Abstract:', '', 1).strip()
                result_dict['abstract'] = abstract_text
            else:
                result_dict['abstract'] = "Abstract text not found"
            
        except Exception as e:
            print(f"Error with abstract: {str(e)}")
            result_dict['abstract'] = "Error retrieving abstract"
        
        result_dict['url'] = url
        return result_dict
        
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
    url = "https://nips.cc/virtual/2024/poster/96272"
    
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
