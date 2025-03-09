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
        additional_args: Additional arguments to pass to cyberdrop-dl
    """
    # Build the command
    cmd = ["cyberdrop-dl", "--colab-mode", "--download"]
    
    # Add arguments
    if block_download_sub_folders:
        cmd.append("--block-download-sub-folders")
    
    cmd.extend(["--output-folder", output_folder])
    
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