from setuptools import setup, find_packages

setup(
    name="maestro-guard",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "maestro-guard=maestro_guard.cli:main",
        ],
    },
    python_requires=">=3.10",
)
