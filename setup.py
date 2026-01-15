from setuptools import setup, find_packages

setup(
    name="data-collector",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pydantic>=2.5.0",
        "sqlalchemy[asyncio]>=2.0.0",
        "asyncpg>=0.29.0",
        "aiosqlite>=0.19.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "pydantic-settings>=2.0.0",
        "alembic>=1.11.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.24.0",
        ],
    },
    python_requires=">=3.9",
)
