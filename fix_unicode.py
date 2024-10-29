import pandas as pd
from unidecode import unidecode

df = pd.read_csv('nips_2024_with_abstracts.csv')

# Function to safely apply unidecode
def safe_unidecode(text):
    if pd.isna(text):
        return text
    return unidecode(str(text))

# Apply unidecode to each column
df['title'] = df['title'].apply(safe_unidecode)
df['abstract'] = df['abstract'].apply(safe_unidecode)

df.to_csv('nips_2024_with_abstracts_fixed.csv', index=False)