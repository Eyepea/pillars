#!/usr/bin/python3

from setuptools import setup, find_namespace_packages

setup(
    name='pillars',
    version='0.5.0',
    description='Maintain PGSQL database schema with incremental patches',
    author='Quentin Dawaans',
    classifiers=[
        'Programming Language :: Python :: 3.7',
    ],
    packages=find_namespace_packages(),
    install_requires=[
    ],
    setup_requires=[
    ],
)

