import pandas as pd 
from pydantic import BaseModel
from openai import AsyncOpenAI
import dotenv
import os
dotenv.load_dotenv()
import json
from tenacity import retry, stop_after_attempt, wait_random_exponential
import re
from tqdm import tqdm
import asyncio
from typing import List, Dict
import aiohttp
import os.path
from datetime import datetime


df = pd.read_csv('nips_2024_with_abstracts_fixed.csv')

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
async def get_completion_with_backoff(title: str, abstract: str):
    return await client.chat.completions.create(
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

async def get_relevance_with_backoff(title: str, abstract: str) -> Relevance:
    try:
        completion = await get_completion_with_backoff(title, abstract)
        output = completion.choices[0].message.content
        
        try:
            json_output = parse_json_with_retry(output)
            return Relevance(**json_output)
        except Exception as e:
            print(f"Failed to parse JSON after retries: {e}")
            return Relevance(justification="", is_relevant=False)
            
    except Exception as e:
        print(f"API call failed after retries: {e}")
        return Relevance(justification="", is_relevant=False)

async def process_batch(batch_indices: List[int], df: pd.DataFrame) -> List[Dict]:
    async def process_single(idx: int) -> Dict:
        try:
            relevance = await get_relevance_with_backoff(df.loc[idx, 'title'], df.loc[idx, 'abstract'])
            return {
                'idx': idx,
                'justification': relevance.justification,
                'is_relevant': relevance.is_relevant
            }
        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            return {
                'idx': idx,
                'justification': "",
                'is_relevant': False
            }
    
    return await asyncio.gather(*[process_single(idx) for idx in batch_indices])

CHECKPOINT_FILE = 'relevance_checkpoint.csv'
PROGRESS_FILE = 'processed_indices.txt'
FINAL_OUTPUT = 'nips_2024_with_relevance.csv'

def save_checkpoint(df: pd.DataFrame, processed_indices: List[int]):
    # Save current dataframe state
    df.to_csv(CHECKPOINT_FILE, index=False)
    
    # Save processed indices
    with open(PROGRESS_FILE, 'w') as f:
        f.write(','.join(map(str, processed_indices)))
    
    print(f"Checkpoint saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def load_checkpoint() -> tuple[set[int], pd.DataFrame]:
    processed_indices = set()
    
    # Load processed indices if they exist
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            content = f.read().strip()
            if content:
                processed_indices = set(map(int, content.split(',')))
    
    # Load checkpoint dataframe if it exists
    if os.path.exists(CHECKPOINT_FILE):
        df = pd.read_csv(CHECKPOINT_FILE)
        print(f"Loaded checkpoint with {len(processed_indices)} processed items")
    else:
        df = pd.read_csv('nips_2024_with_abstracts_fixed.csv')
        print("Starting fresh processing")
    
    return processed_indices, df

async def main():
    processed_indices, df = load_checkpoint()
    batch_size = 10  # Adjust based on your rate limits
    all_indices = df.index.tolist()
    remaining_indices = [idx for idx in all_indices if idx not in processed_indices]
    
    print(f"Total items: {len(all_indices)}")
    print(f"Remaining items: {len(remaining_indices)}")
    
    try:
        for i in tqdm(range(0, len(remaining_indices), batch_size), desc="Processing batches"):
            batch_indices = remaining_indices[i:i + batch_size]
            results = await process_batch(batch_indices, df)
            
            # Update the dataframe with results
            for result in results:
                idx = result['idx']
                df.loc[idx, 'justification'] = result['justification']
                df.loc[idx, 'is_relevant'] = result['is_relevant']
                processed_indices.add(idx)
            
            # Save checkpoint every 5 batches
            if i % (batch_size * 5) == 0:
                save_checkpoint(df, list(processed_indices))
    
    except Exception as e:
        print(f"Error encountered: {e}")
        print("Saving checkpoint before exit...")
        save_checkpoint(df, list(processed_indices))
        raise e
    
    # Save final results
    df.to_csv(FINAL_OUTPUT, index=False)
    
    # Clean up checkpoint files
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
    
    print(f"Processing complete. Results saved to {FINAL_OUTPUT}")

if __name__ == "__main__":
    asyncio.run(main())