#!/usr/bin/env python3
"""
One-line installer for CyberDrop Downloader - Colab Edition
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path


def main():
    """Main installation function"""
    print("Installing CyberDrop Downloader - Colab Edition...")
    
    # Install cyberdrop-dl
    print("Installing cyberdrop-dl...")
    subprocess.run([sys.executable, "-m", "pip", "install", "cyberdrop-dl"], check=True)
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Clone the repository
        print("Cloning the repository...")
        subprocess.run(["git", "clone", "https://github.com/eskaviam/CyberDropDownloader.git", temp_path], check=True)
        
        # Install the package
        print("Installing the Colab wrapper...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", temp_path], check=True)
        
        # Copy the example notebook
        notebook_path = temp_path / "colab_example.ipynb"
        if notebook_path.exists():
            shutil.copy(notebook_path, ".")
            print(f"Example notebook copied to {os.getcwd()}/colab_example.ipynb")
    
    print("\nInstallation complete!")
    print("\nYou can now use the Colab-friendly downloader with:")
    print("  from colab_cyberdrop import run_downloader")
    print("  run_downloader(['https://example.com/your-url'])")
    print("\nOr directly with:")
    print("  !cyberdrop-dl --colab-mode --download https://example.com/your-url")


if __name__ == "__main__":
    main() 