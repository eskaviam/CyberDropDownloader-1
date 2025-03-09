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
5. Detects and reports stalled downloads that aren't making progress
6. Automatically limits concurrent downloads to prevent overwhelming servers

### Understanding the Progress Display

The progress display now clearly distinguishes between different types of downloads:

1. **Active Downloads (⬇️)**: Files that are actively being downloaded right now (updated in the last 10 seconds)
2. **Queued Downloads (⏳)**: Files that are waiting to be downloaded (due to download limits)
3. **Stalled Downloads (⚠️)**: Files that haven't made progress for more than the stall threshold

The summary shows:
- How many downloads are active out of your configured limit (e.g., "Download limits: 8/10 active")
- A breakdown of Active, Queued, and Stalled downloads
- Detailed progress for a subset of downloads in each category

This helps you understand if your download limits are working correctly and identify any issues with stalled downloads.

## Handling Stalled Downloads

The Colab edition includes features to help identify and handle stalled downloads:

1. **Stalled Download Detection**: Downloads that haven't made progress for more than 10 seconds are marked as stalled
2. **Visual Indicators**: Stalled downloads are marked with a warning emoji (⚠️)
3. **Time Since Update**: For stalled downloads, the time since the last progress update is shown
4. **Automatic Limits**: The downloader automatically limits concurrent downloads to prevent overwhelming servers
5. **Stalled Download Warnings**: After 60 seconds of no progress, detailed warnings are shown with troubleshooting tips

### Controlling Download Limits

You can control the download limits to optimize performance:

```python
# Using the Python wrapper with custom limits
run_downloader(
    urls=["https://example.com/your-url"],
    max_downloads=10,  # Limit to 10 concurrent downloads
    max_per_domain=3   # Limit to 3 downloads per domain
)

# Using the command line
!python colab_cyberdrop.py --max-downloads 10 --max-per-domain 3 https://example.com/your-url

# Using cyberdrop-dl directly
!cyberdrop-dl --colab-mode --download --max-simultaneous-downloads 10 --max-simultaneous-downloads-per-domain 3 https://example.com/your-url
```

#### How Download Limits Work

The download limits control how many files can be downloaded simultaneously:

1. **max_downloads / max-simultaneous-downloads**: Controls the total number of files that can be downloaded at the same time across all domains. Default is 15.

2. **max_per_domain / max-simultaneous-downloads-per-domain**: Controls how many files can be downloaded from a single domain at the same time. Default is 5.

Setting these limits appropriately can help prevent:
- Rate limiting by servers
- Network congestion
- Memory issues in Colab
- Excessive CPU usage

For large downloads, consider using more conservative limits like `max_downloads=10` and `max_per_domain=3`.

### Ignoring Download History

If you want to re-download files that have been downloaded before, you can use the `--ignore-history` flag:

```python
# Using the Python wrapper
run_downloader(
    urls=["https://example.com/your-url"],
    ignore_history=True  # Re-download files even if they've been downloaded before
)

# Using the command line
!python colab_cyberdrop.py --ignore-history https://example.com/your-url

# Using cyberdrop-dl directly
!cyberdrop-dl --colab-mode --download --ignore-history https://example.com/your-url
```

### Controlling Stall Detection and Retries

You can control how the downloader handles stalled downloads:

```python
# Using the Python wrapper
run_downloader(
    urls=["https://example.com/your-url"],
    stall_threshold=300,  # Consider downloads stalled after 5 minutes (300 seconds)
    max_retries=3         # Retry stalled downloads up to 3 times
)

# Using the command line
!python colab_cyberdrop.py --stall-threshold 600 --max-retries 5 https://example.com/your-url

# Using cyberdrop-dl directly
!cyberdrop-dl --colab-mode --download --stall-threshold 300 --max-retries 3 https://example.com/your-url
```

## Troubleshooting

If you encounter any issues:

1. **Reduce Concurrent Downloads**: Try reducing the number of concurrent downloads with `--max-downloads 10`
2. **Check for Rate Limiting**: Some hosts may rate-limit downloads, try using `--max-per-domain 2`
3. **Network Issues**: If many downloads are stalled, check your network connection
4. **Server Issues**: Some servers may be slow or unresponsive, try again later
5. **Memory Usage**: If Colab is running out of memory, reduce the number of concurrent downloads

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.