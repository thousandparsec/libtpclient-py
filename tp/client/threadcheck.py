import threading
from decorator import decorator

@decorator
def thread_check_callable(func, self, *args, **kw):
	assert self._thread is threading.currentThread(), "%s can only be called by %s not %s" % (func, self._thread, threading.currentThread())
	return func(self, *args, **kw)

@decorator
def thread_check_init(func, self, *args, **kw):
	self._thread = threading.currentThread()
	return func(self, *args, **kw)

def thread_safe(func):
	"""
	Mark this function as thread safe so can be called accross thread
	boundaries.  
	"""
	func.__threadsafe = True
	return func

# FIXME: This doesn't also check the classes base class!
import inspect
class thread_checker(type):
	"""
	This class can be set as the metaclass for an object to make sure that it
	is only access from a single thread.  

	Methods can be marked "thread_safe" with the thread_safe decorator also 
	found in this module.
	"""
	def __new__(cls,classname,bases,classdict):
		for attr, item in classdict.items():
			if attr == "__init__":
				classdict[attr] = thread_check_init(item)
			elif inspect.isfunction(item) and not hasattr(item, "__threadsafe"):
				classdict[attr] = thread_check_callable(item)

		t = type.__new__(cls,classname,bases,classdict)
		return t

__all__ = ["thread_checker", "thread_safe"]

if __name__ == "__main__":
	class B(object):
		__metaclass__ = thread_checker

		def __init__(self):
			pass

		test_simple  = 2
		test_complex = [1, 3]

		def test_unsafe(self):
			return "test_unsafe worked"

		@thread_safe
		def test_safe(self):
			return "test_safe worked"

	class t1(threading.Thread):
		def __init__(self, ishouldnotaccess):
			self.i = ishouldnotaccess

			threading.Thread.__init__(self)

		def run(self):
			print self.i.test_simple
			print self.i.test_complex
			print self.i.test_safe()
			print self.i.test_unsafe()

	ot = t1(B())

	print ot.i.test_safe
	print inspect.getargspec(ot.i.test_safe)
	print ot.i.test_unsafe	
	print inspect.getargspec(ot.i.test_unsafe)
	
	ot.run()

	# this should fail
	ot.start()

	import time
	time.sleep(10)

