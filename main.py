from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

# Set up the driver
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--disable-extensions')
options.page_load_strategy = 'eager'

print("Starting browser")
browser = webdriver.Chrome(options=options)
browser.set_page_load_timeout(30)
url = "https://papercopilot.com/paper-list/neurips-paper-list/neurips-2024-paper-list/"
browser.get(url)

# Initialize variables
all_unique_links = set()
last_height = browser.execute_script("return document.body.scrollHeight")

# Modified waiting and scrolling strategy
def wait_for_element_count_change(browser, old_count, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        new_count = len(browser.find_elements(By.TAG_NAME, 'a'))
        if new_count > old_count:
            return new_count
        time.sleep(0.5)
    return old_count

# Click Fetch All and wait for initial load
wait = WebDriverWait(browser, 30)
try:
    fetch_button = wait.until(EC.element_to_be_clickable((By.XPATH, 
        "//*[contains(text(), 'Click to Fetch All')]")))
    fetch_button.click()
    print("Successfully clicked 'Fetch All' button")
    
    # Wait longer for initial content load
    time.sleep(15)  # Increased initial wait time
except Exception as e:
    print(f"Error clicking 'Fetch All' button: {e}")

# Modified scrolling strategy
print("Starting scroll and collecting links...")
SCROLL_PAUSE_TIME = 2
last_link_count = 0
no_change_count = 0
MAX_NO_CHANGE = 5

try:
    while no_change_count < MAX_NO_CHANGE:
        # Get current link count
        current_links = browser.find_elements(By.TAG_NAME, 'a')
        current_count = len(current_links)
        
        # Scroll in smaller increments
        for _ in range(3):  # Scroll 3 times before checking
            browser.execute_script("window.scrollBy(0, 1000);")
            time.sleep(SCROLL_PAUSE_TIME)
        
        # Force scroll to bottom occasionally
        if no_change_count % 2 == 0:
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)
        
        # Check if we're still getting new links
        new_count = wait_for_element_count_change(browser, current_count)
        print(f"Links found: {new_count}")
        
        if new_count <= current_count:
            no_change_count += 1
        else:
            no_change_count = 0
            
        last_link_count = new_count

except Exception as e:
    print(f"Error during scrolling: {e}")

# Modified link collection strategy
all_unique_links = set()
retry_count = 0
MAX_RETRIES = 3

while retry_count < MAX_RETRIES:
    try:
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        links = soup.find_all('a')
        current_links = {link.get('href') for link in links if link.get('href') is not None}
        all_unique_links.update(current_links)
        break
    except Exception as e:
        print(f"Error collecting links, attempt {retry_count + 1}: {e}")
        retry_count += 1
        time.sleep(2)

print(f"\nTotal unique links collected: {len(all_unique_links)}")

# Convert set to DataFrame
df = pd.DataFrame(list(all_unique_links), columns=['URL'])

# Filter specifically for NeurIPS 2024 poster links
neurips_prefix = "https://nips.cc/virtual/2024/poster"
df_papers = df[df['URL'].str.contains(neurips_prefix, case=False, na=False)]

# Add an ID column
df_papers['ID'] = range(1, len(df_papers) + 1)

# Reorder columns
df_papers = df_papers[['ID', 'URL']]

# Save to CSV
df_papers.to_csv('neurips_2024_papers.csv', index=False)

print(f"\nTotal NeurIPS 2024 papers found: {len(df_papers)}")
print("\nFirst few entries in the DataFrame:")
print(df_papers.head())

# Optional: Print all found paper URLs for verification
print("\nAll paper URLs found:")
for url in df_papers['URL']:
    print(url)

browser.quit()