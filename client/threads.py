
import pprint
import socket
import sys
import time
import threading
import traceback

from tp.netlib import Connection, failed

from cache import Cache
from config import load_data, save_data
from version import version

class Application(object):
	"""
	Container for all the applications threads and the network cache.

	Calling accross threads requires you to use the .Call method on each thread - DO NOT call directly!
	The cache can be accessed by either thread at any time - be careful.
	"""
	
	def __init__(self):
		self.gui = self.GUIClass(self)
		self.network = self.NetworkClass(self)

		self.cache = None
		
		# Load the Configuration
		self.ConfigLoad()

	def Run(self):
		"""\
		Set the application running.
		"""
		self.network.start()
		self.gui.start()

	def ConfigSave(self):
		"""\
		"""
		config = self.gui.ConfigSave()
		save_data(self.ConfigFile, config)
		
		print "Saving the config...\n" + pprint.pformat(config)

	def ConfigLoad(self):
		"""\
		"""
		config = load_data(self.ConfigFile)
		if config is None:
			config = {}
	
		print "Loading the config...\n" + pprint.pformat(config)
		
		self.gui.ConfigLoad(config)

	def Post(self, event):
		"""\
		Post an application wide event to every thread.
		"""
		self.network.Call(self.network.Post, event)
		self.gui.Call(self.gui.Post, event)

	def Exit(self):
		"""
		Exit the program.
		"""
		self.network.Call(self.network.Cleanup)
		self.gui.Call(self.gui.Cleanup)

class NetworkThread(threading.Thread):
	## These are network events
	class NetworkFailureEvent(Exception):
		"""\
		Raised when the network connection fails for what ever reason.
		"""
		pass

	######################################

	def __init__(self, application):
		threading.Thread.__init__(self)
		self.application = application
		self.exit = False

		self.tocall = []
		self.connection = Connection()
	
	def run(self):
		while not self.exit:
			if len(self.tocall) <= 0:
				if hasattr(time, 'sleep'):
					time.sleep(0.1)
				continue
			
			method, args, kw = self.tocall.pop(0)
			try:
				method(*args, **kw)
			except (IOError, socket.error), e:
				s  = _("There was an unknown network error.\n")
				s += _("Any changes since last save have been lost.\n")
				if getattr(self.connection, 'debug', False):
					s += _("A traceback of the error was printed to the console.\n")
					print e
				self.application.Post(self.NetworkFailureEvent(s))

	def Cleanup(self):
		self.exit = True

	def Call(self, method, *args, **kw):
		"""\
		Call a method in this thread.
		"""
		self.tocall.append((method, args, kw))

	def Post(self, event):
		"""
		Post an Event the current window.
		"""
		func = 'On' + event.__class__.__name__[:-5]
		print "Posting %s to %s" % (event, func)
		if hasattr(self, func):
			getattr(self, func)(event)

	def ConnectTo(self, host, username, password, debug=False, callback=None, cs="unknown"):
		"""\
		Connect to a given host using a certain username and password.
		"""
		if callback is None:
			def callback(*args, **kw):
				pass
		
		callback("Connecting...", mode="connecting")
		if self.connection.setup(host=host, debug=debug):
			s  = _("The client was unable to connect to the host.\n")
			s += _("This could be because the server is down or there is a problem with the network.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return
			
		callback("Looking for Thousand Parsec Server...")
		if failed(self.connection.connect(("libtpclient-py/%i.%i.%i " % version)+cs)):
			s  = _("The client connected to the host but it did not appear to be a Thousand Parsec server.\n")
			s += _("This could be because the server is down or the connection details are incorrect.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return

		callback("Logging In")
		if failed(self.connection.login(username, password)):
			s  = _("The client connected to the host but could not login because the username of password was incorrect.\n")
			s += _("This could be because you are connecting to the wrong server or mistyped the username or password.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return

		# Create a new cache
		self.application.cache = Cache(Cache.key(host, username))

	def CacheUpdate(self, callback):
		self.application.cache.update(self.connection, callback)
		self.application.cache.save()

	def OnCacheDirty(self, evt):
		"""\
		When the cache gets dirty we have to push the changes to the server.
		"""
		try:
			if evt.what == "orders":
				if evt.action in ("remove", "change"):
					if failed(self.connection.remove_orders(evt.id, evt.slot)):
						raise IOError("Unable to remove the order...")
				
				if evt.action in ("create", "change"):
					# FIXME: Maybe an insert_order should return the order object not okay/fail
					if failed(self.connection.insert_order(evt.id, evt.slot, evt.change)):
						raise IOError("Unable to insert the order...")

					if evt.slot == -1:
						evt.slot = len(self.application.cache.orders[evt.id])
						
					o = self.connection.get_orders(evt.id, evt.slot)[0]
					if failed(o):
						raise IOError("Unable to get the order..." + o[1])

					evt.change = o
			elif evt.what == "messages" and evt.action == "remove":
				if failed(self.connection.remove_messages(evt.id, evt.slot)):
					raise IOError("Unable to remove the message...")
			elif evt.what == "designs":
				# FIXME: Assuming that these should succeed is BAD!
				if evt.action == "remove":
					if failed(self.connection.remove_designs(evt.change)):
						raise IOError("Unable to remove the design...")
				if evt.action == "change":
					if failed(self.connection.change_design(evt.change)):
						raise IOError("Unable to change the design...")
				if evt.action == "create":
					result = self.connection.insert_design(evt.change)
					if failed(result):
						raise IOError("Unable to add the design...")
					
					# Need to update the event with the new ID of the design.
					evt.id = result.id
			elif evt.what == "categories":
				# FIXME: Assuming that these should succeed is BAD!
				if evt.action == "remove":
					if failed(self.connection.remove_categories(evt.change)):
						raise IOError("Unable to remove the category...")
				if evt.action == "change":
					if failed(self.connection.change_category(evt.change)):
						raise IOError("Unable to change the category...")
				if evt.action == "create":
					result = self.connection.insert_category(evt.change)
					if failed(result):
						raise IOError("Unable to add the category...")
					
					# Need to update the event with the new ID of the design.
					evt.id = result.id
			else:
				raise ValueError("Can't deal with that yet!")
			self.application.cache.apply(evt)
			self.application.Post(evt)

		except Exception, e:
			type, val, tb = sys.exc_info()
			sys.stderr.write("".join(traceback.format_exception(type, val, tb)))
			self.application.Post(self.NetworkFailureEvent(e))
			"There where the following errors when trying to send changes to the server:"
			"The following updates could not be made:"
