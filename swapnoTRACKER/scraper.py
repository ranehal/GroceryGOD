import os
from datetime import timezone, timedelta
DHAKA_TZ = timezone(timedelta(hours=6))
"""Shwapno Web Scraper Runner
Authoritative entry point for Kaggle orchestrator (scratch.py) and local pipelines.
"""
import os
import sys
import asyncio

# Ensure swapnoTRACKER is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from scraper_web import main

if __name__ == '__main__':
    asyncio.run(main())
