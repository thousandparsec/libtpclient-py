
import pprint
import socket
import sys
import time
import threading
import traceback


from cache import Cache
from media import Media

from config import load_data, save_data
from version import version

def nop(*args, **kw):
	return

class Application(object):
	"""
	Container for all the applications threads and the network cache.

	Calling accross threads requires you to use the .Call method on each thread - DO NOT call directly!
	The cache can be accessed by either thread at any time - be careful.
	"""
	MediaClass = None
	FinderClass = None

	def __init__(self):
		print self.GUIClass, self.NetworkClass, self.MediaClass, self.FinderClass
		self.gui = self.GUIClass(self)
		self.network = self.NetworkClass(self)
		if not self.MediaClass is None:
			self.media = self.MediaClass(self)
		else:
			self.media = None
		if not self.FinderClass is None:
			self.finder = self.FinderClass(self)
		else:
			self.finder = None

		print self.gui, self.network, self.media, self.finder
		self.cache = None
		
		# Load the Configuration
		self.ConfigLoad()

	def Run(self):
		"""\
		Set the application running.
		"""
		print "Application.Run"
		print self.gui, self.network, self.media, self.finder
		self.network.start()

		if not self.finder is None:
			print "Finder start..."
			self.finder.start()
		else:
			print "Finder not starting..."

		if not self.media is None:
			print "Media Start..."
			self.media.start()
		else:
			print "Not Media Start..."

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
	
		self.gui.ConfigLoad(config)

	def Post(self, event):
		"""\
		Post an application wide event to every thread.
		"""
		self.network.Call(self.network.Post, event)
		self.finder.Call(self.finder.Post, event)
		self.media.Call(self.media.Post, event)
		self.gui.Call(self.gui.Post, event)

	def Exit(self):
		"""
		Exit the program.
		"""
		if hasattr(self, "closing"):
			return
		self.closing = True

		self.finder.Cleanup()
		self.network.Cleanup()
		self.media.Cleanup()
		self.gui.Cleanup()

class CallThreadStop(Exception):
	pass
ThreadStop = CallThreadStop

class CallThread(threading.Thread):
	"""\
	A call thread is thread which lets you queue up functions to be called
	in the thread.

	Functions are called in the order they are queue and there is no prempting
	or other fancy stuff.
	"""

	def __init__(self):
		threading.Thread.__init__(self)
		self.exit = False
		self.reset = False
		self.tocall = []
	
	def run(self):
		while not self.exit:
			self.every()

			if len(self.tocall) <= 0:
				self.idle()
				continue
	
			method, args, kw = self.tocall.pop(0)
			try:
				method(*args, **kw)
			except CallThreadStop, e:
				self.Reset()
				self.reset = False
			except Exception, e:
				self.error(e)

	def every(self):
		"""\
		Called every time th run goes around a loop.

		It is called before functions are poped of the tocall list. This mean 
		it could be used to reorganise the pending requests (or even remove
		some).

		By default it does nothing.
		"""
		pass

	def idle(self):
		"""\
		Called when there is nothing left to do. Will keep getting called until
		there is something to be done.

		The default sleeps for 100ms (should most probably sleep if you don't
		want to consume 100% of the CPU).
		"""
		time.sleep(0.1)

	def error(self, error):
		"""\
		Called when an exception occurs in a function which was called. 

		The default just prints out the traceback to stderr.
		"""
		pass

	def Reset(self):
		#del self.tocall[:]
		self.reset = True

	def Cleanup(self):
		"""\
		Ask the thread to try and exit.
		"""
		del self.tocall[:]
		self.exit = True

	def Call(self, method, *args, **kw):
		"""\
		Queue a call to method in on thread.
		"""
		self.tocall.append((method, args, kw))

class NotImportantEvent(Exception):
	"""\
	Not Important events are things like download progress events. They occur 
	often and if one is missed there is not huge problem.
	
	The latest NotImportantEvent is always the most up to date and if there are
	pending updates only the latest in a group should be used.
	"""
	pass

from tp.netlib import Connection, failed
from tp.netlib import objects as tpobjects
class NetworkThread(CallThread):
	"""\
	The network thread deals with talking to the server via the network.
	"""

	## These are network events
	class NetworkFailureEvent(Exception):
		"""\
		Raised when the network connection fails for what ever reason.
		"""
		pass

	class NetworkConnectEvent(Exception):
		"""\
		Raised when the network connects to a server.
		"""
		pass

	class NetworkAccountEvent(Exception):
		"""\
		Raised when an account is successful created on a server.
		"""
		pass

	class NetworkAsyncFrameEvent(Exception):
		"""\
		Raised when an async frame (such as TimeRemaining) is received.
		"""
		def __init__(self, frame):
			self.frame = frame

	class NetworkTimeRemainingEvent(NetworkAsyncFrameEvent):
		"""\
		Called when an async TimeRemaining frame is received. 
		"""
		def __init__(self, frame):
			if not isinstance(frame, tpobjects.TimeRemaining):
				raise SyntaxError("NetworkTimeRemainingEvent requires a TimeRemaining frame!? (got %r)", frame)
			NetworkThread.NetworkAsyncFrameEvent.__init__(self, frame)

			self.gotat      = time.time()
			self.remaining  = frame.time	

	######################################

	def __init__(self, application):
		CallThread.__init__(self)

		self.application = application
		self.connection = Connection()

	def every(self):
		"""\
		Check's if there are any async frames pending. If so creates the correct
		events and posts them.
		"""
		try:
			self.connection.pump()

			if self.connection.buffered['frames-received'].has_key(0):
				pending = self.connection.buffered['frames-received'][0]
				while len(pending) > 0:
					if not isinstance(pending[0], tpobjects.TimeRemaining):
						break
					frame = pending.pop(0)
					self.application.Post(self.NetworkTimeRemainingEvent(frame))
		except (AttributeError, KeyError), e:
			print e

	def error(self, error):
		traceback.print_exc()
		if isinstance(error, (IOError, socket.error)):
			s  = _("There was an unknown network error.\n")
			s += _("Any changes since last save have been lost.\n")
			if getattr(self.connection, 'debug', False):
				s += _("A traceback of the error was printed to the console.\n")
				print error
			self.application.Post(self.NetworkFailureEvent(s))
		else:
			raise

	def Post(self, event):
		"""
		Post an Event the current window.
		"""
		func = 'On' + event.__class__.__name__[:-5]
		if hasattr(self, func):
			getattr(self, func)(event)

	def NewAccount(self, username, password, email):
		"""\
		"""
		result, message = self.connection.account(username, password, email)
		if result:
			self.application.Post(self.NetworkAccountEvent(message))
		else:
			self.application.Post(self.NetworkFailureEvent(message))

	def Connect(self, host, debug=False, callback=nop, cs="unknown"):
		"""\
		"""
		try:
			if self.connection.setup(host=host, debug=debug):
				s  = _("The client was unable to connect to the host.\n")
				s += _("This could be because the server is down or there is a problem with the network.\n")
				self.application.Post(self.NetworkFailureEvent(s))
				return False
		except (IOError, socket.error), e:
			s  = _("The client could not connect to the host.\n")
			s += _("This could be because the server is down or you mistyped the server address.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return False
		callback("connecting", "downloaded", "Successfully connected to the host...", amount=1)
			
		try:
			callback("connecting", "progress", "Looking for Thousand Parsec Server...")
			if failed(self.connection.connect(("libtpclient-py/%s.%s.%s " % version)+cs)):
				raise socket.error("")
		except (IOError, socket.error), e:
			s  = _("The client connected to the host but it did not appear to be a Thousand Parsec server.\n")
			s += _("This could be because the server is down or the connection details are incorrect.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return False
		callback("connecting", "downloaded", "Found a Thousand Parsec Server...", amount=1)

		callback("connecting", "progress", "Looking for supported features...")
		features = self.connection.features()
		if failed(features):
			s  = _("The client connected to the host but it did not appear to be a Thousand Parsec server.\n")
			s += _("This could be because the server is down or the connection details are incorrect.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return False
		callback("connecting", "downloaded", "Got the supported features...", amount=1)

		self.application.Post(self.NetworkConnectEvent(features))
		return 

	def ConnectTo(self, host, username, password, debug=False, callback=nop, cs="unknown"):
		"""\
		Connect to a given host using a certain username and password.
		"""
		callback("connecting", "start", "Connecting...")
		callback("connecting", "todownload", todownload=5)
		try:
			if self.Connect(host, debug, callback, cs) is False:
				return False
			
			callback("connecting", "progress", "Trying to Login to the server...")
			if failed(self.connection.login(username, password)):
				s  = _("The client connected to the host but could not login because the username of password was incorrect.\n")
				s += _("This could be because you are connecting to the wrong server or mistyped the username or password.\n")
				self.application.Post(self.NetworkFailureEvent(s))
				return False
			callback("connecting", "downloaded", "Logged in okay!", amount=1)

			# Create a new cache
			self.application.cache = Cache(Cache.key(host, username))
			return True
		finally:
			callback("connecting", "finished", "")

	def CacheUpdate(self, callback):
		try:
			callback("connecting", "alreadydone", "Already connected to the server!")
			self.application.cache.update(self.connection, callback)
			self.application.cache.save()
		except ThreadStop, e:
			pass
		except Exception, e:
			self.application.Post(self.NetworkFailureEvent(e))	
			raise

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


class MediaThread(CallThread):
	"""\
	The media thread deals with downloading media off the internet.
	"""

	## These are network events
	class MediaFailureEvent(Exception):
		"""\
		Raised when the media connection fails for what ever reason.
		"""
		pass

	class MediaDownload:
		def __init__(self, file, progress=0, size=0, localfile=None):
			self.file = file
			self.progress = progress
			self.size = size
			self.localfile = localfile

		def __str__(self):
			return "<%s %s>" % (self.__class__.__name__, self.file)
		__repr__ = __str__

	class MediaDownloadStartEvent(MediaDownload):
		"""\
		Posted when a piece of media is started being downloaded.
		"""
		pass

	class MediaDownloadProgressEvent(MediaDownload, NotImportantEvent):
		"""\
		Posted when a piece of media is being downloaded.
		"""
		pass

	class MediaDownloadDoneEvent(MediaDownload):
		"""\
		Posted when a piece of media has been downloaded.
		"""
		pass

	class MediaDownloadAbortEvent(Exception, MediaDownload):
		"""\
		Posted when a piece of media started downloading but was canceled.
		"""
		def __str__(self):
			return "<%s>" % (self.__class__.__name__)

	class MediaUpdateEvent:
		"""\
		Posted when the media was download.
		"""
		def __init__(self, files):
			self.files = files

	######################################
	def __init__(self, application):
		CallThread.__init__(self)

		self.application = application

		self.todownload = {}
		self.tostop = []
	
	def idle(self):
		if len(self.todownload) <= 0:
			CallThread.idle(self)
			return

		file, timestamp = self.todownload.iteritems().next()
		print "Media.Downloading Starting", file, timestamp
		def callback(blocknum, blocksize, size, self=self, file=file, tostop=self.tostop):
			progress = min(blocknum*blocksize, size)
			if blocknum == 0:
				self.application.Post(self.MediaDownloadStartEvent(file, progress, size))
	
			self.application.Post(self.MediaDownloadProgressEvent(file, progress, size))
	
			if file in tostop:
				tostop.remove(file)
				raise self.MediaDownloadAbortEvent(file)

		try:
			localfile = self.cache.getfile(file, timestamp, callback=callback)
			print "Media Downloading Finished", file
			self.application.Post(self.MediaDownloadDoneEvent(file, localfile=localfile))
		except self.MediaDownloadAbortEvent, e:
			print "Media Downloading Aborting", e
			self.application.Post(e)

		del self.todownload[file]

	def error(self, error):
		if isinstance(error, (IOError, socket.error)):
			s  = _("There was an unknown network error.\n")
			s += _("Any changes since last save have been lost.\n")
			self.application.Post(self.MediaFailureEvent(s))
		raise

	def Cleanup(self):
		print "Cleanup", self, self.todownload
		for file in self.todownload:
			self.tostop.append(file)
		CallThread.Cleanup(self)

	def Post(self, event):
		"""
		Post an Event the current thread.
		"""
		pass

	def StopFile(self, file):
		self.tostop.append(file)

	def GetFile(self, file, timestamp):
		"""\
		Get a File, return directly or start a download.
		"""
		print "GetFile", file, timestamp
		if self.cache.ready(file, timestamp):
			print "File has already been downloaded.", file
			return self.cache.getfile(file, timestamp)
		self.todownload[file] = timestamp

	def ConnectTo(self, host, username, debug=False):
		"""\
		ConnectTo 
		"""
		print "Media ConnectTo", host, username
		self.cache = Media(Cache.key(host, username), "http://darcs.thousandparsec.net/repos/media/client/")
		self.cache.getfile(self.cache.files)
		files = self.cache.getpossible(['png', 'gif'])
		self.application.Post(self.MediaUpdateEvent(files))

from tp.netlib.discover import LocalBrowser as LocalBrowserB
from tp.netlib.discover import RemoteBrowser as RemoteBrowserB
class LocalBrowser(LocalBrowserB, threading.Thread):
	def __init__(self, *args, **kw):
		threading.Thread.__init__(self)
		LocalBrowserB.__init__(self, *args, **kw)

class RemoteBrowser(RemoteBrowserB, threading.Thread):
	def __init__(self, *args, **kw):
		threading.Thread.__init__(self)
		RemoteBrowserB.__init__(self, *args, **kw)
	
class FinderThread(CallThread):
	"""\
	The finder thread deals with finding games.

	It uses both Zeroconf and talks to the metaserver to get the information it
	needs.
	"""

	## These are network events
	class GameEvent(object):
		def __init__(self, game):
			self.game = game

	class LostGameEvent(GameEvent):
		"""\
		Raised when the finder loses a game.
		"""
		pass

	class FoundGameEvent(GameEvent):
		"""\
		Raised when the finder finds a game.
		"""
		pass
	
	class LostLocalGameEvent(FoundGameEvent):
		"""\
		Raised when the finder loses a local game.
		"""
		pass

	class FoundLocalGameEvent(FoundGameEvent):
		"""\
		Raised when the finder finds a local game.
		"""
		pass
	
	class LostRemoteGameEvent(FoundGameEvent):
		"""\
		Raised when the finder loses a remote game.
		"""
		pass

	class FoundRemoteGameEvent(FoundGameEvent):
		"""\
		Raised when the finder finds a remote game.
		"""
		pass

	class FinderErrorEvent(Exception):
		"""\
		Raised when the finder has an error finding games.
		"""
		pass

	class FinderFinishedEvent(Exception):
		"""\
		Raised when the finder has finished searching for new games.
		"""
		pass

	def __init__(self, application):
		CallThread.__init__(self)

		self.application = application

		self.local  = LocalBrowser()
		self.local.GameFound  = self.FoundLocalGame
		self.local.GameGone   = self.LostLocalGame

		self.remote = RemoteBrowser()
		self.remote.GameFound = self.FoundRemoteGame
		self.remote.GameGone  = self.LostRemoteGame

	def FoundLocalGame(self, game):
		print "FoundLocalGame", self, game
		self.application.Post(FinderThread.FoundLocalGameEvent(game))

	def FoundRemoteGame(self, game):
		print "FoundRemoteGame", self, game
		self.application.Post(FinderThread.FoundRemoteGameEvent(game))

	def LostLocalGame(self, game):
		print "LostLocalGame", self, game
		self.application.Post(FinderThread.LostLocalGameEvent(game))

	def LostRemoteGame(self, game):
		print "LostRemoteGame", self, game
		self.application.Post(FinderThread.LostRemoteGameEvent(game))

	def Games(self):
		"""\
		Get all the currently known games.
		"""
		return self.local.games, self.remote.games

	def Cleanup(self):
		print "Cleanup", self
		self.local.exit()
		self.remote.exit()

	def Post(self, event):
		"""
		Post an Event the current thread.
		"""
		pass

	def run(self):
		self.local.start()
		self.remote.start()
