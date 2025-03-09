# CyberDrop Downloader - Colab Edition

This is a fork of the CyberDrop Downloader that is optimized for use in Google Colab. It provides a simplified progress display that avoids the rich UI that can cause lag in Colab notebooks.

## Features

- Colab-friendly progress display without the rich UI
- Shows download progress with simple ASCII progress bars
- Limits output to avoid Colab lag
- Maintains all the functionality of the original CyberDrop Downloader

## Installation in Colab

To use this in Google Colab, add the following to a cell:

```python
# Install the CyberDrop Downloader
!pip install cyberdrop-dl

# Clone this repository to get the Colab wrapper
!git clone https://github.com/eskaviam/CyberDropDownloader.git
!cd CyberDropDownloader && pip install -e .
```

## Usage

### Basic Usage

```python
# Import the URLs you want to download
urls = [
    "https://cyberdrop.me/a/example1",
    "https://cyberdrop.me/a/example2"
]

# Run the downloader with Colab mode
from CyberDropDownloader_Colab.colab_cyberdrop import run_downloader
run_downloader(urls)
```

### Using the Command Line Wrapper

```python
# Download from URLs
!python colab_cyberdrop.py https://cyberdrop.me/a/example1 https://cyberdrop.me/a/example2

# Skip specific hosts
!python colab_cyberdrop.py --skip-hosts coomer https://cyberdrop.me/a/example1

# Block download sub-folders
!python colab_cyberdrop.py --block-download-sub-folders https://cyberdrop.me/a/example1

# Specify output folder
!python colab_cyberdrop.py --output-folder /content/downloads https://cyberdrop.me/a/example1
```

### Using Direct CyberDrop-DL Command

```python
# Use the colab-mode flag directly with cyberdrop-dl
!cyberdrop-dl --colab-mode --download --block-download-sub-folders --skip-hosts coomer https://cyberdrop.me/a/example1
```

## How It Works

The Colab edition uses a custom progress display that:

1. Updates progress at a controlled rate (default: once per second)
2. Uses simple ASCII progress bars instead of rich UI elements
3. Limits the number of active downloads shown to avoid overwhelming output
4. Provides essential information like download speed and file size

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.