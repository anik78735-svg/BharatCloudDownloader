from setuptools import setup, find_packages

setup(
    name="bharatclouddeveloper",
    version="1.0.0",
    description="Unified Instagram + TikTok + Facebook Reels/Video Downloader SDK & API",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Surya Kumar Boss",
    author_email="surya@bharatcloud.dev",
    url="https://github.com/bharatclouddeveloper/downloader",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.27.0",
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.30.0",
        "aiofiles>=24.1.0",
        "python-multipart>=0.0.9",
        "pydantic>=2.9.0",
    ],
    entry_points={
        "console_scripts": [
            "bharatcloud=bharatclouddeveloper.cli:main",
            "bcd-download=bharatclouddeveloper.cli:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Multimedia :: Video",
    ],
)
