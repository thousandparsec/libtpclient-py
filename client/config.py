"""\
This file contains function useful for storing and retriving config.
"""

import sys
import os
import os.path

try:
	import cPickle as pickle
except ImportError:
	import pickle

def configpath():
	"""\
	Figures out where to save the preferences.
	"""
	dirs = [("APPDATA", "Thousand Parsec"), ("HOME", ".tp"), (".", "var")]
	for base, extra in dirs:
		if base in os.environ:
			base = os.environ[base]
		elif base != ".":
			continue
			
		rc = os.path.join(base, extra)
		if not os.path.exists(rc):
			os.mkdir(rc)
		return rc

def load_data(file):
	"""\
	Loads preference data from a file.
	"""
	try:
		f = open(os.path.join(configpath(), file), "r")
		data = pickle.load(f)
	except IOError:
		return None
	return data
	
def save_data(file, data):
	"""\
	Saves preference data to a file.
	"""
	f = open(os.path.join(configpath(), file), "w")
	pickle.dump(data, f)
