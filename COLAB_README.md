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

The Colab edition includes intelligent stall detection to identify and handle downloads that aren't making progress:

1. **Smart Stall Detection**: Downloads are only marked as stalled if they meet specific criteria:
   - No progress for more than the stall threshold (default: 120 seconds)
   - Download speed has dropped significantly
   - Not near completion (downloads at >95% are not considered stalled)

2. **Detailed Stall Information**: For stalled downloads, the specific reason is shown:
   - "No progress for X seconds"
   - "Speed too low (X/s) for Y seconds"

3. **Automatic Retry**: Stalled downloads are automatically retried up to a configurable number of times

4. **Visual Indicators**: Stalled downloads are marked with a warning emoji (⚠️)

5. **Intelligent Handling**: Downloads that are almost complete (>95%) are not retried even if they appear stalled

### Controlling Download Limits

You can control the number of concurrent downloads to prevent overwhelming your Colab instance or getting rate-limited by servers:

```python
run_downloader(
    urls=["https://example.com/your-url"],
    max_downloads=10,  # Limit to 10 concurrent downloads
    max_per_domain=3   # Limit to 3 downloads per domain
)
```

These limits help prevent:
- Rate limiting from servers
- Network congestion
- Excessive resource usage in Colab
- Crashes due to too many concurrent downloads

The default values are:
- `max_downloads`: 15 (total concurrent downloads)
- `max_per_domain`: 5 (concurrent downloads per domain)

For large downloads, it's recommended to use conservative limits (10 total, 3 per domain) to ensure stability.

### Automatic Limit Enforcement

The downloader now includes automatic limit enforcement to prevent issues:

1. **Active Monitoring**: The downloader constantly monitors the number of active downloads
2. **Warning Notifications**: When limits are exceeded, warnings are displayed in the output
3. **Automatic Pausing**: If downloads exceed the limit, older downloads are automatically paused
4. **Domain-Specific Limits**: Each domain is monitored separately to prevent overwhelming specific servers
5. **Detailed Status**: The progress display shows detailed information about active downloads and limits
6. **Download Queue**: New downloads are automatically queued when limits are reached
7. **Aggressive Enforcement**: The system aggressively enforces limits to prevent crashes
8. **Smart Queue Processing**: When downloads complete, queued downloads are automatically started
9. **Dynamic Domain Limits**: Domain limits are temporarily increased when global capacity is available
10. **Domain-Specific Queues**: The system tracks queued downloads by domain and prioritizes accordingly
11. **Persistent Temporary Limits**: Once a domain limit is increased, it stays increased until the program ends
12. **Balanced Distribution**: Available capacity is distributed among domains with queued downloads
13. **Progressive Limit Increases**: Domain limits are increased gradually to prevent overwhelming servers

This ensures that even if many downloads are queued, the system will remain stable and responsive.

## Handling Stalled Downloads

The Colab edition includes intelligent stall detection to identify and handle downloads that aren't making progress:

1. **Smart Stall Detection**: Downloads are only marked as stalled if they meet specific criteria:
   - No progress for more than the stall threshold (default: 120 seconds)
   - Download speed has dropped significantly
   - Not near completion (downloads at >95% are not considered stalled)

2. **Detailed Stall Information**: For stalled downloads, the specific reason is shown:
   - "No progress for X seconds"
   - "Speed too low (X/s) for Y seconds"

3. **Automatic Retry**: Stalled downloads are automatically retried up to a configurable number of times

4. **Visual Indicators**: Stalled downloads are marked with a warning emoji (⚠️)

5. **Intelligent Handling**: Downloads that are almost complete (>95%) are not retried even if they appear stalled

### Controlling Download Limits

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