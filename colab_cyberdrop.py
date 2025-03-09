#!/usr/bin/env python3
"""
CyberDrop Downloader - Colab Edition
A wrapper script for using CyberDrop Downloader in Google Colab
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Union


def run_downloader(
    urls: List[str],
    block_download_sub_folders: bool = False,
    skip_hosts: Optional[List[str]] = None,
    only_hosts: Optional[List[str]] = None,
    output_folder: str = "./downloads",
    max_downloads: int = 15,
    max_per_domain: int = 5,
    verbose: bool = False,
    ignore_history: bool = False,
    stall_threshold: int = 300,
    max_retries: int = 3,
    additional_args: Optional[Dict[str, Any]] = None
) -> None:
    """
    Run the CyberDrop Downloader with Colab-friendly settings
    
    Args:
        urls: List of URLs to download
        block_download_sub_folders: Whether to block sub folder creation
        skip_hosts: List of hosts to skip
        only_hosts: List of hosts to only include
        output_folder: Path to where you want to save downloads
        max_downloads: Maximum number of concurrent downloads (default: 15)
        max_per_domain: Maximum number of concurrent downloads per domain (default: 5)
        verbose: Whether to enable verbose logging (default: False)
        ignore_history: Whether to ignore download history (default: False)
        stall_threshold: Time in seconds before considering a download stalled (default: 300)
        max_retries: Maximum number of retries for stalled downloads (default: 3)
        additional_args: Additional arguments to pass to cyberdrop-dl
    """
    # Build the command
    cmd = ["cyberdrop-dl", "--colab-mode", "--download"]
    
    # Add arguments
    if block_download_sub_folders:
        cmd.append("--block-download-sub-folders")
    
    cmd.extend(["--output-folder", output_folder])
    
    # Add download limits
    cmd.extend(["--max-simultaneous-downloads", str(max_downloads)])
    cmd.extend(["--max-simultaneous-downloads-per-domain", str(max_per_domain)])
    
    # Add verbose flag if requested
    if verbose:
        cmd.append("--verbose")
        
    # Add ignore_history flag if requested
    if ignore_history:
        cmd.append("--ignore-history")
        
    # Add stall threshold and max retries
    cmd.extend(["--stall-threshold", str(stall_threshold)])
    cmd.extend(["--max-retries", str(max_retries)])
    
    # Add skip hosts
    if skip_hosts:
        for host in skip_hosts:
            cmd.extend(["--skip-hosts", host])
    
    # Add only hosts
    if only_hosts:
        for host in only_hosts:
            cmd.extend(["--only-hosts", host])
    
    # Add additional arguments
    if additional_args:
        for key, value in additional_args.items():
            if isinstance(value, bool) and value:
                cmd.append(f"--{key.replace('_', '-')}")
            elif not isinstance(value, bool):
                cmd.extend([f"--{key.replace('_', '-')}", str(value)])
    
    # Add URLs
    cmd.extend(urls)
    
    # Print the command
    print("Running command:", " ".join(cmd))
    
    # Execute the command
    subprocess.run(cmd)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="CyberDrop Downloader - Colab Edition")
    parser.add_argument("--download", action="store_true", help="start downloading immediately", default=True)
    parser.add_argument("--block-download-sub-folders", action="store_true", help="block sub folder creation", default=False)
    parser.add_argument("--skip-hosts", action="append", help="skip these domains when scraping", default=[])
    parser.add_argument("--only-hosts", action="append", help="only scrape these domains", default=[])
    parser.add_argument("--output-folder", type=str, help="path to where you want to save downloads", default="./downloads")
    parser.add_argument("--max-downloads", type=int, help="maximum number of concurrent downloads", default=15)
    parser.add_argument("--max-per-domain", type=int, help="maximum number of concurrent downloads per domain", default=5)
    parser.add_argument("--verbose", action="store_true", help="enable verbose logging", default=False)
    parser.add_argument("--ignore-history", action="store_true", help="ignore download history", default=False)
    parser.add_argument("--stall-threshold", type=int, help="time in seconds before considering a download stalled", default=300)
    parser.add_argument("--max-retries", type=int, help="maximum number of retries for stalled downloads", default=3)
    parser.add_argument("links", nargs="*", help="links to download")
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()
    
    # Build the command
    cmd = ["cyberdrop-dl", "--colab-mode"]
    
    # Add arguments
    if args.download:
        cmd.append("--download")
    if args.block_download_sub_folders:
        cmd.append("--block-download-sub-folders")
    if args.output_folder:
        cmd.extend(["--output-folder", args.output_folder])
    
    # Add download limits
    cmd.extend(["--max-simultaneous-downloads", str(args.max_downloads)])
    cmd.extend(["--max-simultaneous-downloads-per-domain", str(args.max_per_domain)])
    
    # Add verbose flag if requested
    if args.verbose:
        cmd.append("--verbose")
        
    # Add ignore_history flag if requested
    if args.ignore_history:
        cmd.append("--ignore-history")
        
    # Add stall threshold and max retries
    cmd.extend(["--stall-threshold", str(args.stall_threshold)])
    cmd.extend(["--max-retries", str(args.max_retries)])
    
    # Add skip hosts
    for host in args.skip_hosts:
        cmd.extend(["--skip-hosts", host])
    
    # Add only hosts
    for host in args.only_hosts:
        cmd.extend(["--only-hosts", host])
    
    # Add links
    cmd.extend(args.links)
    
    # Print the command
    print("Running command:", " ".join(cmd))
    
    # Execute the command
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()