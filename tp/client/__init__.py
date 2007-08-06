
from version import version, installpath
__version__     = version
__installpath__ = installpath

import __builtin__
try:
	print __builtin__
	__builtin__._
except AttributeError:
	def _(s):
		return s
	__builtin__._ = _
