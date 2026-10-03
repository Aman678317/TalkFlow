from setuptools import setup, find_packages

setup(
    name="desi-python",
    version="2.1.0",
    packages=find_packages(),
    package_data={"desi": ["py.typed"]},
    install_requires=[
        "httpx>=0.24.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
)
