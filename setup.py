#!/usr/bin/env python

from tp.client import version
version = "%s.%s.%s" % version

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

	packages=[ \
		'tp.client',
		'tp.client.pyscheme',
	],
	namespace_packages = ['tp'],
)
