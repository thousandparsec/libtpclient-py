#!/usr/bin/env python

from distutils.core import setup

version = "0.0.1"

import os.path
import os

setup(name="libtpclient-py",
	version=version,
	license="GPL",
	description="Client support library for Thousand Parsec",
	author="Tim Ansell",
	author_email="tim@thousandparsec.net",
	url="http://www.thousandparsec.net",
	packages=[ \
		'tp',
		'tp.client',
		'tp.client.pyscheme',
	],
	package_dir = {'tp': ''}
)


