import pandas as pd 
from pydantic import BaseModel
from openai import OpenAI
import dotenv
import os
dotenv.load_dotenv()
import json
from tenacity import retry, stop_after_attempt, wait_random_exponential
import re
from tqdm import tqdm


df = pd.read_csv('nips_2024_with_abstracts_fixed.csv')

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Relevance(BaseModel):
    justification: str
    is_relevant: bool

class InvalidJSONResponse(Exception):
    """Raised when JSON parsing fails"""
    pass

sysprompt = """
You are an AI assistant tasked with determining the relevance of research papers to the field of Machine Learning Data Curation. This field includes, but is not limited to, the following topics:
Synthetic data generation, Continuous pre-training, Multimodal Data Curation, Text data curation, Data mixing, Data augmentation, Data Filtering, Data Pruning, Deduplication, Target distribution matching, heuristic filtering, and automated curation.

You are given a research paper title and abstract. Your task is to determine if the paper is relevant to the field of Machine Learning Data Curation, also called Data-Centric AI.

Please first reason and provide a justification for your answer. Then, provide your answer as a boolean value. Please respond in JSON format with the following two fields:
- justification: A justification for your answer. Please be very concise and to the point.
- is_relevant: A boolean value indicating if the paper is relevant to the field of Machine Learning Data Curation.
"""

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def get_completion_with_backoff(title: str, abstract: str):
    return client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": sysprompt},
            {"role": "user", "content": f"Title: {title}\nAbstract: {abstract}"},
        ],
    )

@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(3))
def parse_json_with_retry(output: str) -> dict:
    json_match = re.search(r'\{[\s\S]*\}', output)
    if not json_match:
        raise InvalidJSONResponse("No valid JSON found in the response")
    
    cleaned_json = json_match.group(0)
    try:
        return json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        raise InvalidJSONResponse(f"Invalid JSON format: {e}")

def get_relevance_with_backoff(title: str, abstract: str) -> Relevance:
    try:
        completion = get_completion_with_backoff(title, abstract)
        output = completion.choices[0].message.content
        
        try:
            json_output = parse_json_with_retry(output)
            return Relevance(**json_output)
        except Exception as e:
            print(f"Failed to parse JSON after retries: {e}")
            # Return default values if all retries fail
            return Relevance(justification="", is_relevant=False)
            
    except Exception as e:
        print(f"API call failed after retries: {e}")
        return Relevance(justification="", is_relevant=False)


# Process all rows with progress bar
for idx in tqdm(df.index, desc="Processing papers"):
    try:
        relevance = get_relevance_with_backoff(df.loc[idx, 'title'], df.loc[idx, 'abstract'])
        df.loc[idx, 'justification'] = relevance.justification
        df.loc[idx, 'is_relevant'] = relevance.is_relevant
    except Exception as e:
        print(f"Error processing row {idx}: {e}")
        df.loc[idx, 'justification'] = ""
        df.loc[idx, 'is_relevant'] = False

# Save the updated dataframe
output_path = 'nips_2024_with_relevance.csv'
df.to_csv(output_path, index=False)
print(f"Results saved to {output_path}")