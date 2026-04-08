from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="adaptive-skill-system",
    version="1.2.0",

    author="sdenilson212",
    description="三层递进 AI Skill 引擎 — 让 AI 在复杂问题上自动学习进化",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sdenilson212/adaptive-skill-system",
    packages=find_packages(exclude=["tests*", "docs*"]),
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "dev": ["pytest>=7.0"],
    },
    entry_points={
        "console_scripts": [
            "adaptive-skill-report=adaptive_skill.harness.cli:main",
        ],
    },
    classifiers=[

        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
