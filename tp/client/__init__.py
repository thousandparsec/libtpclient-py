
from version import version as vi
from version import installpath as ip
__version__     = vi
__installpath__ = ip

import __builtin__
try:
	__builtin__._
except AttributeError:
	def _(s):
		return s
	__builtin__._ = _
