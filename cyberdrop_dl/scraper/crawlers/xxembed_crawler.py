from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
)
import m3u8_To_MP4
import shutil

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class XXEmbedCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "xxembed", "XXEmbed")
        self.primary_base_domain = URL("https://xxembed.com")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        if scrape_item.url.path.startswith("/embed"):
            await self.video(scrape_item)
        else:
            await self.album(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_BS4_with_referrer(self.domain, scrape_item.url)

            album_id = self.get_album_id(str(scrape_item.url))
            container = soup.select("div[class*=toggleable]")[-1]
            listings = container.select("span[class*=episode]")

            for listing in listings:
                path = listing.get("data-url")

                new_url = scrape_item.url.with_path(path)
                scrape_video = ScrapeItem(new_url, parent_title="", album_id=album_id)
                await self.video(scrape_video)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_BS4_with_referrer(self.domain, scrape_item.url)
            url = self.get_playlist_url(soup)
            file_name = self.get_album_name(str(scrape_item.url)) + ".mp4"
            download_dir = self.get_save_path(scrape_item)

            # for some strange reason it always download file to home directory
            m3u8_To_MP4.multithread_download(url, mp4_file_name=file_name)
            self.move_file(file_name, download_dir)

    def move_file(self, file_name: str, download_dir: str):
        current_path = os.path.join(os.getcwd(), file_name)
        target_path = os.path.join(download_dir, file_name)
        if not os.path.exists(download_dir):
            os.mkdir(download_dir)
        shutil.move(current_path, target_path)

    def get_playlist_url(self, soup: BeautifulSoup):
        scripts = soup.findAll("script")
        for script in scripts:
            if 'jwplayer("vplayer")' in script.text:
                source = re.search(
                    r'(?<=\[\{file:")(.*?)(?="\}\])', script.text.strip()
                )
                return source.group(0)

    def get_album_name(seld, url: str):
        album = url.split("/").pop().split("-").pop().replace(".html", "")
        return album

    def get_save_path(self, scrape_item: ScrapeItem):
        default_download_path = self.manager.path_manager.download_dir

        if not scrape_item.album_id:
            return os.path.join(
                os.getcwd(), default_download_path, "Loose_files_xxembed"
            )
        else:
            return os.path.join(os.getcwd(), default_download_path, scrape_item.album_id)

    def get_album_id(self, url: str):
        return url.split("/").pop()
