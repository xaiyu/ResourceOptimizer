from setuptools import setup, find_packages

setup(
    name="ResourceOptimizer",
    version="1.0.0",
    description="Resource optimizer for Quark cloud drive links",
    packages=["ResourceOptimizer", "clients", "core", "utils"],
    package_dir={"ResourceOptimizer": "."},
    install_requires=[
        "requests",
        "guessit",
        "PyYAML",
        "tenacity",
        "aiohttp",
        "ollama",
    ],
)
