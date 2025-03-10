import asyncio
import sys
import traceback
import time
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import os

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
        self.progress_update_interval = 5.0
        self.total_files = 0
        self.completed_files = 0
        self.previously_completed_files = 0
        self.skipped_files = 0
        self.failed_files = 0
        self.active_downloads: Dict[str, Dict[str, Any]] = {}
        self.max_concurrent_downloads = 20  
        self.verbose_logging = False
        self.stall_threshold = 300.0
        self.retry_attempts = {}
        self.max_retries = 3
        
        # Initialize download limit tracking
        self.current_download_limit = 10  # Default limit
        self.current_domain_limit = 3     # Default domain limit
        self.active_domain_counts = {}    # Track active downloads per domain
        
        # Track temporary domain limits
        self.temp_domain_limits = {}      # Temporary increased limits for domains
        
        # Semaphores for strict download limits
        self.global_download_semaphore = None  # Will be initialized in _apply_download_limits
        self.domain_semaphores = {}            # Domain-specific semaphores
        
        # Queue for pending downloads
        self.download_queue = []
        self.is_processing_queue = False
        
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
        
        self._setup_progress_tracking()
        
        self._apply_download_limits()
        
        progress_task = asyncio.create_task(self._display_progress())
        
        stalled_checker_task = asyncio.create_task(self._check_stalled_downloads())
        
        heartbeat_task = asyncio.create_task(self._heartbeat())
        
        # Add a task to enforce download limits
        limit_enforcer_task = asyncio.create_task(self._enforce_download_limits())
        
        # Add a task to process the download queue
        queue_processor_task = asyncio.create_task(self._process_download_queue())
        
        async with asyncio.TaskGroup() as task_group:
            self.manager.task_group = task_group
            await scrape_mapper.start()
        
        progress_task.cancel()
        stalled_checker_task.cancel()
        heartbeat_task.cancel()
        limit_enforcer_task.cancel()
        queue_processor_task.cancel()
        try:
            await progress_task
            await stalled_checker_task
            await heartbeat_task
            await limit_enforcer_task
            await queue_processor_task
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
            if self.verbose_logging:
                self.force_print(f"File completed: Total completed = {self.completed_files}")
            await original_add_completed()
        
        async def new_add_previously_completed():
            self.previously_completed_files += 1
            if self.verbose_logging:
                self.force_print(f"File previously completed: Total = {self.previously_completed_files}")
            await original_add_previously_completed()
        
        async def new_add_skipped():
            self.skipped_files += 1
            if self.verbose_logging:
                self.force_print(f"File skipped: Total skipped = {self.skipped_files}")
            await original_add_skipped()
        
        async def new_add_failed():
            self.failed_files += 1
            if self.verbose_logging:
                self.force_print(f"File failed: Total failed = {self.failed_files}")
            await original_add_failed()
        
        async def new_add_task(file: str, expected_size=None):
            self.total_files += 1
            
            # Extract domain from filename (format is typically "(DOMAIN) filename")
            domain = None
            domain_match = re.match(r'\(([^)]+)\)', file)
            if domain_match:
                domain = domain_match.group(1).lower()
            
            # Check if we're at or over the download limits
            at_global_limit = len(self.active_downloads) >= self.current_download_limit
            at_domain_limit = False
            
            if domain:
                domain_count = self.active_domain_counts.get(domain, 0)
                at_domain_limit = domain_count >= self.current_domain_limit
            
            if at_global_limit or at_domain_limit:
                # We're at a limit, queue this download instead of starting it immediately
                if self.verbose_logging or len(self.download_queue) % 10 == 0:  # Log every 10th queued download
                    if at_global_limit:
                        self.force_print(f"Queuing download (global limit reached): {file}")
                    else:
                        self.force_print(f"Queuing download (domain limit reached for {domain}): {file}")
                
                # Get the original task ID from the progress manager
                task_id = await original_add_task(file, expected_size)
                
                # Add to queue
                self.download_queue.append({
                    "file": file,
                    "expected_size": expected_size,
                    "domain": domain,
                    "task_id": task_id
                })
                
                # Return the task ID
                return task_id
            
            # If we're not at a limit, proceed with the download
            if self.verbose_logging:
                self.force_print(f"New download: {file} (size: {self._format_size(expected_size) if expected_size else 'unknown'})")
            
            # Get the task ID from the progress manager
            task_id = await original_add_task(file, expected_size)
            
            # Add to active downloads
            self.active_downloads[task_id] = {
                "filename": file,
                "total": expected_size,
                "completed": 0,
                "start_time": time.time(),
                "last_update_time": time.time(),
                "domain": domain
            }
            
            # Update domain counts
            if domain:
                if domain not in self.active_domain_counts:
                    self.active_domain_counts[domain] = 0
                self.active_domain_counts[domain] += 1
            
            return task_id
        
        async def new_mark_task_completed(task_id):
            if task_id in self.active_downloads:
                filename = self.active_downloads[task_id]["filename"]
                domain = self.active_downloads[task_id].get("domain")
                
                # Only log if verbose logging is enabled
                if self.verbose_logging:
                    self.force_print(f"Download completed: {Path(filename).name}")
                
                # Remove from active downloads
                del self.active_downloads[task_id]
                
                # Update domain counts
                if domain and domain in self.active_domain_counts:
                    self.active_domain_counts[domain] = max(0, self.active_domain_counts[domain] - 1)
                
                # Remove from retry attempts if it was being retried
                if task_id in self.retry_attempts:
                    del self.retry_attempts[task_id]
                
                # Increment completed files counter
                self.completed_files += 1
                
                # Process the download queue to start new downloads if possible
                asyncio.create_task(self._process_download_queue())
            
            await original_mark_task_completed(task_id)
        
        async def new_advance_file(task_id, amount):
            try:
                if task_id in self.active_downloads:
                    # Store the previous completed amount for stall detection
                    previous_completed = self.active_downloads[task_id].get("completed", 0)
                    previous_update_time = self.active_downloads[task_id].get("last_update_time", time.time())
                    
                    # Update the completed amount and last update time
                    self.active_downloads[task_id]["completed"] += amount
                    current_time = time.time()
                    self.active_downloads[task_id]["last_update_time"] = current_time
                    
                    # Store progress information for stall detection
                    self.active_downloads[task_id]["last_progress_amount"] = amount
                    self.active_downloads[task_id]["last_progress_time"] = current_time
                    
                    # Calculate and store download speed
                    time_diff = current_time - previous_update_time
                    if time_diff > 0:
                        speed = amount / time_diff
                        self.active_downloads[task_id]["current_speed"] = speed
                    
                    # Debug logging for download progress
                    if self.active_downloads[task_id]["completed"] == amount:  # First progress update
                        filename = Path(self.active_downloads[task_id]["filename"]).name
                        self.force_print(f"🔄 Download started: {filename} - received first {self._format_size(amount)} of data")
                    
                    # Only log progress for large files at major milestones if verbose logging is enabled
                    if self.verbose_logging:
                        completed = self.active_downloads[task_id]["completed"]
                        total = self.active_downloads[task_id]["total"]
                        filename = Path(self.active_downloads[task_id]["filename"]).name
                        
                        # Log progress for large files at certain thresholds
                        if total and total > 10*1024*1024:  # For files > 10MB
                            percentage = (completed / total) * 100
                            if percentage % 25 < 1 and percentage > 1:  # Log at ~25%, 50%, 75% only
                                self.force_print(f"Progress: {filename} - {percentage:.1f}% ({self._format_size(completed)}/{self._format_size(total)})")
            except Exception as e:
                if self.verbose_logging:
                    self.force_print(f"Error in new_advance_file: {e}")
            
            await original_advance_file(task_id, amount)
        
        self.manager.progress_manager.download_progress.add_completed = new_add_completed
        self.manager.progress_manager.download_progress.add_previously_completed = new_add_previously_completed
        self.manager.progress_manager.download_progress.add_skipped = new_add_skipped
        self.manager.progress_manager.download_progress.add_failed = new_add_failed
        self.manager.progress_manager.file_progress.add_task = new_add_task
        self.manager.progress_manager.file_progress.mark_task_completed = new_mark_task_completed
        self.manager.progress_manager.file_progress.advance_file = new_advance_file
    
    async def _display_progress(self) -> None:
        """Display download progress in a Colab-friendly way"""
        last_completed = self.completed_files
        last_completed_time = time.time()
        
        while True:
            try:
                current_time = time.time()
                if current_time - self.last_progress_update >= self.progress_update_interval:
                    self.last_progress_update = current_time
                    
                    # Calculate overall download speed
                    elapsed_since_last = current_time - last_completed_time
                    files_completed_since_last = self.completed_files - last_completed
                    
                    if elapsed_since_last >= 5.0:  # Update stats every 5 seconds
                        last_completed = self.completed_files
                        last_completed_time = current_time
                    
                    # Print a summary of the current downloads
                    await self._print_download_summary("Progress Update")
                    
                    # Add files per minute if we have data
                    if elapsed_since_last >= 5.0 and files_completed_since_last > 0:
                        files_per_minute = (files_completed_since_last / elapsed_since_last) * 60
                        self.force_print(f"Download rate: {files_per_minute:.1f} files/min")
                    
                    # Print active downloads (limit to 5 to avoid lag)
                    active_count = 0
                    stalled_count = 0
                    queued_count = 0
                    
                    # Get a copy of active downloads to avoid modification during iteration
                    active_downloads = list(self.active_downloads.items())
                    
                    # Categorize downloads
                    truly_active = []
                    queued = []
                    stalled = []
                    
                    for task_id, download in active_downloads:
                        # Check if download is complete
                        completed = download.get("completed", 0)
                        total = download.get("total", None)
                        if total and completed >= total:
                            # This download is complete, don't categorize it
                            continue
                            
                        # Check for stalled downloads using the same logic as _check_stalled_downloads
                        is_stalled = False
                        
                        # 1. Check if there's been any progress update recently
                        last_progress_time = download.get("last_progress_time", download.get("last_update_time", download["start_time"]))
                        time_since_progress = current_time - last_progress_time
                        
                        # 2. Check if the download speed has dropped significantly
                        current_speed = download.get("current_speed", 0)
                        
                        # 3. Check if we're near the end of the download
                        near_completion = total and completed > 0.95 * total
                        
                        # Determine if the download is stalled based on these factors
                        if time_since_progress > self.stall_threshold and not near_completion:
                            is_stalled = True
                            download["stall_reason"] = f"No progress for {time_since_progress:.1f}s"
                        # Only consider slow downloads as stalled if they're really slow and have been that way for a while
                        elif current_speed < 50 and time_since_progress > self.stall_threshold and not near_completion:
                            # For large files (>100MB), be more lenient
                            if not (total and total > 100*1024*1024 and completed < 0.5 * total):
                                is_stalled = True
                                download["stall_reason"] = f"Speed too low ({self._format_size(current_speed)}/s) for {time_since_progress:.1f}s"
                        
                        if is_stalled:
                            stalled.append((task_id, download))
                            stalled_count += 1
                        elif time_since_progress <= 10.0:  # Active in the last 10 seconds
                            truly_active.append((task_id, download))
                            active_count += 1
                        else:  # In between - likely queued or slow
                            queued.append((task_id, download))
                            queued_count += 1
                    
                    # Sort each category by activity (most recently active first)
                    truly_active.sort(
                        key=lambda x: x[1].get("last_update_time", 0) if "last_update_time" in x[1] else x[1]["start_time"],
                        reverse=True
                    )
                    
                    # Display active downloads
                    if truly_active:
                        self.force_print("\nActive downloads:")
                        for task_id, download in truly_active[:5]:  # Show up to 5 active downloads
                            self._print_download_item("⬇️", download, current_time)
                    
                    # Display queued downloads if any
                    if queued and len(queued) <= 5:  # Only show if there are 5 or fewer to avoid clutter
                        self.force_print("\nQueued downloads:")
                        for task_id, download in queued[:3]:  # Show up to 3 queued downloads
                            self._print_download_item("⏳", download, current_time)
                    
                    # Display stalled downloads if any
                    if stalled:
                        self.force_print("\nStalled downloads:")
                        for task_id, download in stalled[:3]:  # Show up to 3 stalled downloads
                            self._print_download_item("⚠️", download, current_time, is_stalled=True)
                    
                    # Show a summary if there are more downloads than we displayed
                    total_shown = min(5, len(truly_active)) + min(3, len(queued)) + min(3, len(stalled))
                    total_downloads = len(active_downloads)
                    
                    if total_shown < total_downloads:
                        self.force_print(f"\n... and {total_downloads - total_shown} more downloads in progress")
                
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.force_print(f"Error in progress display: {e}")
                await asyncio.sleep(1)
    
    def _print_download_item(self, status_indicator, download, current_time, is_stalled=False):
        """Helper method to print a download item with consistent formatting"""
        try:
            filename = Path(download["filename"]).name
            completed = download.get("completed", 0)
            total = download.get("total", None)
            
            if total:
                percentage = (completed / total) * 100 if total > 0 else 0
                
                # If download is 100% complete, override the status indicator
                if percentage >= 100:
                    status_indicator = "✅"  # Checkmark for completed downloads
                    is_stalled = False  # Don't show stalled message for completed downloads
                
                progress_bar = self._create_progress_bar(percentage)
                elapsed = current_time - download["start_time"]
                speed = completed / elapsed if elapsed > 0 else 0
                
                # Use current speed if available
                current_speed = download.get("current_speed", 0)
                if current_speed > 0:
                    speed = current_speed
                
                # Format sizes
                completed_str = self._format_size(completed)
                total_str = self._format_size(total)
                speed_str = self._format_size(speed) + "/s"
                
                self.force_print(f"{status_indicator} {filename[:40]}... {progress_bar} {percentage:.1f}% | {completed_str}/{total_str} | {speed_str}")
                if is_stalled:
                    stall_reason = download.get("stall_reason", "No recent progress")
                    self.force_print(f"   Stalled: {stall_reason}")
            else:
                # If total is None, just show the completed size
                completed_str = self._format_size(completed)
                elapsed = current_time - download["start_time"]
                speed = completed / elapsed if elapsed > 0 else 0
                
                # Use current speed if available
                current_speed = download.get("current_speed", 0)
                if current_speed > 0:
                    speed = current_speed
                
                speed_str = self._format_size(speed) + "/s"
                
                self.force_print(f"{status_indicator} {filename[:40]}... {completed_str} | {speed_str}")
                if is_stalled:
                    stall_reason = download.get("stall_reason", "No recent progress")
                    self.force_print(f"   Stalled: {stall_reason}")
        except Exception:
            pass
    
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

    async def _check_stalled_downloads(self) -> None:
        """Check for stalled downloads and handle them"""
        # Wait a bit before starting to check for stalled downloads
        await asyncio.sleep(60)  # Increased from 30
        
        while True:
            current_time = time.time()
            stalled_downloads = []
            
            # Find downloads that haven't made progress in a while
            for task_id, download in list(self.active_downloads.items()):
                # First check if download is complete
                completed = download.get("completed", 0)
                total = download.get("total", None)
                
                if total and completed >= total:
                    # This download is complete, schedule it for removal
                    self.force_print(f"✅ Auto-completing download: {Path(download['filename']).name}")
                    self.completed_files += 1
                    await self._remove_completed_download(task_id)
                    continue
                
                # Check if the download is stalled using multiple indicators
                is_stalled = False
                stall_reason = ""
                
                # 1. Check if there's been any progress update recently
                last_progress_time = download.get("last_progress_time", download.get("last_update_time", download["start_time"]))
                time_since_progress = current_time - last_progress_time
                
                # 2. Check if the download speed has dropped significantly
                current_speed = download.get("current_speed", 0)
                
                # 3. Check if we're near the end of the download (sometimes servers slow down at the end)
                near_completion = total and completed > 0.95 * total
                
                # Determine if the download is stalled based on these factors
                if time_since_progress > self.stall_threshold and not near_completion:
                    is_stalled = True
                    download["stall_reason"] = f"No progress for {time_since_progress:.1f}s"
                # Only consider slow downloads as stalled if they're really slow and have been that way for a while
                elif current_speed < 50 and time_since_progress > self.stall_threshold and not near_completion:
                    # For large files (>100MB), be more lenient
                    if not (total and total > 100*1024*1024 and completed < 0.5 * total):
                        is_stalled = True
                        download["stall_reason"] = f"Speed too low ({self._format_size(current_speed)}/s) for {time_since_progress:.1f}s"
                
                # If the download is stalled, check if the file exists and is complete
                if is_stalled:
                    try:
                        download_dir = self.manager.path_manager.download_dir
                        filename = Path(download["filename"]).name
                        potential_file = Path(download_dir) / filename
                        
                        if potential_file.exists():
                            # If the file exists and is the expected size, mark it as complete
                            if total and potential_file.stat().st_size >= total:
                                self.force_print(f"✅ File exists and is complete: {filename}")
                                self.completed_files += 1
                                await self._remove_completed_download(task_id)
                                continue
                    except Exception:
                        # If there's an error checking the file, just continue with stall detection
                        pass
                    
                    # Add to stalled downloads with the reason
                    stalled_downloads.append(task_id)
            
            # Retry stalled downloads
            if stalled_downloads:
                await self._retry_stalled_downloads(stalled_downloads)
                
                # Log stalled downloads only if there are a significant number
                if len(stalled_downloads) > 5:
                    await self._print_download_summary(f"Found {len(stalled_downloads)} stalled downloads")
                    
                    # For now, we'll just log them - in a future version we could implement retry logic
                    self.force_print("\nStalled downloads:")
                    for i, task_id in enumerate(stalled_downloads[:3]):  # Show only first 3 to avoid spam (reduced from 5)
                        download = self.active_downloads[task_id]
                        filename = Path(download["filename"]).name
                        time_stalled = current_time - download.get("last_update_time", download["start_time"])
                        completed = download.get("completed", 0)
                        total = download.get("total", None)
                        
                        if total:
                            percentage = (completed / total) * 100 if total > 0 else 0
                            self.force_print(f"{i+1}. {filename[:40]} - {percentage:.1f}% ({self._format_size(completed)}/{self._format_size(total)})")
                        else:
                            self.force_print(f"{i+1}. {filename[:40]} - {self._format_size(completed)}")
                        self.force_print(f"   ⚠️ Stalled for {time_stalled:.1f}s")
                    
                    # Suggest solutions
                    self.force_print("\nPossible solutions:")
                    self.force_print("  - Reduce the number of concurrent downloads with --max-downloads 10 --max-per-domain 3")
                    self.force_print("  - Check your internet connection")
                    self.force_print("  - The server might be rate limiting you, try again later")
            
            # Check every 60 seconds (increased from 30)
            await asyncio.sleep(60)
            
    async def _retry_stalled_downloads(self, stalled_downloads: List[str]) -> None:
        """Retry stalled downloads"""
        for task_id in stalled_downloads:
            if task_id not in self.active_downloads:
                continue
                
            # Get the download info
            download = self.active_downloads[task_id]
            filename = Path(download["filename"]).name
            
            # Check if the download is actually complete
            completed = download.get("completed", 0)
            total = download.get("total", None)
            if total and completed >= total:
                # This download is complete, don't retry it
                self.force_print(f"✅ Download already complete for {filename}, removing from active downloads")
                await self._remove_completed_download(task_id)
                continue
                
            # Check if we're near the end of the download (sometimes servers slow down at the end)
            near_completion = total and completed > 0.95 * total
            if near_completion:
                # Don't retry downloads that are almost complete
                self.force_print(f"⏳ Download almost complete for {filename} ({completed/total:.1%}), not retrying")
                continue
            
            # Check if we've already retried this download too many times
            retry_count = self.retry_attempts.get(task_id, 0)
            if retry_count >= self.max_retries:
                self.force_print(f"⚠️ Maximum retries reached for {filename}, giving up")
                continue
                
            # Increment retry count
            self.retry_attempts[task_id] = retry_count + 1
            
            # Log the retry with the stall reason
            stall_reason = download.get("stall_reason", "Unknown reason")
            self.force_print(f"🔄 Retrying download for {filename} (attempt {retry_count + 1}/{self.max_retries})")
            self.force_print(f"   Reason: {stall_reason}")
            
            try:
                # Get the media item from the download
                media_item = None
                domain = None
                
                # Extract domain from the filename (format is typically "(DOMAIN) filename")
                domain_match = re.match(r'\(([^)]+)\)', filename)
                if domain_match:
                    domain_str = domain_match.group(1).lower()
                    # Map the display domain to the actual domain key used in _download_instances
                    domain_map = {
                        "pd.cybar.xyz": "pd.cybar.xyz",
                        "pixeldrain": "pixeldrain",
                        "no_crawler": "no_crawler"
                    }
                    domain = domain_map.get(domain_str, domain_str)
                
                # If we found a domain, look for the media item in that specific downloader
                if domain and domain in self.manager.download_manager._download_instances:
                    downloader = self.manager.download_manager._download_instances[domain]
                    for item in downloader.processed_items:
                        if hasattr(item, 'task_id') and item.task_id == task_id:
                            media_item = item
                            break
                else:
                    # Fall back to checking all downloaders
                    for d, downloader in self.manager.download_manager._download_instances.items():
                        for item in downloader.processed_items:
                            if hasattr(item, 'task_id') and item.task_id == task_id:
                                media_item = item
                                domain = d
                                break
                        if media_item:
                            break
                
                if media_item and domain:
                    # Reset the download
                    self.force_print(f"🔄 Restarting download for {filename}")
                    
                    # Update the last update time to avoid immediate re-stalling
                    self.active_downloads[task_id]["last_update_time"] = time.time()
                    
                    # Create a task to retry the download
                    self.manager.task_group.create_task(
                        self.manager.download_manager._download_instances[domain].download(media_item)
                    )
                else:
                    # Check if the file already exists on disk (might have completed but not been marked)
                    download_dir = self.manager.path_manager.download_dir
                    potential_file = Path(download_dir) / Path(filename).name
                    if potential_file.exists():
                        self.force_print(f"✅ File already exists on disk for {filename}, marking as completed")
                        await self._remove_completed_download(task_id)
                    else:
                        self.force_print(f"❌ Could not find media item for {filename}, cannot retry")
            except Exception as e:
                self.force_print(f"❌ Error retrying download for {filename}: {e}")

    async def _remove_completed_download(self, task_id: str) -> None:
        """Remove a completed download from the active downloads list"""
        if task_id in self.active_downloads:
            # Small delay to ensure any pending updates are processed
            await asyncio.sleep(1)
            if task_id in self.active_downloads:
                filename = Path(self.active_downloads[task_id]["filename"]).name
                
                # Update domain counts if available
                domain = self.active_downloads[task_id].get("domain")
                if domain and domain in self.active_domain_counts:
                    self.active_domain_counts[domain] = max(0, self.active_domain_counts[domain] - 1)
                
                # Remove from active downloads
                del self.active_downloads[task_id]
                self.force_print(f"Removed completed download {filename} from active downloads")
                
                # Also remove from retry attempts if it was being retried
                if task_id in self.retry_attempts:
                    del self.retry_attempts[task_id]
                    
                # Process the download queue to start new downloads if possible
                asyncio.create_task(self._process_download_queue())

    def _apply_download_limits(self) -> None:
        """Apply download limits to avoid overwhelming servers"""
        # Set a reasonable limit for concurrent downloads
        global_settings = self.manager.config_manager.global_settings_data
        
        # Check if the user has specified a max_simultaneous_downloads value
        if 'Rate_Limiting_Options' in global_settings and 'max_simultaneous_downloads' in global_settings['Rate_Limiting_Options']:
            user_limit = global_settings['Rate_Limiting_Options']['max_simultaneous_downloads']
            # If the user limit is higher than our default, use our default
            if user_limit > self.max_concurrent_downloads:
                self.force_print(f"⚠️ Limiting concurrent downloads to {self.max_concurrent_downloads} to avoid Colab lag")
                self.force_print(f"   (Your setting was {user_limit})")
                global_settings['Rate_Limiting_Options']['max_simultaneous_downloads'] = self.max_concurrent_downloads
            
            # Store the limit for our own tracking
            self.current_download_limit = global_settings['Rate_Limiting_Options']['max_simultaneous_downloads']
            
            # Initialize the global semaphore for strict download limits
            self.global_download_semaphore = asyncio.Semaphore(self.current_download_limit)
            
            # Recreate the download_session_limit with the new value
            self.manager.client_manager.download_session_limit = asyncio.Semaphore(
                global_settings['Rate_Limiting_Options']['max_simultaneous_downloads']
            )
            self.force_print(f"✅ Set maximum concurrent downloads to {global_settings['Rate_Limiting_Options']['max_simultaneous_downloads']}")
            
        # Also limit per-domain downloads
        if 'Rate_Limiting_Options' in global_settings and 'max_simultaneous_downloads_per_domain' in global_settings['Rate_Limiting_Options']:
            domain_limit = global_settings['Rate_Limiting_Options']['max_simultaneous_downloads_per_domain']
            # Set a reasonable per-domain limit
            if domain_limit > 5:
                self.force_print(f"⚠️ Limiting per-domain concurrent downloads to 5 to avoid rate limiting")
                self.force_print(f"   (Your setting was {domain_limit})")
                global_settings['Rate_Limiting_Options']['max_simultaneous_downloads_per_domain'] = 5
            
            # Store the domain limit for our own tracking
            self.current_domain_limit = global_settings['Rate_Limiting_Options']['max_simultaneous_downloads_per_domain']

    async def _heartbeat(self) -> None:
        """Print a heartbeat message periodically to show the downloader is still running"""
        while True:
            await asyncio.sleep(60)
            await self._print_download_summary("Heartbeat")

    def force_print(self, *args, **kwargs):
        """Force print to ensure output is visible in Colab"""
        print(*args, **kwargs, flush=True)
        
    async def _print_download_summary(self, reason: str) -> None:
        """Print a summary of the current downloads"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.force_print(f"\n[{timestamp}] {reason} - Download Summary")
        
        # Get the configured download limits
        max_downloads = self.current_download_limit
        max_per_domain = self.current_domain_limit
        
        # Count truly active vs. stalled downloads
        active_count = 0
        stalled_count = 0
        queued_count = 0
        
        # Count domains
        domain_counts = {}
        
        current_time = time.time()
        for task_id, download in self.active_downloads.items():
            # Update domain counts
            domain = download.get("domain")
            if domain:
                if domain not in domain_counts:
                    domain_counts[domain] = 0
                domain_counts[domain] += 1
            
            last_update = download.get("last_update_time", download["start_time"])
            time_since_update = current_time - last_update
            
            if time_since_update <= 10.0:  # Active in the last 10 seconds
                active_count += 1
            elif time_since_update > self.stall_threshold:  # Stalled
                stalled_count += 1
            else:  # In between - likely queued or slow
                queued_count += 1
        
        # Update our tracking of active domain counts
        self.active_domain_counts = domain_counts
        
        # Count domains in the queue
        queue_domain_counts = {}
        for item in self.download_queue:
            domain = item.get("domain")
            if domain:
                if domain not in queue_domain_counts:
                    queue_domain_counts[domain] = 0
                queue_domain_counts[domain] += 1
        
        self.force_print(f"Progress: {self.completed_files}/{self.total_files} files")
        
        # Show queue information
        if self.download_queue:
            self.force_print(f"Queue: {len(self.download_queue)} downloads waiting")
            
            # Show queue by domain if there are multiple domains
            if len(queue_domain_counts) > 1 or len(self.download_queue) > 10:
                self.force_print("Queue by domain:")
                for domain, count in sorted(queue_domain_counts.items(), key=lambda x: x[1], reverse=True):
                    active_for_domain = domain_counts.get(domain, 0)
                    temp_limit = self.temp_domain_limits.get(domain, max_per_domain)
                    limit_str = f"{temp_limit}" if temp_limit != max_per_domain else f"{max_per_domain}"
                    self.force_print(f"  {domain}: {count} queued, {active_for_domain}/{limit_str} active")
        
        # Show warning if exceeding limits
        if len(self.active_downloads) > max_downloads:
            self.force_print(f"⚠️ WARNING: {len(self.active_downloads)} active downloads exceeds limit of {max_downloads}")
            self.force_print(f"   This may cause performance issues or crashes")
        
        self.force_print(f"Download limits: {active_count}/{max_downloads} active (max {max_downloads}, {max_per_domain} per domain)")
        
        # Show domains with temporary limits
        if self.temp_domain_limits:
            self.force_print("Domain limits:")
            for domain, limit in sorted(self.temp_domain_limits.items()):
                if limit != max_per_domain:
                    active_for_domain = domain_counts.get(domain, 0)
                    self.force_print(f"  {domain}: {active_for_domain}/{limit} active (temporary limit)")
        
        # Show domain counts if any domain exceeds the limit
        domains_exceeding_limit = {}
        for domain, count in domain_counts.items():
            domain_limit = self.temp_domain_limits.get(domain, max_per_domain)
            if count > domain_limit:
                domains_exceeding_limit[domain] = (count, domain_limit)
                
        if domains_exceeding_limit:
            self.force_print(f"⚠️ Domains exceeding limit:")
            for domain, (count, limit) in domains_exceeding_limit.items():
                self.force_print(f"   {domain}: {count}/{limit}")
        
        if self.previously_completed_files > 0 or self.skipped_files > 0 or self.failed_files > 0:
            status_parts = []
            if self.previously_completed_files > 0:
                status_parts.append(f"Previously: {self.previously_completed_files}")
            if self.skipped_files > 0:
                status_parts.append(f"Skipped: {self.skipped_files}")
            if self.failed_files > 0:
                status_parts.append(f"Failed: {self.failed_files}")
            self.force_print(f"Status: {' | '.join(status_parts)}")
        
        # Print detailed download status
        if self.active_downloads:
            self.force_print(f"Downloads: Active: {active_count}, Queued: {queued_count}, Stalled: {stalled_count}, Total: {len(self.active_downloads)}")
            
            # Print the most recently active downloads (only if there are active downloads)
            if active_count > 0:
                active_downloads = sorted(
                    self.active_downloads.items(),
                    key=lambda x: x[1].get("last_update_time", 0) if "last_update_time" in x[1] else x[1]["start_time"],
                    reverse=True
                )
                
                # Filter to only show active (non-stalled) downloads
                active_downloads = [(task_id, download) for task_id, download in active_downloads 
                                   if (time.time() - download.get("last_update_time", download["start_time"])) <= 10.0]
                
                if active_downloads:
                    self.force_print("\nMost recently active downloads:")
                    for i, (task_id, download) in enumerate(active_downloads[:2]):  # Show only 2 most active downloads
                        try:
                            filename = Path(download["filename"]).name
                            completed = download.get("completed", 0)
                            total = download.get("total", None)
                            
                            if total:
                                percentage = (completed / total) * 100 if total > 0 else 0
                                self.force_print(f"{i+1}. {filename[:40]} - {percentage:.1f}% ({self._format_size(completed)}/{self._format_size(total)})")
                            else:
                                self.force_print(f"{i+1}. {filename[:40]} - {self._format_size(completed)}")
                        except Exception:
                            pass

    async def _enforce_download_limits(self) -> None:
        """Periodically check and enforce download limits"""
        # Wait a bit before starting to enforce limits
        await asyncio.sleep(30)
        
        while True:
            try:
                # Check if we're exceeding the total download limit
                if len(self.active_downloads) > self.current_download_limit:
                    self.force_print(f"⚠️ WARNING: Too many active downloads ({len(self.active_downloads)}), enforcing limits")
                    
                    # Find downloads to pause (oldest first)
                    downloads_to_pause = []
                    active_downloads = list(self.active_downloads.items())
                    
                    # Sort by start time (oldest first)
                    active_downloads.sort(key=lambda x: x[1]["start_time"])
                    
                    # Calculate how many to pause - be more aggressive to get back under the limit quickly
                    excess = len(active_downloads) - self.current_download_limit
                    # Pause at least 25% more than the excess to prevent oscillation
                    to_pause = min(len(active_downloads) - 1, int(excess * 1.25) + 1)
                    
                    if to_pause > 0:
                        downloads_to_pause = active_downloads[:to_pause]
                        
                        self.force_print(f"Pausing {to_pause} downloads to enforce limits")
                        for task_id, download in downloads_to_pause:
                            filename = Path(download["filename"]).name
                            self.force_print(f"⏸️ Pausing download: {filename}")
                            
                            # Mark as completed to remove from active downloads
                            await self._remove_completed_download(task_id)
                            
                            # Increment failed count
                            self.failed_files += 1
                            
                            # Re-queue the download if it wasn't complete
                            completed = download.get("completed", 0)
                            total = download.get("total", None)
                            if not (total and completed >= total * 0.95):  # Don't re-queue if >95% complete
                                self.download_queue.append({
                                    "file": download["filename"],
                                    "expected_size": download.get("total"),
                                    "domain": download.get("domain"),
                                    "task_id": None  # Create a new task ID when processing
                                })
                                self.force_print(f"Re-queued download: {filename}")
                
                # Check if any domain is exceeding its limit
                for domain, count in list(self.active_domain_counts.items()):
                    # Use the temporary domain limit if set
                    domain_limit = self.temp_domain_limits.get(domain, self.current_domain_limit)
                    
                    if count > domain_limit:
                        self.force_print(f"⚠️ WARNING: Too many active downloads for domain {domain} ({count}), enforcing limits")
                        
                        # Find downloads for this domain
                        domain_downloads = [(task_id, download) for task_id, download in self.active_downloads.items() 
                                          if download.get("domain") == domain]
                        
                        # Sort by start time (oldest first)
                        domain_downloads.sort(key=lambda x: x[1]["start_time"])
                        
                        # Calculate how many to pause - be more aggressive
                        excess = count - domain_limit
                        # Pause at least 25% more than the excess to prevent oscillation
                        to_pause = min(len(domain_downloads) - 1, int(excess * 1.25) + 1)
                        
                        if to_pause > 0:
                            downloads_to_pause = domain_downloads[:to_pause]
                            
                            self.force_print(f"Pausing {to_pause} downloads for domain {domain} to enforce limits")
                            for task_id, download in downloads_to_pause:
                                filename = Path(download["filename"]).name
                                self.force_print(f"⏸️ Pausing download for domain {domain}: {filename}")
                                
                                # Mark as completed to remove from active downloads
                                await self._remove_completed_download(task_id)
                                
                                # Increment failed count
                                self.failed_files += 1
                                
                                # Re-queue the download if it wasn't complete
                                completed = download.get("completed", 0)
                                total = download.get("total", None)
                                if not (total and completed >= total * 0.95):  # Don't re-queue if >95% complete
                                    self.download_queue.append({
                                        "file": download["filename"],
                                        "expected_size": download.get("total"),
                                        "domain": download.get("domain"),
                                        "task_id": None  # Create a new task ID when processing
                                    })
                                    self.force_print(f"Re-queued download: {filename}")
                
                # Process the download queue to start new downloads if possible
                if self.download_queue and not self.is_processing_queue:
                    # Trigger queue processing
                    self.force_print(f"Queue has {len(self.download_queue)} items, triggering queue processing")
                    asyncio.create_task(self._process_download_queue())
            
            except Exception as e:
                self.force_print(f"Error in limit enforcer: {e}")
            
            # Check every 15 seconds (more frequently)
            await asyncio.sleep(15)

    async def _process_download_queue(self) -> None:
        """Process the download queue, respecting download limits"""
        # Wait a bit before starting to process the queue
        await asyncio.sleep(5)
        
        while True:
            try:
                if self.is_processing_queue:
                    await asyncio.sleep(1)
                    continue
                    
                self.is_processing_queue = True
                
                try:
                    # Process queue until empty or at limits
                    queue_processed = 0
                    queue_size = len(self.download_queue)
                    
                    if queue_size > 0:
                        self.force_print(f"Processing download queue ({queue_size} items waiting)")
                    
                    # Check if we need to adjust domain limits
                    # If we have global capacity but domain limits are preventing downloads
                    if len(self.active_downloads) < self.current_download_limit and queue_size > 0:
                        # Count domains in the queue
                        domain_counts = {}
                        for item in self.download_queue:
                            domain = item.get("domain")
                            if domain:
                                if domain not in domain_counts:
                                    domain_counts[domain] = 0
                                domain_counts[domain] += 1
                        
                        # Find domains that are at their limit but have queued downloads
                        domains_at_limit = []
                        for domain, queued_count in domain_counts.items():
                            active_count = self.active_domain_counts.get(domain, 0)
                            domain_limit = self.temp_domain_limits.get(domain, self.current_domain_limit)
                            
                            if active_count >= domain_limit and queued_count > 0:
                                domains_at_limit.append((domain, active_count, queued_count))
                        
                        # If we have domains at their limit but global capacity available
                        if domains_at_limit:
                            # Sort by number of queued downloads (descending)
                            domains_at_limit.sort(key=lambda x: x[2], reverse=True)
                            
                            # Calculate available capacity
                            available_capacity = self.current_download_limit - len(self.active_downloads)
                            
                            # Distribute available capacity among domains with queued downloads
                            for domain, active_count, queued_count in domains_at_limit:
                                if available_capacity <= 0:
                                    break
                                    
                                # Calculate how many more downloads to allow for this domain
                                # Use at least 3 or half the available capacity, whichever is smaller
                                increase = min(3, available_capacity, queued_count)
                                
                                if increase > 0:
                                    # Set a temporary increased limit for this domain
                                    new_limit = active_count + increase
                                    self.temp_domain_limits[domain] = new_limit
                                    
                                    self.force_print(f"Temporarily increasing limit for domain {domain} from {self.current_domain_limit} to {new_limit} (has {queued_count} queued downloads)")
                                    
                                    # Reduce available capacity
                                    available_capacity -= increase
                    
                    # Process the queue with adjusted limits
                    queue_processed = 0
                    domains_processed = set()
                    
                    # First pass: try to process at least one download from each domain
                    for i, item in enumerate(list(self.download_queue)):
                        # Check if we're at the global limit
                        if len(self.active_downloads) >= self.current_download_limit:
                            self.force_print(f"Global download limit reached ({len(self.active_downloads)}/{self.current_download_limit}), pausing queue processing")
                            break
                            
                        domain = item.get("domain")
                        if not domain or domain in domains_processed:
                            continue
                            
                        # Check domain limits, using temporary limits if set
                        domain_count = self.active_domain_counts.get(domain, 0)
                        domain_limit = self.temp_domain_limits.get(domain, self.current_domain_limit)
                        
                        if domain_count >= domain_limit:
                            continue
                            
                        # Process this item
                        self.download_queue.pop(i - queue_processed)
                        queue_processed += 1
                        domains_processed.add(domain)
                        
                        # Start the download
                        file = item.get("file")
                        expected_size = item.get("expected_size")
                        task_id = item.get("task_id")
                        
                        self.force_print(f"Starting queued download for domain {domain}: {file}")
                        
                        # Create a new task ID if needed
                        if not task_id:
                            task_id = await self.manager.progress_manager.file_progress.add_task(file, expected_size)
                        
                        # Add to active downloads
                        self.active_downloads[task_id] = {
                            "filename": file,
                            "total": expected_size,
                            "completed": 0,
                            "start_time": time.time(),
                            "last_update_time": time.time(),
                            "domain": domain
                        }
                        
                        # Update domain counts
                        if domain not in self.active_domain_counts:
                            self.active_domain_counts[domain] = 0
                        self.active_domain_counts[domain] += 1
                        
                        # Start the actual download
                        await self._start_download_from_queue(file, domain, task_id, expected_size)
                        
                        # Small delay between starting downloads
                        await asyncio.sleep(0.5)
                    
                    # Second pass: normal queue processing
                    while self.download_queue:
                        # Check if we're at the global limit
                        if len(self.active_downloads) >= self.current_download_limit:
                            # We're at the limit, stop processing the queue
                            self.force_print(f"Global download limit reached ({len(self.active_downloads)}/{self.current_download_limit}), pausing queue processing")
                            break
                        
                        # Get the next item from the queue
                        item = self.download_queue[0]
                        domain = item.get("domain")
                        file = item.get("file")
                        expected_size = item.get("expected_size")
                        original_task = item.get("original_task")
                        task_id = item.get("task_id")
                        
                        # Check domain limits, using temporary limits if set
                        if domain:
                            domain_count = self.active_domain_counts.get(domain, 0)
                            domain_limit = self.temp_domain_limits.get(domain, self.current_domain_limit)
                            
                            if domain_count >= domain_limit:
                                # This domain is at its limit, try the next item
                                # Move this item to the end of the queue
                                self.download_queue.append(self.download_queue.pop(0))
                                
                                # If we've gone through the entire queue without finding a suitable item, stop
                                if len(self.download_queue) <= 1 or queue_processed >= queue_size:
                                    # Check if we can increase any domain limits
                                    if len(self.active_downloads) < self.current_download_limit * 0.8:
                                        # We have capacity, try to increase a domain limit
                                        domain_queue_counts = {}
                                        for q_item in self.download_queue:
                                            q_domain = q_item.get("domain")
                                            if q_domain:
                                                if q_domain not in domain_queue_counts:
                                                    domain_queue_counts[q_domain] = 0
                                                domain_queue_counts[q_domain] += 1
                                        
                                        # Find the domain with the most queued downloads
                                        if domain_queue_counts:
                                            max_domain = max(domain_queue_counts.items(), key=lambda x: x[1])[0]
                                            current_limit = self.temp_domain_limits.get(max_domain, self.current_domain_limit)
                                            new_limit = current_limit + 2  # Increase by 2
                                            
                                            self.temp_domain_limits[max_domain] = new_limit
                                            self.force_print(f"Increasing limit for domain {max_domain} to {new_limit} to process queue")
                                            
                                            # Continue processing
                                            continue
                                    
                                    self.force_print(f"Domain limit reached for all queued downloads, pausing queue processing")
                                    break
                                    
                                queue_processed += 1
                                continue
                        
                        # Remove the item from the queue
                        self.download_queue.pop(0)
                        
                        # Start the download
                        self.force_print(f"Starting queued download: {file}")
                        
                        try:
                            # Create a new task for the download
                            if original_task:
                                self.force_print(f"Creating task from original task for {file}")
                                self.manager.task_group.create_task(original_task)
                            else:
                                # If no original task, create a new one using the file info
                                if not task_id:
                                    self.force_print(f"Creating new task ID for {file}")
                                    task_id = await self.manager.progress_manager.file_progress.add_task(file, expected_size)
                                
                                self.active_downloads[task_id] = {
                                    "filename": file,
                                    "total": expected_size,
                                    "completed": 0,
                                    "start_time": time.time(),
                                    "last_update_time": time.time(),
                                    "domain": domain
                                }
                                
                                # Update domain counts
                                if domain:
                                    if domain not in self.active_domain_counts:
                                        self.active_domain_counts[domain] = 0
                                    self.active_domain_counts[domain] += 1
                                
                                # Start the actual download
                                await self._start_download_from_queue(file, domain, task_id, expected_size)
                                
                                # Debug: Check if the file exists in the download directory
                                try:
                                    download_dir = self.manager.path_manager.download_dir
                                    potential_file = Path(download_dir) / Path(file).name
                                    if potential_file.exists():
                                        self.force_print(f"⚠️ Warning: File already exists: {potential_file}")
                                except Exception as e:
                                    self.force_print(f"Error checking file existence: {e}")
                        except Exception as e:
                            self.force_print(f"Error starting download: {e}")
                            traceback.print_exc()
                        
                        queue_processed += 1
                        
                        # Small delay between starting downloads to avoid overwhelming the system
                        await asyncio.sleep(0.5)
                finally:
                    self.is_processing_queue = False
                
                # Check the queue every 5 seconds
                await asyncio.sleep(5)
            except Exception as e:
                self.force_print(f"Error in queue processor: {e}")
                traceback.print_exc()
                self.is_processing_queue = False
                await asyncio.sleep(5)

    async def _start_download_from_queue(self, file, domain, task_id=None, expected_size=None):
        """Start a download from the queue"""
        try:
            # Debug information
            self.force_print(f"Starting download for {file} (domain: {domain})")
            
            # Create a MediaItem for the download
            from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem
            from yarl import URL
            import os
            from pathlib import Path
            
            # Extract the filename from the file path
            filename = Path(file).name
            if "(" in file and ")" in file:
                # Try to extract just the filename part after the domain
                parts = file.split(")", 1)
                if len(parts) > 1:
                    filename = parts[1].strip()
            
            # Create a URL based on the domain and filename
            if domain == "no_crawler":
                # For no_crawler domain, check if the filename might be a URL
                if " http" in file:
                    url_part = file.split(" http", 1)[1]
                    url = URL(f"http{url_part}")
                else:
                    url = URL(f"https://example.com/{filename}")
            else:
                # Create a domain-based URL
                url = URL(f"https://{domain}.com/{filename}")
            
            # Determine the download directory
            download_dir = self.manager.path_manager.download_dir
            
            # Create a MediaItem
            media_item = MediaItem(
                url=url,
                referer=url,
                filename=filename,
                download_folder=download_dir,
                parent_title="",
                date=int(time.time())
            )
            
            # Set the task_id if provided
            if task_id:
                media_item.task_id = task_id
            
            # Start the download using the appropriate downloader
            from cyberdrop_dl.downloader.downloader import Downloader
            
            # Create a downloader instance if needed
            if not hasattr(self, 'downloader_instance'):
                self.downloader_instance = Downloader(self.manager)
                
            # Start the download
            self.force_print(f"Starting download for {filename}")
            self.manager.task_group.create_task(
                self.downloader_instance.download(media_item)
            )
            
            return True
        except Exception as e:
            self.force_print(f"Error starting download: {e}")
            traceback.print_exc()
            return False


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