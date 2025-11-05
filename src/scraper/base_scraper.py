# region: Script Description
# This is our Basic Scraper, upon which we will implement code for scraping using the data from the seed files,
# implement BFS and thread-level parallelization in the base_scraper.py file.
# 
# endregion

# region: Importing Required Libraries and Setting Up Environment Variables
import requests 
from bs4 import BeautifulSoup  
import threading
import queue
import time
import json
import os
import sys
import logging
# endregion

class Scraper:

    # region: Initialization
    def __init__(self):
        seed_urls=self.load_seed(file_path="data/forbes_ai50_seed.json")

    # endregion

    # region: Loading Seed
    def load_seed(self, file_path: str):
        with open(file_path, "r") as file:
            return json.load(file)
        

    # endregion

    # region: Scraping
    def scrape(self):
        pass

    # endregion

    # region: Crawling
    def crawl(self,url:str):
        pass
    # endregion