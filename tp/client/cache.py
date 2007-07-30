
# Python imports
import os
import copy
import base64
import pprint
import struct
import cPickle as pickle
from datetime import datetime
def df(time):
	if type(time) in (float, int, long):
		return datetime.utcfromtimestamp(time).strftime('%c')
	elif type(time) is datetime:
		return time.strftime('%c')
	else:
		raise TypeError("Unable to output this type...")

try:
	set()
except NameError:
	from sets import Set as set

# Other library imports
from tp.netlib import Connection, failed, constants
from tp.netlib.objects import Header, Description, OrderDescs, DynamicBaseOrder

# Local imports
from ChangeDict import ChangeDict

class Cache(object):
	"""\
	This is the a cache of the data downloaded from the network. 

	It can be pickled and restored at a later date to preserve the data accross application runs.

	To update the cache you use CacheDirtyEvents in the following way...
		

	"""
	version = 3

	class CacheEvent(object):
		"""\
		Raised when the game cache is made dirty. Contains a reference to what was updated.
		"""
		def __init__(self, what, action, id, *args, **kw):
			if what in Cache.readonly:
				raise ValueError("Can not change that!")
			elif not what in Cache.readwrite:
				raise ValueError("Invalid value (%s) for what" % (what,))
			else:
				self.what = what

			if not action in Cache.actions:
				raise ValueError("Invalid action (%s)" % (action,))
			else:
				self.action = action

			self.id = id

			args = list(args)
			if what in Cache.compound:
				if len(args) == 2:
					self.slot = args.pop(0)
				elif kw.has_key('slot'):
					self.slot = kw['slot']
				else:
					raise TypeError("A slot value is required for compound types.")

			if len(args) == 1:
				self.change = args.pop(0)
			elif kw.has_key('change'):
				self.change = kw['change']
			else:
				raise TypeError("The actual change needs to be added.")

		def __str__(self):
			if not self.what:
				return "<%s full-update>" % (self.__class__,)
			elif hasattr(self, 'slot'):
				return "<%s %s %s id=%i slot=%i>" % (self.__class__, self.what, self.action, self.id, self.slot)
			else:
				return "<%s %s %s id=%i>" % (self.__class__, self.what, self.action, self.id)

	class CacheDirtyEvent(CacheEvent):
		"""\
		Raised when the game cache is made dirty. Contains a reference to what was updated.
		"""
		pass

	class CacheUpdateEvent(CacheEvent):
		"""\
		Raised when the game cache is changed. Contains a reference to what was updated. 
		If the what is None a new cache has been created.
		"""
		def __init__(self, what, *args, **kw):
			if what == None:
				self.what = None
			else:
				CacheEvent.__init__(self, what, *args, **kw)

	# Read Only things can only be updated via the network
	readonly = ("features", "objects", "orders_probe", "boards", "resources", "components", "properties", "players", "resources")
	# These can be updated via either side
	readwrite = ("orders", "messages", "categories", "designs")
	# How we can update the Cache
	actions = ("create", "remove", "change")
	compound = ("orders", "messages")

	def key(server, username):
		key = server

		p = ['tp://', 'tps://', 'http://', 'https://']
		found = False
		for p in p:
			if key.startswith(p):
				found = True
				break
		if not found:
			key = 'tp://' + key
		if key.find('@') == -1:
			p, s = key.split('//', 1)
			key = "%s//%s@%s" % (p, username, s)
		return key
	key = staticmethod(key)

	def configkey(key):
		key = base64.encodestring(key)[:-2]
		return key
	configkey = staticmethod(configkey)

	def configdir():
		dirs = [("APPDATA", "Thousand Parsec"), ("HOME", ".tp"), (".", "var")]
		for base, extra in dirs:
			if base in os.environ:
				base = os.environ[base]
				break
			elif base != ".":
				continue

		return os.path.join(base, extra)
	configdir = staticmethod(configdir)

	def __init__(self, key, configdir=None, new=False):
		"""\
		It is important that key constructed the following way,

		protocol://username@server:port/

		Everything must be there, even if the port is the default.
		"""
		if configdir == None:
			configdir = Cache.configdir()

		if not os.path.exists(configdir):
			os.mkdir(configdir)

		key = Cache.configkey(key)

		self.file = os.path.join(configdir, "cache.%s" % (key,))
		if os.path.exists(self.file) and not new:
			# Load the previously cached status
			print "Loading previous saved data (from %s)." % (self.file,)
			try:
				self.load()
				return
			except (IOError, EOFError), e:
				print e
				print "Unable to load the data, saved cache must be corrupt."
		print "Creating the Cache fresh (%s)." % (self.file,)
		self.new()

	def new(self):
		# Features
		self.features		= []

		# The object stuff
		self.objects		= ChangeDict()
		self.orders			= ChangeDict()
		self.orders_probe	= ChangeDict()

		# The message boards
		self.boards			= ChangeDict()
		self.messages		= ChangeDict()

		# Design stuff
		self.categories		= ChangeDict()
		self.designs		= ChangeDict()
		self.components		= ChangeDict()
		self.properties		= ChangeDict()

		self.players		= ChangeDict()
		self.resources		= ChangeDict()

	def apply(self, evt):
		"""\
		Given a CacheDirtyEvent it applies the changes to the cache.
		It then mutates the event into a CacheUpdateEvent.
		"""
		if not isinstance(evt, self.CacheDirtyEvent):
			raise TypeError("I can only accept CacheDirtyEvents")

		if not evt.what in Cache.compound:
			if evt.action == "create" or evt.action == "change":
				getattr(self, evt.what)[evt.id] = (-1, evt.change)
			elif evt.action == "remove":
				del getattr(self, evt.what)[evt.id]
		else:
			d = getattr(self, evt.what)[evt.id]
			if evt.action == "create":
				if evt.slot == -1:
					d.append(evt.change)
				else:
					d.insert(evt.slot, evt.change)

				if evt.what is "orders":
					self.objects[evt.id].order_number += 1

			elif evt.action == "change":
				d[evt.slot] = evt.change
			elif evt.action == "remove":
				if not isinstance(evt.slot, (list, tuple)):
					evt.slot = [evt.slot]
				for slot in evt.slot:
					del d[slot]

					if evt.what is "orders":
						self.objects[evt.id].order_number -= 1

		evt.__class__ = self.CacheUpdateEvent

	def load(self):
		"""\
		"""
		f = open(self.file, 'rb')

		# Read in the version number
		v, = struct.unpack('!I', f.read(4))
		if v != self.version:
			raise IOError("The cache is not of this version! (It's version %s)" % (v,))

		# First load the pickle
		self.__dict__ = pickle.load(f)

		# Now load the order cache
		self.orders = ChangeDict()
		while True:
			d = f.read(Header.size)
			if len(d) != Header.size:
				if len(d) != 0:
					raise IOError("Garbage was found at the end!")
				break

			p = Header.fromstr(d)

			d = f.read(p.length)
			p.__process__(d)

			# Descriptions
			if isinstance(p, Description):
				p.register()
			# Orders
			else:
				# Get the ID number
				id, = struct.unpack('!Q', f.read(8))

				if not self.orders.has_key(id):
					self.orders[id] = (self.objects.times[id], [])
				self.orders[id].append(p)

		for id in self.objects.keys():
			if not self.orders.has_key(id):
				self.orders[id] = (self.objects.times[id], [])

		#pprint.pprint(self.__dict__)

	def save(self):
		"""\
		"""
		#pprint.pprint(self.__dict__)

		# Save the cache
		f = open(self.file, 'wb')
		f.write(struct.pack('!I', self.version))

		p = copy.copy(self.__dict__)
		del p['orders']
		pickle.dump(p, f)

		# Save each dynamic order description
		for orderdesc in OrderDescs().values():
			#print orderdesc, type(orderdesc), issubclass(orderdesc, DynamicBaseOrder)
			if issubclass(orderdesc, DynamicBaseOrder):
				f.write(str(orderdesc.packet))

		# Save each order now
		for id in self.orders.keys():
			for order in self.orders[id]:
				f.write(str(order))
				f.write(struct.pack('!Q', id))

	def update(self, connection, callback):
		"""\
		Updates the cache using the connection.

		The callback function is called in the following way,

		callback(<message string>, group=<mode>)
		callback(<message string>, group=<mode>, total=<total>)
		callback(<message string>, group=<mode>, number=<number>)

		The message string is a human readable message about what is happening.

		total is the total number of objects in this group
		number is the current object which is being downloaded

		Group is the current group of things been updated the possible choices are,
			objects
			orders
			orders_probe
			boards
			messages
			categories
			designs
			components
			properties
			players
			resources
		"""

		# FIXME: We should restart with an empty cache if the following has happened
		#	FIXME: This should compare any read-only attributes and see if they have change
		#	FIXME: This should check the current turn and see if the turn is strange (IE gone back in time)
		#	FIXME: Should check that none of the Order definitions have changed


		# Get the features this server support
		callback("Looking for supported features...", mode="connecting")
		self.features = connection.features()

		# Get all the objects
		# -----------------------------------------------------------------------------------
		callback("Getting objects...", mode="objects")

		# Figure out the IDs to download
		toget = []
		ids = []
		for id, time in connection.get_object_ids(iter=True):
			ids.append(id)
			if not self.objects.has_key(id) or time > self.objects.times[id]:
				toget.append(id)
# FIXME: This doesn't work if an object disappears...
#			elif constants.FEATURE_ORDERED_OBJECT in self.features:
#				break

		# Callback function
		def OnPacket(p, callback=callback):
			if not failed(p):
				callback("Got object with ID of %i (last modified at %s)..." % (p.id, df(p.modify_time)), add=1)
			else:
				callback("Get object failed...", add=1)

		# Download the objects
		callback("Have %i objects to get..." % len(toget), of=len(toget))
		frames = connection.get_objects(ids=toget, callback=OnPacket)
		callback("Gotten all objects...")

		# Set the blocking so we can pipeline the order requests
		connection.setblocking(True)
		if failed(frames):
			raise IOError("Failed to get objects..")

		for id, object in zip(toget, frames):
			# Did we download the object okay?
			if failed(object):
				# Clean up the object
				if self.objects.has_key(id):
					del self.objects[id]

					if self.orders.has_key(id):
						del self.orders[id]
				continue

			self.objects[id] = (object.modify_time, object)

			# Pipeline the get order requests
			self.orders[id] = (object.modify_time, [])
			connection.get_orders(id, range(0, object.order_number))

		# Wait for the response to the order requests
		while len(toget) > 0:
			result = None
			while result is None:
				result = connection.poll()

			id = toget.pop(0)
			#print id, repr(result)

			if failed(result):
				continue

			self.orders[id] = (self.objects[id].modify_time, result)

		# Check for objects which no longer exist..
		# FIXME: There should be a better way to do this
		if len(ids) != len(self.objects):
			gotten = set(ids)
			having = set(self.objects.keys())

			difference = having.difference(gotten)
			#print "diff", difference
			for id in difference:
				del self.objects[id]
				if self.orders.has_key(id):
					del self.orders[id]

		connection.setblocking(False)

		#print "Building two way Universe Tree for speed"
		def build(object, parent=None, self=self):
			if parent:
				object.parent = parent.id
			for id in object.contains:
				build(self.objects[id], object)
		build(self.objects[0])

		# Get all the boards 
		# -----------------------------------------------------------------------------------
		callback("Getting boards...", mode="boards")

		# Figure out the IDs to download
		toget = []
		ids = []
		for id, time in connection.get_board_ids(iter=True):
			ids.append(id)
			if not self.boards.has_key(id) or time > self.boards.times[id]:
				toget.append(id)
# FIXME: This doesn't work if an object disappears...
#			elif constants.FEATURE_ORDERED_BOARD in self.features:
#				break

		# Callback function
		def OnPacket(p, callback=callback):
			if not failed(p):
				callback("Got board with ID of %i (last modified at %s)..." % (p.id, df(p.modify_time)), add=1)
			else:
				callback("Get board failed...", add=1)

		# Download the boards
		callback("Have %i boards to get..." % len(toget), of=len(toget))
		frames = []
		if len(toget) > 0:
			frames = connection.get_boards(ids=toget, callback=OnPacket)
		callback("Gotten all boards...")

		# Set the blocking so we can pipeline the order requests
		connection.setblocking(True)

		for id, board in zip(toget, frames):
			# Did we download the board okay?
			if failed(board):
				# Clean up the board
				if self.boards.has_key(id):
					del self.boards[id]

					if self.messages.has_key(id):
						del self.messages[id]
				continue

			self.boards[id] = (time, board)

			# Pipeline the get order requests
			self.messages[id] = (time, [])
			connection.get_messages(id, range(0, board.number))

		while len(toget) > 0:
			result = None
			while result is None:
				result = connection.poll()

			id = toget.pop(0)
			#print id, repr(result)

			if failed(result):
				continue

			self.messages[id] = (self.boards[id].modify_time, result)

		connection.setblocking(False)

		# Check for boards which no longer exist..
		# FIXME: There should be a better way to do this
		if len(ids) != len(self.boards):
			gotten = set(ids)
			having = set(self.boards.keys())

			difference = having.difference(gotten)
			for id in difference:
				del self.boards[id]
				if self.messages.has_key(id):
					del self.messages[id]

		# Get all the order descriptions
		# -----------------------------------------------------------------------------------
		callback("Getting order descriptions...", mode="order_descs")
		iter = connection.get_orderdesc_ids(iter=True)

		for id, time in iter:
			callback("Getting order description with id of %i (last modified at %s)..." % (id, df(time)), of=iter.total)

			desc = connection.get_orderdescs(id=id)[0]

			# Did we download the order description okay?
			if not failed(desc):
				desc.register()
			else:
				print "Warning: failed to get %i" % id, desc

			callback("Got order description with id of %i (last modified at %s)..." % (id, df(time)), add=1)

		def get_all(name, get_ids, get, cache, feature, callback=callback):
			callback("Getting %s..." % name)

			# Figure out the IDs to download
			toget = []
			for id, time in get_ids(iter=True):
				if not cache.has_key(id) or time > cache.times[id]:
					toget.append(id)
				elif feature in self.features:
					break

			# If there is nothing left to do
			if len(toget) == 0:
				return

			# Callback function
			def OnPacket(p, callback=callback):
				if not failed(p):
					callback("Got %s with ID of %i (last modified at %s)..." % (name, p.id, df(p.modify_time)), add=1)
				else:
					callback("Getting %s failed..." % name, add=1)

			# Download the objects
			callback("Have %i %s to get..." % (len(toget), name), of=len(toget))
			frames = get(ids=toget, callback=OnPacket)
			callback("Gotten all %s..." % name)

			for id, object in zip(toget, frames):
				# Did we download the object okay?
				if failed(object):
					# Clean up the object
					if cache.has_key(id):
						del cache[id]
					continue

				cache[id] = (time, object)

		callback("Getting design objects...", mode="designs")
		get_all("Categories", connection.get_category_ids, connection.get_categories, 
					self.categories, constants.FEATURE_ORDERED_CATEGORY)

		get_all("Designs", connection.get_design_ids, connection.get_designs, 
					self.designs, constants.FEATURE_ORDERED_DESIGN)

		get_all("Components", connection.get_component_ids, connection.get_components, 
					self.components, constants.FEATURE_ORDERED_COMPONENT)

		get_all("Properties", connection.get_property_ids, connection.get_properties, 
					self.properties, constants.FEATURE_ORDERED_PROPERTY)

		callback("Getting all other objects...", mode="remaining")
		get_all("Resources", connection.get_resource_ids, connection.get_resources, 
					self.resources, constants.FEATURE_ORDERED_RESOURCE)

		#get_all("Players", connection.get_player_ids, connection.get_players, 
		#			self.players, constants.FEATURE_ORDERED_PLAYERS)
		self.players[0] = connection.get_players(0)[0]
		#print self.players
		return
