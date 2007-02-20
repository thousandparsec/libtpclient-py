
# Python imports
import os
import copy
import base64
import pprint
import struct
import traceback
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
from tp.netlib import Connection, failed, constants, objects
from tp.netlib.objects import Header, Description, OrderDescs, DynamicBaseOrder

# Local imports
from ChangeDict import ChangeDict

class Cache(object):
	"""\
	This is the a cache of the data downloaded from the network. 

	It can be pickled and restored at a later date to preserve the data accross application runs.
	"""
	version = 4

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
		print "Cache file", self.file
		if os.path.exists(self.file) and not new:
			# Load the previously cached status
			print "Loading previous saved data (from %s)." % (self.file,)
			try:
				self.load()
				return
			except (IOError, EOFError, KeyError), e:
				print e
				traceback.print_exc()
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

			elif evt.action == "change":
				d[evt.slot] = evt.change
			elif evt.action == "remove":
				del d[evt.slot]

			# FIXME: This should update order_number, number on Object/Board..

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
		d = pickle.load(f)
		if d.has_key('file'):
			del d['file']				# Stop the file being loaded
		self.__dict__.update(d)

		# Now load the order cache
		self.orders = ChangeDict()
		while True:
			d = f.read(Header.size)
			if len(d) != Header.size:
				if len(d) != 0:
					raise IOError("Garbage was found at the end!")
				break

			p = Header(d)

			d = f.read(p.length)
			p.process(d)

			# Descriptions
			if isinstance(p, Description):
				p.register()
			# Orders
			else:
				# Get the ID number
				id, = struct.unpack('!Q', f.read(8))
				if not self.objects.has_key(id):
					print "Cache Error: Found order (%s) for non-existant object (%s). " % (repr(p), id) 
					continue

				if not self.orders.has_key(id):
					self.orders[id] = (self.objects.times[id], [])
				self.orders[id].append(p)

		for id in self.objects.keys():
			if not self.orders.has_key(id):
				self.orders[id] = (self.objects.times[id], [])

	def save(self):
		"""\
		"""
		# We don't want this filename appearing in the cace
		file = self.file
		del self.file

		# Save the cache
		f = open(file, 'wb')
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
			if self.objects.has_key(id):
				for order in self.orders[id]:
					f.write(str(order))
					f.write(struct.pack('!Q', id))
		f.close()

		# Restore the file
		self.file = file

	def update(self, connection, callback):
		"""\
		Updates the cache using the connection.

		The callback function is called in the following way,

		callback(group=<mode>, state=<state>, message=<message>)

		The message string is a human readable message about what is happening.

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

		State is one of the following,
			start		- no more arguments
			todownload	- total, the total number of things to be downloaded
			progress	- some sort of undetermined progress occured
			failure		- some sort of failure when downloading occured
			downloaded	- amount, the number of things which have been downloaded
			finished	- no more arguments
		"""
		c = callback
		# FIXME: We should restart with an empty cache if the following has happened
		#	FIXME: This should compare any read-only attributes and see if they have change
		#	FIXME: This should check the current turn and see if the turn is strange (IE gone back in time)
		#	FIXME: Should check that none of the Order definitions have changed

		# Get the features this server support
#		c("connecting", "todownload", message="Looking for supported features...")
		self.features = connection.features()
#		c("connecting", "finished")

		c("orderdescs", "start", message="Getting order descriptions...")
		c("orderdescs", "progess", message="Working out the number of order descriptions to get..")
		ids = []
		for id, time in connection.get_orderdesc_ids(iter=True):
			if OrderDescs().has_key(id) and hasattr(OrderDescs()[id], "modify_time"):
				if time < OrderDescs()[id].modify_time:
					continue
			ids.append(id)
		c("orderdescs", "todownload", todownload=len(ids))

		for id in ids:
			desc = connection.get_orderdescs(id=id)[0]
			# Did we download the order description okay?
			if not failed(desc):
				c("orderdescs", "downloaded", amount=1, \
					message="Got order description %s (ID: %i) (last modified at %s)..." % (desc._name, id, time))
				desc.register()
			else:
				c("orderdescs", "failure",
					message="Failed to get order description with id, %i (last modified at %s)..." % (id, time))
		c("orderdescs", "finished", message="Finished getting order descriptions...")

		# Get all the objects
		#############################################################################
		#############################################################################
		toget = self.__getObjects(connection,   "objects", callback)
		if toget > 0:
			self.__getSubObjects(connection, toget, "objects", "orders", "order_number", callback)
		toget = self.__getObjects(connection,   "boards", callback)
		if toget > 0:
			self.__getSubObjects(connection, toget, "boards",  "messages", "number", callback)

		self.__getObjects(connection, "categories", callback)
		self.__getObjects(connection, "designs",    callback)
		self.__getObjects(connection, "components", callback)
		self.__getObjects(connection, "properties", callback)
		#self.__getObjects(connection, "players",    callback)
		self.__getObjects(connection, "resources",  callback)

		c("players", "start", message="Getting your player object...")
		self.players[0] = connection.get_players(0)[0]
		c("players", "finished", message="Gotten your player object...")

	def __getObjects(self, connection, plural_name, callback):
		"""\
		Get a thing which has a container.
		"""
		c = callback
		pn = plural_name

		if pn[-3:] == 'ies':
			sn = pn[:-3]+'y'
		elif pn[-1:] == 's':
			sn = pn[:-1]
		else:
			sn = pn

		def cache(id=None, self=self, pn=pn):
			if id==None:
				return getattr(self, pn)
			else:
				return getattr(self, pn)[id]

		c(pn, "start", message="Getting %s..." % pn)

		# Figure out the IDs to download
		c(pn, "progess", message="Working out the number of %s to get.." % pn)
		toget = []
		ids = []
		for id, time in getattr(connection, "get_%s_ids" % sn)(iter=True):
			ids.append(id)
			if not cache().has_key(id) or time > cache().times[id]:
				toget.append(id)
			# FIXME: This doesn't work if an thing disappears...
			#elif constants.FEATURE_ORDERED_OBJECT in self.features:
			#	break

		# Callback function
		def OnPacket(p, c=c, pn=pn, sn=sn, objects=objects):
			if isinstance(p, getattr(objects, sn.title())):
				c(pn, "downloaded", amount=1, \
					message="Got %s %s (id: %i) (last modified at %s)..." % (sn, p.name, p.id, p.modify_time))

		if len(toget) < 1:
			c(pn, "finished", message="No %s to get, skipping..." % pn)
			return 0

		# Download the XXX
		c(pn, "todownload", \
			message="Have %i %s to get..." % (len(toget), pn), todownload=len(toget))
		frames = getattr(connection, "get_%s" % pn)(ids=toget, callback=OnPacket)

		if failed(frames):
			raise IOError("Strange error occured, unable to request %s." % pn)

		for id, frame in zip(toget, frames):
			if not failed(frame):
				cache()[id] = (frame.modify_time, frame)
			elif cache().has_key(id):
				c(pn, "failure", \
					message="Failed to get the %s which was previously called %s." % (sn, cache(id).name))
				del cache()[id]
			else:
				c(pn, "failure", \
					message="Failed to get the %s with id %s." % (sn, id))

		c(pn, "progress", message="Cleaning up %s which have disappeared..." % pn)
		# Check for XXX which no longer exist..
		gotten = set(ids)
		having = set(cache().keys())
		difference = having.difference(gotten)
		for id in difference:
			c(pn, "progress", \
				message="Removing %s %s as it has disappeared..." % (sn, cache(id).name))
			del cache()[id]

		if pn == "objects":
			c(pn, "progress", \
				message="Building two way tree of the universe for speed...")
			def build(frame, parent=None, self=self):
				if parent:
					frame.parent = parent.id

				for id in frame.contains:
					build(cache(id), frame)
			build(cache(0))

		c(pn, "finished", message="Gotten all %s..." % pn)

		return toget

	def __getSubObjects(self, connection, toget, plural_name, subname, number, callback=None):
		c = callback
		pn = plural_name
		sn = plural_name[:-1]

		def cache(id=None, self=self, pn=pn):
			if id==None:
				return getattr(self, pn)
			else:
				return getattr(self, pn)[id]

		c = callback
		sb = subname

		c(sb, "start", message="Getting %s.." % sb)
		c(sb, "todownload", message="Have to get %s for %i %s.." % (sb, len(toget), pn), todownload=len(toget))

		# Set the blocking so we can pipeline the requests
		connection.setblocking(True)
		empty = []
		for id in toget:
			frame = cache(id)

			if getattr(frame, number) > 0:
				c(sb, "progress", \
					message="Sending a request for all %s on %s.." % (sb, str(frame.name)))
				getattr(connection, "get_%s" % sb)(id, range(0, getattr(frame, number)))
			else:
				c(sb, "progress", \
					message="Skipping requesting %s on %s as there are none!" % (sb, str(frame.name)))
				empty.append(id)

		for id in empty:
			getattr(self, sb)[id] = (cache(id).modify_time, [])
			toget.remove(id)

		# Wait for the response to the order requests
		while len(toget) > 0:
			result = None
			while result is None:
				result = connection.poll()

			id = toget.pop(0)
			frame = cache(id)

			if failed(result):
				c(sb, "failure", \
					message="Failed to get %s for %s (id: %s) (%s)..." % (sb, str(frame.name), frame.id, result[1]))
				result = []
			else:
				c(sb, "downloaded", amount=1, \
					message="Got %i %s for %s (id: %s)..." % (len(result), sb, str(frame.name), frame.id))
			getattr(self, sb)[id] = (cache(id).modify_time, result)

		c(sb, "progress", message="Cleaning up any stray %s.." % sb)
		for id in getattr(self, sb).keys():
			if not cache().has_key(id):
				c(sb, "progress", message="Found stray %s for %s.." % (sb, id))
				del getattr(self, sb)[id]

		connection.setblocking(False)
		c(sb, "finished", message="Gotten all the %s.." % sb)

