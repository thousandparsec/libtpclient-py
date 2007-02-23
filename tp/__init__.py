try:
	try:
		import pkg_resources
		pkg_resources.declare_namespace(__name__)
	except ImportError:
		import pkgutil
		__path__ = pkgutil.extend_path(__path__, __name__)
except Exception, e:
	import warnings
	warnings.warn(e, RuntimeWarning)

try:
	import modulefinder
	for p in __path__:
		modulefinder.AddPackagePath(__name__, p)
except Exception, e:
	import warnings
	warnings.warn(e, RuntimeWarning)
