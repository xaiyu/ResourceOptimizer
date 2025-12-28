from setuptools import setup, find_packages
import re
from pathlib import Path

# 从 __init__.py 读取版本号
def get_version():
    init_file = Path(__file__).parent / "__init__.py"
    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    return "4.1.0"  # 默认版本

setup(
    name="ResourceOptimizer",
    version=get_version(),
    description="智能媒体资源治理系统 - 夸克网盘资源优化器",
    author="Smart Chase Team",
    python_requires=">=3.8",
    packages=find_packages(exclude=["tests", "tests.*", "instance", "1111"]),
    package_dir={"": "."},
    install_requires=[
        "requests>=2.28.0",
        "aiohttp>=3.8.0",
        "PyYAML>=6.0",
        "tenacity>=8.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=0.991",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
