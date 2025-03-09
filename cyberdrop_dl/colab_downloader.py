import asyncio
import sys
import traceback
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.scraper.scraper import ScrapeMapper
from cyberdrop_dl.utils.utilities import check_latest_pypi, check_partials_and_empty_folders
from cyberdrop_dl.utils.sorting import Sorter


class ColabDownloader:
    """
    A simplified downloader for Google Colab that avoids the rich UI
    but still shows download progress in a Colab-friendly way.
    """
    
    def __init__(self):
        self.manager = None
        self.last_progress_update = 0
        self.progress_update_interval = 1.0  # Update progress every 1 second
        self.total_files = 0
        self.completed_files = 0
        self.previously_completed_files = 0
        self.skipped_files = 0
        self.failed_files = 0
        self.active_downloads: Dict[str, Dict[str, Any]] = {}
        
    def startup(self) -> Manager:
        """
        Starts the program and returns the manager
        """
        try:
            self.manager = Manager()
            self.manager.startup()
            return self.manager
        except KeyboardInterrupt:
            print("\nExiting...")
            exit(0)
    
    async def runtime(self) -> None:
        """Main runtime loop for the program, this will run until all scraping and downloading is complete"""
        scrape_mapper = ScrapeMapper(self.manager)
        
        # Hook into the progress manager to track downloads
        self._setup_progress_tracking()
        
        # Start the progress display task
        progress_task = asyncio.create_task(self._display_progress())
        
        # Start the scraping and downloading
        async with asyncio.TaskGroup() as task_group:
            self.manager.task_group = task_group
            await scrape_mapper.start()
        
        # Wait for the progress display task to complete
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
    
    def _setup_progress_tracking(self) -> None:
        """Set up hooks to track download progress"""
        # Store original methods
        original_add_completed = self.manager.progress_manager.download_progress.add_completed
        original_add_previously_completed = self.manager.progress_manager.download_progress.add_previously_completed
        original_add_skipped = self.manager.progress_manager.download_progress.add_skipped
        original_add_failed = self.manager.progress_manager.download_progress.add_failed
        original_add_task = self.manager.progress_manager.file_progress.add_task
        original_mark_task_completed = self.manager.progress_manager.file_progress.mark_task_completed
        original_advance_file = self.manager.progress_manager.file_progress.advance_file
        
        # Override methods to track progress
        async def new_add_completed():
            self.completed_files += 1
            await original_add_completed()
        
        async def new_add_previously_completed():
            self.previously_completed_files += 1
            await original_add_previously_completed()
        
        async def new_add_skipped():
            self.skipped_files += 1
            await original_add_skipped()
        
        async def new_add_failed():
            self.failed_files += 1
            await original_add_failed()
        
        async def new_add_task(file: str, expected_size=None):
            self.total_files += 1
            task_id = await original_add_task(file, expected_size)
            self.active_downloads[task_id] = {
                "filename": file,
                "total": expected_size,
                "completed": 0,
                "start_time": time.time()
            }
            return task_id
        
        async def new_mark_task_completed(task_id):
            if task_id in self.active_downloads:
                del self.active_downloads[task_id]
            await original_mark_task_completed(task_id)
        
        async def new_advance_file(task_id, amount):
            if task_id in self.active_downloads:
                self.active_downloads[task_id]["completed"] += amount
            await original_advance_file(task_id, amount)
        
        # Replace the original methods with our tracking methods
        self.manager.progress_manager.download_progress.add_completed = new_add_completed
        self.manager.progress_manager.download_progress.add_previously_completed = new_add_previously_completed
        self.manager.progress_manager.download_progress.add_skipped = new_add_skipped
        self.manager.progress_manager.download_progress.add_failed = new_add_failed
        self.manager.progress_manager.file_progress.add_task = new_add_task
        self.manager.progress_manager.file_progress.mark_task_completed = new_mark_task_completed
        self.manager.progress_manager.file_progress.advance_file = new_advance_file
    
    async def _display_progress(self) -> None:
        """Display download progress in a Colab-friendly way"""
        while True:
            current_time = time.time()
            if current_time - self.last_progress_update >= self.progress_update_interval:
                self.last_progress_update = current_time
                
                # Clear previous output (don't use too many newlines to avoid lag)
                sys.stdout.write("\r\033[K")  # Clear current line
                
                # Print overall progress
                total_progress = f"Progress: {self.completed_files}/{self.total_files} files"
                if self.previously_completed_files > 0:
                    total_progress += f" | Previously Downloaded: {self.previously_completed_files}"
                if self.skipped_files > 0:
                    total_progress += f" | Skipped: {self.skipped_files}"
                if self.failed_files > 0:
                    total_progress += f" | Failed: {self.failed_files}"
                
                print(total_progress)
                
                # Print active downloads (limit to 3 to avoid lag)
                active_count = 0
                for task_id, download in list(self.active_downloads.items())[:3]:
                    filename = Path(download["filename"]).name
                    completed = download["completed"]
                    total = download["total"]
                    
                    if total:
                        percentage = (completed / total) * 100 if total > 0 else 0
                        progress_bar = self._create_progress_bar(percentage)
                        elapsed = time.time() - download["start_time"]
                        speed = completed / elapsed if elapsed > 0 else 0
                        
                        # Format sizes
                        completed_str = self._format_size(completed)
                        total_str = self._format_size(total)
                        speed_str = self._format_size(speed) + "/s"
                        
                        print(f"{filename[:40]}... {progress_bar} {percentage:.1f}% | {completed_str}/{total_str} | {speed_str}")
                    else:
                        # If total is None, just show the completed size
                        completed_str = self._format_size(completed)
                        elapsed = time.time() - download["start_time"]
                        speed = completed / elapsed if elapsed > 0 else 0
                        speed_str = self._format_size(speed) + "/s"
                        
                        print(f"{filename[:40]}... {completed_str} | {speed_str}")
                    
                    active_count += 1
                
                # Show how many more active downloads there are
                remaining_active = len(self.active_downloads) - active_count
                if remaining_active > 0:
                    print(f"... and {remaining_active} more downloads in progress")
                
                sys.stdout.flush()
            
            await asyncio.sleep(0.1)  # Small sleep to avoid CPU hogging
    
    def _create_progress_bar(self, percentage: float, width: int = 20) -> str:
        """Create a simple ASCII progress bar"""
        filled_width = int(width * percentage / 100)
        return f"[{'#' * filled_width}{'-' * (width - filled_width)}]"
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f}MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f}GB"
    
    async def director(self) -> None:
        """Runs the program and handles the progress display"""
        configs = self.manager.config_manager.get_configs()
        configs_ran = []
        self.manager.path_manager.startup()
        self.manager.log_manager.startup()
        
        while True:
            if self.manager.args_manager.all_configs:
                print(f"Picking new config...")
                
                configs_to_run = list(set(configs) - set(configs_ran))
                configs_to_run.sort()
                self.manager.config_manager.change_config(configs_to_run[0])
                configs_ran.append(configs_to_run[0])
                print(f"Changing config to {configs_to_run[0]}...")
            
            print(f"Starting Async Processes...")
            await self.manager.async_startup()
            
            print(f"Starting Download...")
            try:
                await self.runtime()
            except Exception as e:
                print("\nAn error occurred, please report this to the developer")
                print(e)
                print(traceback.format_exc())
                exit(1)
            
            print(f"\nRunning Post-Download Processes For Config: {self.manager.config_manager.loaded_config}...")
            if isinstance(self.manager.args_manager.sort_downloads, bool):
                if self.manager.args_manager.sort_downloads:
                    sorter = Sorter(self.manager)
                    await sorter.sort()
            elif self.manager.config_manager.settings_data['Sorting']['sort_downloads'] and not self.manager.args_manager.retry:
                sorter = Sorter(self.manager)
                await sorter.sort()
            
            await check_partials_and_empty_folders(self.manager)
            
            if self.manager.config_manager.settings_data['Runtime_Options']['update_last_forum_post']:
                print("Updating Last Forum Post...")
                await self.manager.log_manager.update_last_forum_post()
            
            print("Printing Stats...")
            await self.print_stats()
            
            print("Checking for Program End...")
            if not self.manager.args_manager.all_configs or not list(set(configs) - set(configs_ran)):
                break
            await asyncio.sleep(5)
        
        print("Checking for Updates...")
        await check_latest_pypi()
        
        print("Closing Program...")
        await self.manager.close()
        
        print("\nFinished downloading. Enjoy :)")
    
    async def print_stats(self) -> None:
        """Prints the stats of the program"""
        print("\nDownload Stats:")
        print(f"Downloaded {self.completed_files} files")
        print(f"Previously Downloaded {self.previously_completed_files} files")
        print(f"Skipped By Config {self.skipped_files} files")
        print(f"Failed {self.manager.progress_manager.download_stats_progress.failed_files} files")
        
        scrape_failures = await self.manager.progress_manager.scrape_stats_progress.return_totals()
        print("\nScrape Failures:")
        for key, value in scrape_failures.items():
            print(f"Scrape Failures ({key}): {value}")
        
        download_failures = await self.manager.progress_manager.download_stats_progress.return_totals()
        print("\nDownload Failures:")
        for key, value in download_failures.items():
            print(f"Download Failures ({key}): {value}")


def main():
    """Main entry point for the Colab downloader"""
    downloader = ColabDownloader()
    manager = downloader.startup()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        asyncio.run(downloader.director())
    except KeyboardInterrupt:
        print("\nTrying to Exit...")
        try:
            asyncio.run(manager.close())
        except Exception:
            pass
        exit(1)
    loop.close()
    sys.exit(0)


if __name__ == '__main__':
    main()