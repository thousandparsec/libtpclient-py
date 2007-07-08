
version = (0, 3, 0)

# Add the git version if in a git tree...
import os, os.path
__path__ = os.path.realpath(os.path.dirname(__file__))
installpath = os.path.split(os.path.split(__path__)[0])[0]

# Get the git version this tree is based on
if os.path.exists(os.path.join(installpath, '.git')):
	# Read in git's 'HEAD' file which points to the correct reff to look at
	h = open(os.path.join(installpath, '.git', 'HEAD'))
	# Read in the ref
	ref = h.readline().strip().split(': ', 1)[1]
	# This file has the SHA1
	p = open(os.path.join(installpath, '.git', ref))
	version = tuple(list(version)+[p.read().strip()])

