from types import TupleType

class ChangeDict(dict):
	"""\
	A simple dictionary which also stores the "times" an object was last updated.

	Used so that we only upload/download items which have changed.
	"""
	def __init__(self):
		dict.__init__(self)
		self.times = {}
	
	def __setitem__(self, key, value):
		"""\
		This set item is special, it only takes keys of the form,
		(<last modified time>, <normal key>)
		"""
		if type(value) is TupleType and len(value) == 2:
			time, value = value
		else:
			time = -1

		if time != -1 and self.times.has_key(key) and self.times[key] > time:
			raise ValueError("The object isn't new enough to update the dictionary with! Current %s, update %s" % (self.times[key], time))
		
		self.times[key] = time
		dict.__setitem__(self, key, value)

	def __delitem__(self, key):
		del self.times[key]
		dict.__delitem__(self, key)

ChangeDict.__repr__ = dict.__repr__
