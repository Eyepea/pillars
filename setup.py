#!/usr/bin/env python
# -*- coding: utf-8 -*-
 
from setuptools import setup, find_packages
 
# notez qu'on import la lib
# donc assurez-vous que l'importe n'a pas d'effet de bord
import pillars
 
setup(
 
    name='pillars',
 
    version=0.5,
 
    packages=find_packages(),
 
    author="Quentin Dawaans, Nicolas Turcksin",
 
 
 
    long_description=open('README.md').read(),
 
    url='http://github.com/eyepea/pillars',
 
    classifiers=[
        "Programming Language :: Python",
        "Development Status :: 1 - Planning",
        "License :: OSI Approved",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7.4",
        "Topic :: Communications",
    ],
 
 
 
 
)
