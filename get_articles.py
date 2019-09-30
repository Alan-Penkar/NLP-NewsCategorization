#!/usr/bin/python3

from functools import lru_cache
import re
import asyncio

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import aiofiles
from aiohttp import ClientSession

ua = UserAgent()
headers={'User-Agent':ua.random}

async def get_article(url, session):
    """
    Handles making requests asynchronously for a single page
    """
    async with session.request(url=url, method='GET', headers=headers) as resp:
        if resp.status!=200:
            return None
        else:
            return await resp.text()

    try:
        text = await session.request(url=url, method='GET', headers=headers).text()
    except Exception as e:
        return None
    else:
        return text

async def parse_article(text):
    """
    Parses text from HTML page.  
    Several schemes seem to exist in the html set, so a few methods are tried to capture all articles correctly
      - all methods fail on the wrong page type, which is why this uses try/except instead of trying to classify pages
    """
    soup = BeautifulSoup(text, 'lxml')
    try:
        string = " ".join(soup.find("section", {"id":"entry-body"}).stripped_strings)
        return string
    except:
        pass
    try:
        string = " ".join([''.join(x.stripped_strings) for x in soup.find_all("div", {"class":"content-list-component"}) ])
        return string
    except:
        pass
    return None

async def write_article(text, name):
    """
    Handles file I/O - overwrites if file exists
    """
    async with aiofiles.open(f"articles/{name}.txt", "w") as f:
        await f.write(text)

async def write_error(name, url, error_type):
    """
    Tracks errors to rerun script after it finishes
    """
    async with aiofiles.open(f"error_locations.csv", "a") as f:
        await f.write(f"{name},{url},{error_type}\n")

def initialize_error_file():
    with open("error_locations.csv", "w") as f:
        f.write("Row,URL,ErrorType\n")

async def chain_processing(file_name, session, url):
    try:
        resp = await get_article(url,session)
    except:
        await write_error(file_name, url, 'GET')
        return None
    else:
        if resp is None:
            await write_error(file_name, url, 'GET')
            return

    text = await parse_article(resp)
    if text is None:
        await write_error(file_name, url, 'PARSE')
    else:
        try:
            await write_article(text, file_name)    
        except:
            await write_error(file_name, url, 'WRITE')
    
@lru_cache()
def get_prepared_data():
    print('Preparing Data')
    df = pd.read_json('data/News_Category_Dataset.json', lines=True, orient='records')
    p=re.compile(r'(?<=www\.).+(?=\.com)')

    def get_root(url):
        tmp = p.search(url)
        if tmp is None:
            return None
        else:
            return tmp.group()

    df['root'] = df.link.apply(get_root)
    mismatches = df[df.root!='huffingtonpost']['link']
    print(f"Total number of news articles = {len(df)}\nNumber of mismatches = {len(mismatches)}\n")
    
    df.drop(mismatches.index, inplace=True)
    return df

async def main(start, stop):
    df = get_prepared_data()
    async with ClientSession() as session:
        names = df.index.to_list()[start:stop]
        urls = df.link.to_list()[start:stop]
        tasks = [asyncio.create_task(chain_processing(name, session, url)) for name, url in zip(names, urls)]
        await asyncio.gather(*tasks)

if __name__=='__main__':
    import time
    batch_size = 600
    dataset_size = 124989 #dataset size hardcoded here- not the best practice
    initialize_error_file()

    s_time = time.time()
    for start in range(0,dataset_size,batch_size): 
        print(f"Running for {start}")
        asyncio.run(main(start=start, stop=start+batch_size))
        time.sleep(30)
    e_time = time.time()
    hours = (e_time - s_time) // 3600
    minutes = (e_time - s_time) // 60 - 60*hours
    seconds = (e_time - s_time) - 3600*hours - 60*minutes
    print(f"All Articles scraped in {hours} hours, {minutes} minutes, and {seconds} seconds")