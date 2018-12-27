#!/usr/bin/env python

import sys
from setuptools import setup

# dependences
setup_requires = []
if sys.argv[-1] in ('sdist', 'bdist_wheel'):
    setup_requires.append('setuptools-markdown')

install_requires = [
    'lxml>=4.2.5',
]

setup(
    name = 'ldcv',
    version = '1.0.0',
    description = "LangMan Console Version",
    long_description = 'README.rst',
    author = 'leetking',
    author_email = 'li_tking@163.com',
    url = "https://github.com/leetking/ldcv",
    license = 'GPL',
    package_dir = {'': 'src'},
    py_modules = ['ldcv'],
    entry_points = {
        'console_scripts': ['ldcv=ldcv:main'],
    },
    setup_requires = setup_requires,
    install_requires = install_requires,
    classifiers = [
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX :: SunOS/Solaris",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Utilities",
    ],
)
