from setuptools import setup, find_packages

setup(
    name="cyberdrop-dl-colab",
    version="0.1.0",
    description="Colab-friendly version of CyberDrop Downloader",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/eskaviam/CyberDropDownloader",
    packages=find_packages(),
    py_modules=["colab_cyberdrop"],
    install_requires=[
        "cyberdrop-dl",
    ],
    entry_points={
        "console_scripts": [
            "cyberdrop-colab=cyberdrop_dl.colab_downloader:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
)