
# Python imports
import os
import sys
import copy
import base64
import pprint
import struct
import traceback

if sys.platform == "darwin":
	import pickle as pickle
else:
	import pickle as pickle
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
from tp.netlib.objects import Header, Description
from tp.netlib.objects import OrderDescs, DynamicBaseOrder
from tp.netlib.objects import ObjectDescs, DynamicBaseObject

# Local imports
# FIXME: Should I think about merging the ChangeList and ChangeDict?
from ChangeDict import ChangeDict
from ChangeList import ChangeList, ChangeNode

from threads import Event
from threadcheck import thread_checker, thread_safe

__CACHE = None
class Cache(object):
	"""\
	This is the a cache of the data downloaded from the network. 

	It can be pickled and restored at a later date to preserve the data accross application runs.
	"""
	__metaclass__ = thread_checker

	version = 7

	class CacheEvent(Event):
		"""\
		Raised when the game cache is made dirty. Contains a reference to what was updated.
		"""
		def __init__(self, what, action, id, *args, **kw):
			Event.__init__(self)

			if what in Cache.readonly:
				raise ValueError("Can not change that!")
			elif not what in Cache.readwrite:
				raise ValueError("Invalid value (%s) for what" % (what,))
			else:
				self.what = what

			if what in Cache.compound:
				if not action in Cache.actions_compound:
					raise ValueError("Invalid action (%s)" % (action,))
			else:
				if not action in Cache.actions:
					raise ValueError("Invalid action (%s)" % (action,))
			self.action = action

			self.id = id

			args = list(args)
			if what in Cache.compound:
				if len(args) == 2:
					self.node = args.pop(0)
				elif kw.has_key('node'):
					self.node = kw['node']
				elif kw.has_key('nodes'):
					if not action is "remove":
						raise ValueError("Slots is only valid with a remove action")
					self.node  = None
					self.nodes = kw['nodes']
				else:
					raise TypeError("A node is required for compound types.")
				if not hasattr(self, "nodes"):
					self.nodes = [self.node]

				# Do a type check for the nodes
				for node in self.nodes:
					if (not node is None) and not isinstance(node, ChangeNode):
						raise TypeError("Nodes must be of type ChangeNode not %s (%r)" % (type(node), node))

					assert node.inlist()

			if len(args) == 1:
				self.change = args.pop(0)
			elif kw.has_key('change'):
				self.change = kw['change']
			elif action is "remove":
				pass
			else:
				raise TypeError("The actual change needs to be added.")

		def __str__(self):
			if not self.what:
				return "<%s full-update>" % (self.__class__.__name__,)
			elif hasattr(self, 'node'):
				if self.node is None:
					return "<%s %s %s id=%i nodes=%r>" % (self.__class__.__name__, self.what, self.action, self.id, self.nodes)
				else:
					return "<%s %s %s id=%i node=%r>" % (self.__class__.__name__, self.what, self.action, self.id, self.node)
			else:
				return "<%s %s %s id=%i>" % (self.__class__.__name__, self.what, self.action, self.id)

		__repr__ = __str__

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
				Event.__init__(self)
				self.what = None
			else:
				CacheEvent.__init__(self, what, *args, **kw)

	# Read Only things can only be updated via the network
	readonly = ("features", "objects", "orderqueues", "orders_probe", "boards", "resources", "components", "properties", "players", "resources")
	# These can be updated via either side
	readwrite = ("orders", "messages", "categories", "designs")
	# How we can update the Cache
	actions = ("create", "remove", "change")
	actions_compound = ("create before", "create after", "remove", "change")
	compound = ("orders", "messages")

	@staticmethod
	def key(server, game, username):
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
			key = "%s//%s@%s(%s)" % (p, username, s, game.ctime)
		return key

	@staticmethod
	def configkey(key):
		if isinstance(key, unicode):
			key = key.encode('utf-8')
		key = base64.encodestring(key)[:-2].replace('/', '')
		return key

	@staticmethod
	def configdir():
		dirs = [("APPDATA", "Thousand Parsec"), ("HOME", ".tp"), (".", "var")]
		for base, extra in dirs:
			if base in os.environ:
				base = os.environ[base]
				break
			elif base != ".":
				continue

		return os.path.join(base, extra)

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
			except (IOError, EOFError, KeyError, pickle.PickleError), e:
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
		self.orderqueues    = ChangeDict()
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

	@thread_safe # FIXME: This probably isn't thread safe!
	def apply(self, *args, **kw):
		"""\
		Given a CacheDirtyEvent, it sets up the changes...
		"""
		evt = Cache.CacheDirtyEvent(*args, **kw)

		if not evt.what in Cache.compound:
			return evt
		else:
			d = getattr(self, evt.what)[evt.id]

			if evt.action == "remove":
				for node in evt.nodes:
					node.AddState("removing")
				evt.change = None

			elif evt.action == "change":
				assert len(evt.nodes) == 1
				assert not evt.node.LastState in ("removed", "removing")

				evt.node.AddState("updating", evt.change)
				evt.change = evt.node

			elif evt.action.startswith("create"):
				assert len(evt.nodes) == 1

				# Create the new node
				newnode = ChangeNode(None)
				newnode.AddState("creating", evt.change)

				# Insert the node
				if evt.action == "create after":
					d.insert_after(evt.node,  newnode)
				elif evt.action == "create before":
					d.insert_before(evt.node, newnode)
				else:
					assert False, "Unknown action!"

				# Set the new node as the change
				evt.change = newnode
			else:
				assert False, "Unknown action!"

			return evt

	def commit(self, evt):
		"""\
		Given a CacheDirtyEvent it applies the changes to the cache.
		It should be called after the changes have been confimed by the server.

		It then mutates the event into a CacheUpdateEvent.
		"""
		if not isinstance(evt, self.CacheDirtyEvent):
			raise TypeError("I can only accept CacheDirtyEvents")

		if not evt.what in Cache.compound:
			if evt.action == "create" or evt.action == "change":
				getattr(self, evt.what)[evt.id] = (evt.change.modify_time, evt.change)
			elif evt.action == "remove":
				del getattr(self, evt.what)[evt.id]

		else:
			d = getattr(self, evt.what)[evt.id]

			if evt.action.startswith("create") or evt.action == "change":
				node = evt.change

				assert node.CurrentState in ("creating", "updating"), "Current state (%s) doesn't match action %s" % (node.CurrentState, evt.action)

				node.PopState()

			elif evt.action == "remove":
				for node in evt.nodes:
					assert node.CurrentState == "removing"

					del d[node.id]
					node.PopState()
			else:
				raise SystemError("Unknown node state!")


		evt.__class__ = self.CacheUpdateEvent

	def load(self):
		"""\
		"""
		f = open(self.file, 'rb')

		# Read in the version number
		v, = struct.unpack('!I', f.read(4))
		if v != self.version:
			raise IOError("The cache is not of this version! (It's version %s)" % (v,))

		# Now load the object cache
		objectdescs, = struct.unpack('!I', f.read(4))
		for i in xrange(0, objectdescs):
			d = f.read(Header.size)

			p = Header.fromstr(d)

			d = f.read(p._length)
			p.__process__(d)
			
			assert isinstance(p, Description)
			p.register()

		# Now load the order cache
		orderdescs, = struct.unpack('!I', f.read(4))
		for i in xrange(0, orderdescs):
			d = f.read(Header.size)
			p = Header.fromstr(d)

			d = f.read(p._length)
			p.__process__(d)

			assert isinstance(p, Description)
			p.register()

		# First load the pickle
		d = pickle.load(f)
		if d.has_key('file'):
			del d['file']				# Stop the file being loaded

		for clist in d['orders'].values():
			for node in clist:
				for pending in node._pending:
					pending.__class__ = OrderDescs()[pending.subtype]
				node._what.__class__ = OrderDescs()[node._what.subtype]

		for node in d['objects'].values():
			node.__class__ = ObjectDescs()[node.subtype]

		self.__dict__.update(d)

	def save(self):
		"""\
		"""
		# We don't want this filename appearing in the cace
		file = self.file
		del self.file

		# Save the cache
		f = open(file, 'wb')
		f.write(struct.pack('!I', self.version))

		# Save each dynamic object description
		descriptions = ObjectDescs()
		f.write(struct.pack('!I', len(descriptions)))
		for objectdesc in descriptions.values():
			f.write(str(objectdesc.packet))
	
		# Save each dynamic order description
		descriptions = OrderDescs()
		f.write(struct.pack('!I', len(descriptions)))
		for orderdesc in descriptions.values():
			f.write(str(orderdesc.packet))

		p = copy.copy(self.__dict__)
		del p['_thread']

		# Stop referencing the dynamic orders
		for node in p['objects'].values():
			subtype = node.subtype
			node.__class__ = DynamicBaseObject
			node.subtype = subtype

		for clist in p['orders'].values():
			for node in clist:
				for pending in node._pending:
					subtype = pending.subtype
					pending.__class__ = DynamicBaseOrder
					pending.subtype = subtype

				subtype = node._what.subtype
				node._what.__class__ = DynamicBaseOrder
				node._what.subtype = subtype

		pickle.dump(p, f)

		# FIXME: The above copy should not be mutating!
		for clist in p['orders'].values():
			for node in clist:
				for pending in node._pending:
					pending.__class__ = OrderDescs()[pending.subtype]
				node._what.__class__ = OrderDescs()[node._what.subtype]

		for node in p['objects'].values():
			node.__class__ = ObjectDescs()[node.subtype]
			
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
#		c("connecting", "todownload", message=_("Looking for supported features..."))
		self.features = connection.features()
#		c("connecting", "finished")

		c("orderdescs", "start", message=_("Getting order descriptions..."))
		c("orderdescs", "progess", message=_("Working out the number of order descriptions to get.."))
		ids = []
		for id, time in connection.get_orderdesc_ids(iter=True):
			if OrderDescs().has_key(id) and hasattr(OrderDescs()[id], "modify_time"):
				if time <= OrderDescs()[id].modify_time:
					continue
			ids.append(id)
		c("orderdescs", "todownload", todownload=len(ids))

		for id in ids:
			desc = connection.get_orderdescs(id=id)[0]
			# Did we download the order description okay?
			if not failed(desc):
				c("orderdescs", "downloaded", amount=1, \
					message=_("Got order description %(order)s (ID: %(id)i) (last modified at %(time)s)...") % {'order': desc._name, 'id': id, 'time': time})
				desc.register()
			else:
				c("orderdescs", "failure",
					message=_("Failed to get order description with ID %(id)i (last modified at %(time)s)...") % {'id': id, 'time': time})

		c("orderdescs", "finished", message=_("Recieved all order descriptions..."))

		# Get all the objects
		#############################################################################
		#############################################################################
		self.__getObjects(connection, "objects", callback)

		toget = self.__getObjects(connection, "orderqueues", callback)
		if len(toget) > 0:
			self.__getSubObjects(connection, toget, "orderqueues",  "orders", "numorders", callback)
		else:
			c("orders", "finished", message=_("Don't have any orders to get.."))

		toget = self.__getObjects(connection, "boards", callback)
		if len(toget) > 0:
			self.__getSubObjects(connection, toget, "boards",  "messages", "number", callback)
		else:
			c("messages", "finished", message=_("Don't have any messages to get.."))

		self.__getObjects(connection, "categories", callback)
		self.__getObjects(connection, "designs",    callback)
		self.__getObjects(connection, "components", callback)
		self.__getObjects(connection, "properties", callback)
		self.__getObjects(connection, "players",    callback)
		self.__getObjects(connection, "resources",  callback)

		self.players[0] = connection.get_players(0)[0]

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

		c(pn, "start", message=_("Getting %s...") % pn)

		# Figure out the IDs to download
		c(pn, "progess", message=_("Working out the number of %s to get..") % pn)
		toget = []
		ids = []

		for id, time in getattr(connection, "get_%s_ids" % sn)(iter=True):
			ids.append(id)
			if not cache().has_key(id):
				c(pn, "info", message=_("%(plural_name)s: Getting new object with %(id)s.") % {'plural_name': pn, 'id': id})
				toget.append(id)
			elif time > cache().times[id]:
				c(pn, "info", message=_("%(plural_name)s: Getting %(id)s (%(name)s) as %(time)s > %(cached_time)s") % {'plural_name': pn, 'id': id, 'name': cache(id).name, 'time': time, 'cached_time': cache().times[id]})
				toget.append(id)
			else:
				c(pn, "info", message=_("%(plural_name)s: Not getting %(id)s (%(name)s) as %(time)s <= %(cached_time)s") % {'plural_name': pn, 'id': id, 'name': cache(id).name, 'time': time, 'cached_time': cache().times[id]})

		# Callback function
		def OnPacket(p, c=c, pn=pn, sn=sn, objects=objects):
			if isinstance(p, getattr(objects, sn.title())):
				c(pn, "downloaded", amount=1, \
					message=_("Got %(singular_name)s %(name)s (ID: %(id)i) (last modified at %(time)s)...") % {'singular_name': sn, 'name': p.name, 'id': p.id, 'time': p.modify_time})

		if len(toget) > 0:
			# Download the XXX
			c(pn, "todownload", \
				message=_("Have %(amount)i %(plural_name)s to get...") % {'amount': len(toget), 'plural_name': pn}, todownload=len(toget))
			frames = getattr(connection, "get_%s" % pn)(ids=toget, callback=OnPacket)

			if failed(frames):
				raise IOError("Strange error occured, unable to request %s." % pn)

			# Match the results to the associated ids
			for id, frame in zip(toget, frames):
				if not failed(frame):
					if cache().has_key(id):
						c(pn, "info", \
							message=_("%(plural_name)s: Updating %(id)s (%(name)s - %(frame_name)s) with modtime %(time)s") % {'plural_name': pn, 'id': id, 'name': cache(id).name, 'frame_name': frame.name, 'time': frame.modify_time})
					else:
						c(pn, "info", \
							message=_("%(plural_name)s: Updating %(id)s (%(frame_name)s - New!) with modtime %(time)s") % {'plural_name': pn, 'id': id, 'frame_name': frame.name, 'time': frame.modify_time})
					cache()[id] = (frame.modify_time, frame)
				else:
					if cache().has_key(id):
						c(pn, "failure", \
							message=_("Failed to get the %(singular_name)s which was previously called %(name)s. (%(error)s)") % {'singular_name': sn, 'name': cache(id).name, 'error': frame[-1]})
					else:
						c(pn, "failure", \
							message=_("Failed to get the %(singular_name)s with ID %(id)s. (%(error)s)") % {'singular_name': sn, 'id': id, 'error': frame[-1]})

					# Don't get any sub-objects for this 
					toget.remove(id)

					# This object does not really exist on the server
					ids.remove(id)

		c(pn, "progress", message=_("Cleaning up %s which have disappeared...") % pn)

		# Remove any objects which are no longer on the server
		onserver  = set(ids)
		havelocal = set(cache().keys())
		for id in havelocal-onserver:
			c(pn, "progress", \
				message=_("Removing %(singular_name)s %(name)s as it has disappeared...") % {'singular_name': sn, 'name': cache(id).name})
			del cache()[id]

		if pn == "objects":
			c(pn, "progress", \
				message=_("Building two way tree of the universe for speed..."))
			def build(frame, parent=None, self=self):
				if parent:
					frame.parent = parent.id

				for id in frame.contains:
					try:
						build(cache(id), frame)
					except KeyError:
						from threads import NetworkThread
						raise NetworkThread.NetworkFailureEvent("%s (ID %i) references an object with ID %i, which does not exist!" % (frame.name, frame.id, id))
			build(cache(0))

		c(pn, "finished", message=_("Received all %s...") % pn)

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

		c(sb, "start", message=_("Getting %s..") % sb)
		c(sb, "todownload", message=_("Have to get %(name)s for %(ammount)i %(plural_name)s..") % {'name': sb, 'ammount': len(toget), 'plural_name': pn}, todownload=len(toget))

		# Set the blocking so we can pipeline the requests
		connection.setblocking(True)
		empty = []
		for id in toget:
			frame = cache(id)

			if getattr(frame, number) > 0:
				c(sb, "progress", \
					message=_("Sending a request for all %(name)s on %(frame_name)s..") % {'name': sb, 'frame_name': unicode(frame.name)})
				getattr(connection, "get_%s" % sb)(id, range(0, getattr(frame, number)))
			else:
				c(sb, "progress", \
					message=_("Skipping requesting %(name)s on %(frame_name)s as there are none!") % {'name': sb, 'frame_name': unicode(frame.name)})
				empty.append(id)

		for id in empty:
			getattr(self, sb)[id] = (cache(id).modify_time, ChangeList())
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
					message=_("Failed to get %(name)s for %(frame_name)s (ID: %(id)s) (%(result)s)...") % {'name': sb, 'frame_name': unicode(frame.name), 'id': frame.id, 'result': result[1]})
				result = []
			else:
				c(sb, "downloaded", amount=1, \
					message=_("Got %(ammount)i %(name)s for %(frame_name)s (ID: %(id)s)...") % {'ammount': len(result), 'name': sb, 'frame_name': unicode(frame.name), 'id': frame.id})

			subs = ChangeList()
			for sub in result:
				subs.append(ChangeNode(sub))

			getattr(self, sb)[id] = (cache(id).modify_time, subs)

		c(sb, "progress", message=_("Cleaning up any stray %s..") % sb)
		for id in getattr(self, sb).keys():
			if not cache().has_key(id):
				c(sb, "progress", message=_("Found stray %(name)s for %(id)s..") % {'name': sb, 'id': id})
				del getattr(self, sb)[id]

		connection.setblocking(False)
		c(sb, "finished", message=_("Received all the %s..") % sb)

def apply(connection, evt, cache):
	"""\
	Applies a CacheDirty event to a connection.
	"""
	if evt.what == "orders":
		d = cache.orders[evt.id]

		if evt.action == "remove":
			slots = []
			for node in evt.nodes:
				assert isinstance(node, ChangeNode)
				slots.append(d.slot(node))
			slots.sort(reverse=True)

			if failed(connection.remove_orders(evt.id, slots)):
				raise IOError("Unable to remove the order...")
		
		elif evt.action in ("create after", "create before", "change"):
			assert len(evt.nodes) == 1, "%s event has multiple slots! (%r) WTF?" % (evt.action, evt.nodes)
			assert evt.change in d

			slot = d.slot(evt.change)
			if evt.action == "change":
				# Remove the old order
				if failed(connection.remove_orders(evt.id, slot)):
					raise IOError("Unable to remove the order...")

			assert not evt.change.CurrentState == "idle"
			assert not evt.change.PendingOrder is None
			if failed(connection.insert_order(evt.id, slot, evt.change.PendingOrder)):
				raise IOError("Unable to insert the order...")

			o = connection.get_orders(evt.id, slot)[0]
			if failed(o):
				raise IOError("Unable to get the order..." + o[1])

			evt.change.UpdatePending(o)

		else:
			raise SystemError("Unknown Action")

	elif evt.what == "messages" and evt.action == "remove":
		d = cache.messages[evt.id]

		slots = []
		for node in evt.nodes:
			slots.append(d.slot(node))
		slots.sort(reverse=True)

		if failed(connection.remove_messages(evt.id, slots)):
			raise IOError("Unable to remove the message...")

	elif evt.what == "designs":

		# FIXME: Assuming that these should succeed is BAD!
		if evt.action == "remove":
			if failed(connection.remove_designs(evt.change)):
				raise IOError("Unable to remove the design...")
		if evt.action == "change":
			if failed(connection.change_design(evt.change)):
				raise IOError("Unable to change the design...")
		if evt.action == "create":
			result = connection.insert_design(evt.change)
			if failed(result):
				raise IOError("Unable to add the design...")
			
			evt.id = result.id
			evt.change = result

	elif evt.what == "categories":

		# FIXME: Assuming that these should succeed is BAD!
		if evt.action == "remove":
			if failed(connection.remove_categories(evt.change)):
				raise IOError("Unable to remove the category...")
		if evt.action == "change":
			if failed(connection.change_category(evt.change)):
				raise IOError("Unable to change the category...")
		if evt.action == "create":
			result = connection.insert_category(evt.change)
			if failed(result):
				raise IOError("Unable to add the category...")
			
			evt.id = result.id
			evt.change = result
	else:
		raise ValueError("Can't deal with that yet!")

	cache.commit(evt)
	return evt
