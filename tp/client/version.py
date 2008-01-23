
version = (0, 2, 3)

import os, os.path
__path__ = os.path.realpath(os.path.dirname(__file__))
installpath = os.path.split(os.path.split(__path__)[0])[0]

version_str = "%i.%i.%i" % version[:3]
