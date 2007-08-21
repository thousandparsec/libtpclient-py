#!/usr/bin/env python

import sys

try:
	del sys.argv[sys.argv.index('--ignore-deps')]
	print "Ignoring dependencies..."
except ValueError:
	import pkg_resources
	pkg_resources.require('libtpproto-py')

from tp.client import __version__
version = "%s.%s.%s" % __version__[0:3]

from setuptools import setup

setup(
	name		="libtpclient-py",
	version		=version,
	license		="GPL",
	description	="Client support library for Thousand Parsec",
	long_description="""\
A library of code to support quick development of Clients for Thousand Parsec.

Includes support for:
	* Classes of keeping a download cache of the universe (including automatic
 update)
	* Classes for parsing and calculating tpcl 
	* Threading support
""",
	author		="Tim Ansell",
	author_email="tim@thousandparsec.net",
	url			="http://www.thousandparsec.net",
	keywords	="thousand parsec space client support empire building strategy game tpcl scheme",

	namespace_packages = ['tp'],
	packages=[ \
		'tp',
		'tp.client',
		'tp.client.pyscheme',
	],
	zip_safe=False,
)
