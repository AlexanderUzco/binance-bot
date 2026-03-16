from setuptools import setup, find_packages

setup(
    name="binance-bot",
    version="2.0.0",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "httpx>=0.27",
        "websockets>=12.0",
        "aiosqlite>=0.20",
        "python-dotenv>=1.0",
    ],
    entry_points={
        "console_scripts": [
            "binbot=binance_bot.cli:main",
        ],
    },
)
