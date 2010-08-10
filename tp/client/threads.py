
import pprint
import socket
import sys
import time
import traceback
from threading import Lock

import objectutils

from media import Media

from config import load_data, save_data
from version import version
		
from tp.netlib.objects import parameters
from tp.netlib import objects

def nop(*args, **kw):
	return

class Event(Exception):
	"""
	Base class for all events which get posted.
	"""
	def type(self):
		return self.__class__.__name__[:-5]
	type = property(type)

	def __init__(self, *args, **kw):
		self.message = ""
		Exception.__init__(self, *args, **kw)

		if self.__class__.__name__[-5:] != "Event":
			raise SystemError("All event class names must end with Event!")	

		self.time = time.time()

	def __str__(self):
		return self.__unicode__().encode('ascii', 'replace')

	def __unicode__(self):
		return unicode(self.message)

from cache import Cache
from ChangeList import ChangeNode

class Application(object):
	"""
	Container for all the applications threads and the network cache.

	Calling accross threads requires you to use the .Call method on each thread - DO NOT call directly!
	The cache can be accessed by either thread at any time - be careful.
	"""
	MediaClass  = None
	FinderClass = None
	CacheClass  = None

	def __init__(self):
		if self.CacheClass is None:
			from cache import Cache
			self.CacheClass = Cache

		try:
			import signal

			# Make sure these signals go to me, rather then a child thread..
			signal.signal(signal.SIGINT,  self.Exit)
			signal.signal(signal.SIGTERM, self.Exit)
		except ImportError:
			pass

		print self.GUIClass, self.NetworkClass, self.MediaClass, self.FinderClass
		self.gui = self.GUIClass(self)
		if not self.MediaClass is None:
			self.media = self.MediaClass(self)
		else:
			self.media = None
		if not self.FinderClass is None:
			self.finder = self.FinderClass(self)
		else:
			self.finder = None

		self.cache = None

		if hasattr(self.GUIClass, "Create"):
			self.gui.Create()
		
		# Load the Configuration
		self.ConfigLoad()

	def Run(self):
		"""\
		Set the application running.
		"""
		self.StartNetwork()

		if not self.media is None:
			self.media.start()

		if not self.finder is None:
			self.finder.start()

		self.gui.start()

	def StartNetwork(self):
		self.network = self.NetworkClass(self)
		self.network.start()

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

	def Post(self, event, source=None):
		"""\
		Post an application wide event to every thread.
		"""
		event.source = source

		self.network.Post(event)
		self.finder.Post(event)
		self.media.Post(event)

		self.gui.Call(self.gui.Post, event)

	def Exit(self, *args, **kw):
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


import threading
from threadcheck import thread_checker, thread_safe

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
	__metaclass__ = thread_checker

	def __init__(self):
		threading.Thread.__init__(self, name=self.name)
		self.setDaemon(True)
		self.exit = False
		self.reset = False
		self.tocall = []

	@thread_safe
	def run(self):
		self._thread = threading.currentThread()

		try:
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

		except Exception, e:
			self.error(e)

		self.Cleanup()

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

	@thread_safe
	def Reset(self):
		#del self.tocall[:]
		self.reset = True

	@thread_safe
	def Cleanup(self):
		"""\
		Ask the thread to try and exit.
		"""
		del self.tocall[:]
		self.exit = True

	@thread_safe
	def Call(self, method, *args, **kw):
		"""\
		Queue a call to method in on thread.
		"""
		self.tocall.append((method, args, kw))

	@thread_safe
	def Post(self, event):
		func = 'On' + event.type
		if hasattr(self, func):
			self.Call(getattr(self, func), event)

class NotImportantEvent(Event):
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
	name = "Network"

	## These are network events
	class NetworkFailureEvent(Event):
		"""\
		Raised when the network connection fails for what ever reason.
		"""
		pass

	class NetworkFailureUserEvent(NetworkFailureEvent):
		"""\
		Raised when there was a network failure because the user does not exist.
		"""
		pass

	class NetworkFailurePasswordEvent(NetworkFailureEvent):
		"""\
		Raised when there was a network failure because the password was incorrect.
		"""
		pass

	class NetworkConnectEvent(Event):
		"""\
		Raised when the network connects to a server.
		"""
		def __init__(self, msg, features, games):
			Event.__init__(self, msg)
			self.features = features
			self.games    = games

	class NetworkAccountEvent(Event):
		"""\
		Raised when an account is successful created on a server.
		"""
		pass

	class NetworkAsyncFrameEvent(Event):
		"""\
		Raised when an async frame (such as TimeRemaining) is received.
		"""
		def __init__(self, frame):
			Event.__init__(self)

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

			pending = self.connection.buffered['frames-async']
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
			s  = _(u"There was an unknown network error.\n")
			s += _("Any changes since last save have been lost.\n")
			if getattr(self.connection, 'debug', False):
				s += _("A traceback of the error was printed to the console.\n")
				print error
			print repr(s)
			self.application.Post(self.NetworkFailureEvent(s))
		else:
			raise

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
		callback("connecting", "downloaded", _("Successfully connected to the host..."), amount=1)
			
		try:
			callback("connecting", "progress", _("Looking for Thousand Parsec Server..."))
			if failed(self.connection.connect(("libtpclient-py/%s.%s.%s " % version[:3])+cs)):
				raise socket.error("")
		except (IOError, socket.error), e:
			s  = _("The client connected to the host but it did not appear to be a Thousand Parsec server.\n")
			s += _("This could be because the server is down or the connection details are incorrect.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return False
		callback("connecting", "downloaded", _("Found a Thousand Parsec Server..."), amount=1)

		callback("connecting", "progress", _("Looking for supported features..."))
		features = self.connection.features()
		if failed(features):
			s  = _("The client connected to the host but it did not appear to be a Thousand Parsec server.\n")
			s += _("This could be because the server is down or the connection details are incorrect.\n")
			self.application.Post(self.NetworkFailureEvent(s))
			return False
		callback("connecting", "downloaded", _("Got the supported features..."), amount=1)

		callback("connecting", "progress", _("Looking for running games..."))
		self.games = self.connection.games()
		if failed(self.games):
			self.games = []
		else:
			for game in self.games:
				callback("connecting", "progress", _("Found %(game)s playing %(ruleset)s (%(version)s)") % {'game': game.name, 'ruleset': game.rule, 'version': game.rulever})

		callback("connecting", "downloaded", _("Got the supported features..."), amount=1)

		self.application.Post(self.NetworkConnectEvent("Connected to %s" % host, features, self.games))
		return 

	def ConnectTo(self, host, username, password, debug=False, callback=nop, cs="unknown"):
		"""\
		Connect to a given host using a certain username and password.
		"""
		callback("connecting", "start", _("Connecting..."))
		callback("connecting", "todownload", todownload=5)
		try:
			if self.Connect(host, debug, callback, cs) is False:
				return False
			
			callback("connecting", "progress", _("Trying to Login to the server..."))
			if failed(self.connection.login(username, password)):
				s  = _("The client connected to the host but could not login because the username of password was incorrect.\n")
				s += _("This could be because you are connecting to the wrong server or mistyped the username or password.\n")
				self.application.Post(self.NetworkFailureUserEvent(s))
				return False
			callback("connecting", "downloaded", _("Logged in okay!"), amount=1)

			# Create a new cache
			# FIXME: This should choose the actual game we are connecting too.
			self.application.cache = self.application.CacheClass(self.application.CacheClass.key(host, self.games[0], username))
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

	def RequestEOT(self, callback=None):
		if callback is None:
			def callback(self, *args, **kw):
				pass

		try:
			if not hasattr(self.connection, "turnfinished"):
				print "Was unable to request turnfinished."
				return

			if failed(self.connection.turnfinished()):
				print "The request for end of turn failed."
				return
		except Exception, e:
			print e

	def OnCacheDirty(self, evt):
		"""\
		When the cache gets dirty we have to push the changes to the server.
		"""
		try:
			from cache import apply
			self.application.Post(apply(self.connection, evt, self.application.cache))
		except Exception, e:
			type, val, tb = sys.exc_info()
			sys.stderr.write("".join(traceback.format_exception(type, val, tb)))
			self.application.Post(self.NetworkFailureEvent(e))
			"There where the following errors when trying to send changes to the server:"
			"The following updates could not be made:"

class ThreadedMedia(Media):
	__metaclass__ = thread_checker

	def __init__(self, url, username, password, configdir=None):
		self.medialock = threading.Lock()
		self.gettingfiles = set()
		self.gettingfileslock = threading.Lock()
		self.locationlock = threading.Lock()
		
		Media.__init__(self, url, username, password, configdir)
		
	@thread_safe
	def media(self):
		"""\
		Returns the current media.gz file.
		"""
		self.medialock.acquire()
		try:
			return Media.media(self)
		finally:
			self.medialock.release()
			
	@thread_safe
	def get(self, file, callback=None):
		"""\
		Gets a file from the remote server.
		"""
		self.gettingfileslock.acquire()
		try:
			if file in self.gettingfiles:
				return None
			
			self.gettingfiles.add(file)
		finally:
			self.gettingfileslock.release()
		
		thisfile = Media.get(self, file, callback)
		
		self.gettingfileslock.acquire()
		try:
			self.gettingfiles.remove(file)
		finally:
			self.gettingfileslock.release()
		
		return thisfile
	
	@thread_safe
	def recreatefile(self, local_location):
		"""\
		Creates a file at a given location, removing the old one if necessary.
		"""
		self.locationlock.acquire()
		try:
			Media.recreatefile(self, local_location)
		finally:
			self.locationlock.release()
		

class DownloaderThread(threading.Thread):
	"""\
	This thread downloads a file and then exits.
	"""
	
	# FIXME: Creating and destroying threads is expensive. This should use a thread pool.
	
	name = "Downloader"
	
	__metaclass__ = thread_checker
	
	def __init__(self, file, callback, finishedcallback, parent, cache, application):
		threading.Thread.__init__(self)
		self.setDaemon(True)
		self.file = file
		self.finishedcallback = finishedcallback
		self.callback = callback
		self.parent = parent
		self.cache = cache
		self.application = application
	
	@thread_safe
	def run(self):
		try:
			localfile = self.cache.get(self.file, callback=self.callback)
			self.application.Post(self.parent.MediaDownloadDoneEvent(self.file, localfile=localfile))
			self.finishedcallback(self.file)
		except self.parent.MediaDownloadAbortEvent, e:
			self.finishedcallback(self.file)
			self.application.Post(e)
		
		self.exit = True

class MediaThread(CallThread):
	"""\
	The media thread deals with downloading media off the internet.
	"""
	name = "Media"

	## These are network events
	class MediaFailureEvent(Event):
		"""\
		Raised when the media connection fails for what ever reason.
		"""
		pass

	class MediaDownloadEvent(Event):
		"""
		Base class for media download events.
		"""
		def __init__(self, file, progress=0, size=0, localfile=None, amount=0):
			Event.__init__(self)

			self.file      = file
			self.amount    = amount
			self.progress  = progress
			self.size      = size
			self.localfile = localfile

		def __str__(self):
			return "<%s %s>" % (self.__class__.__name__, self.file)
		__repr__ = __str__

	class MediaDownloadStartEvent(MediaDownloadEvent):
		"""\
		Posted when a piece of media is started being downloaded.
		"""
		pass

	class MediaDownloadProgressEvent(MediaDownloadEvent, NotImportantEvent):
		"""\
		Posted when a piece of media is being downloaded.
		"""
		pass

	class MediaDownloadDoneEvent(MediaDownloadEvent):
		"""\
		Posted when a piece of media has been downloaded.
		"""
		pass

	class MediaDownloadAbortEvent(MediaDownloadEvent):
		"""\
		Posted when a piece of media started downloading but was canceled.
		"""
		def __str__(self):
			return "<%s>" % (self.__class__.__name__)

	class MediaUpdateEvent(Event):
		"""\
		Posted when the media was download.
		"""
		def __init__(self, files):
			Event.__init__(self)

			self.files = files

	######################################
	def __init__(self, application):
		CallThread.__init__(self)

		self.application = application
		
		self.files = []
		self.fileslock = Lock()
		
		self.filesinprogress = set()
		self.filesinprogresslock = Lock()
		
		self.todownload = {}
		self.tostop = set()
		
	
	def idle(self):
		if len(self.todownload) <= 0:
			# When we are really idle, call our base class's idle method.
			CallThread.idle(self)
			return

		file, timestamp = self.todownload.iteritems().next()
		def callback(blocknum, blocksize, size, self=self, file=file, tostop=self.tostop):
			progress = min(blocknum*blocksize, size)
			if blocknum == 0:
				self.application.Post(self.MediaDownloadStartEvent(file, progress, size))

			self.application.Post(self.MediaDownloadProgressEvent(file, progress, size, amount=blocksize))

			if file in tostop:
				self.filedone(file)
				tostop.remove(file)
				raise self.MediaDownloadAbortEvent(file)
		
		@thread_safe
		def finishedcallback(filename):
			self.filedone(filename)
		
		try:
			newthread = DownloaderThread(file, callback, finishedcallback, self, self.cache, self.application)
			newthread.start()
			self.filesinprogresslock.acquire()	
			try:
				self.filesinprogress.add(file)
			finally:
				self.filesinprogresslock.release()
			del self.todownload[file]
		
		except self.MediaDownloadAbortEvent, e:
			self.application.Post(e)

	@thread_safe
	def filedone(self, filename):
		"""\
		Called when a file finishes downloading, to remove it from the list of files in progress.
		"""
		self.filesinprogresslock.acquire()	
		try:
			self.filesinprogress.remove(filename)
		finally:
			self.filesinprogresslock.release()

	def error(self, error):
		if isinstance(error, (IOError, socket.error)):
			s  = _("There was an unknown network error.\n")
			s += _("Any changes since last save have been lost.\n")
			self.application.Post(self.MediaFailureEvent(s))
		raise

	@thread_safe
	def Cleanup(self):
		for file in self.todownload:
			self.tostop.add(file)
		CallThread.Cleanup(self)

	@thread_safe
	def Post(self, event):
		"""
		Post an Event the current thread.
		"""
		pass

	@thread_safe
	def StopFile(self, file):
		self.tostop.add(file)

	@thread_safe
	def GetFile(self, file):
		"""\
		Get a File, return directly or start a download. Returns None if download is started.
		"""
		location = self.cache.newest(file)
		if location:
			return location
			
		self.filesinprogresslock.acquire()	
		try:
			if not file in self.filesinprogress:
				self.todownload[file] = None
		finally:
			self.filesinprogresslock.release()

	def ConnectTo(self, host, username, password, debug=False):
		"""\
		ConnectTo 
		"""
		
		self.cache = ThreadedMedia(host, username, password)

		self.cache.update_media()

		# FIXME: Hack to prevent cross thread calling - should fix the media object
		files = []
		for file in self.cache.getpossible(['png', 'gif']):
			files.append(file)
		
		self.fileslock.acquire()	
		try:
			self.files = files
		finally:
			self.fileslock.release()
			
		self.application.Post(self.MediaUpdateEvent(files))
	
	@thread_safe
	def GetFilenames(self, fileprefix, filesuffixlist=None):
		"""\
		Get the list of possible files with extensions for a given file prefix.
		"""
		if filesuffixlist is None:
			filesuffixlist = []
		filelist = []
		self.fileslock.acquire()	
		try:
			if len(self.files) <= 0:
				return []
			for file in self.files:
				if not fileprefix in file:
					continue
					
				if len(filesuffixlist) <= 0:
					filelist.append(file)
				else:
					for suffix in suffixlist:
						if not file.endswith(suffix):
							continue
						filelist.append(file)
						break
		finally:
			self.fileslock.release()
			
		return filelist
	
	@thread_safe
	def getImages(self, oid, filesuffixlist=None):
		"""\
		Returns full image URLs for this object as a list of tuples, each containing (name, [filename1, etc.])
		"""
		if filesuffixlist is None:
			filesuffixlist = []
		urls = []
		mediaurls = objectutils.getMediaURLs(self.application.cache, oid)
		for (name, url) in mediaurls.items():
			filenames = self.GetFilenames(url, filesuffixlist)
			urls.append((name, filenames))
		
		images = []
		for name, filenames in urls:
			thisnameimages = []
			for imageurl in filenames:
				file = self.GetFile(imageurl)
		
				if file == None:
					continue
				
				thisnameimages.append(file)
			
			if len(thisnameimages) <= 0:
				continue
			
			images.append((name, thisnameimages))
		
		return images

	@thread_safe
	def getImagesForURL(self, url, filesuffixlist=None):
		"""\
		Returns full image URLs for a given base URL.
		"""
		if filesuffixlist is None:
			filesuffixlist = []
		images = []
		filenames = self.GetFilenames(url, filesuffixlist)
		for filename in filenames:
			file = self.GetFile(filename)
		
			if file == None:
				continue
			
			images.append(file)
		return images
	
	@thread_safe
	def getDownloading(self):
		"""\
		Get the list of currrently downloading files.
		"""
		self.filesinprogresslock.acquire()	
		try:
			return self.filesinprogress
		finally:
			self.filesinprogresslock.release()
			
	@thread_safe
	def getDownloadingForObject(self, oid):
		"""\
		Get the list of files currently downloading for a given object.
		"""
		fileurls = []
		self.filesinprogresslock.acquire()	
		try:
			mediaurls = objectutils.getMediaURLs(self.application.cache, oid)
			for (name, url) in mediaurls.items():
				filenames = self.GetFilenames(url)
				for filename in filenames:
					if filename not in self.filesinprogress:
						continue
						
					fileurls.append(filename)
			
			return fileurls
		finally:
			self.filesinprogresslock.release()

class FileTrackerMixin:
	def __init__(self, application):
		self.application = application
		self.filesinprogress = set()
		self.application.gui.Binder(self.application.MediaClass.MediaUpdateEvent, self.OnMediaUpdate)
		self.application.gui.Binder(self.application.MediaClass.MediaDownloadDoneEvent,	self.OnMediaDownloadDone)
		self.application.gui.Binder(self.application.MediaClass.MediaDownloadAbortEvent, self.OnMediaDownloadAborted)
		
	def AddURL(self, url):
		self.filesinprogress.add(url)
	
	def AddURLsFromBase(self, url):
		for filename in self.application.media.GetFilenames(url):
			self.filesinprogress.add(filename)
	
	def AddObjectURLs(self, objectid):
		for filename in self.application.media.getDownloadingForObject(objectid):
			self.filesinprogress.add(filename)
	
	def RemoveURL(self, url):
		if url in self.filesinprogress:
			self.filesinprogress.remove(url)
			
	def ClearURLs(self):
		self.filesinprogress = set()
	
	def CheckURL(self, url):
		return url in self.filesinprogress
		
	def OnMediaUpdate(self, evt):
		pass
	
	def OnMediaDownloadDone(self, evt):
		if evt is None:
			return

		if self.CheckURL(evt.file):
			self.RemoveURL(evt.file)
	
	def OnMediaDownloadAborted(self, evt):
		if evt is None:
			self.ClearURLs()

		if self.CheckURL(evt.file):
			self.RemoveURL(evt.file)

from tp.netlib.discover import LocalBrowser as LocalBrowserB
from tp.netlib.discover import RemoteBrowser as RemoteBrowserB
class LocalBrowser(LocalBrowserB, threading.Thread):
	name="LocalBrowser"

	def __init__(self, *args, **kw):
		threading.Thread.__init__(self, name=self.name)
		self.setDaemon(True)
		LocalBrowserB.__init__(self, *args, **kw)

class RemoteBrowser(RemoteBrowserB, threading.Thread):
	name="RemoteBrowser"

	def __init__(self, *args, **kw):
		threading.Thread.__init__(self, name=self.name)
		self.setDaemon(True)
		RemoteBrowserB.__init__(self, *args, **kw)
	
class FinderThread(CallThread):
	"""\
	The finder thread deals with finding games.

	It uses both Zeroconf and talks to the metaserver to get the information it
	needs.
	"""
	name="Finder"

	## These are network events
	class GameEvent(Event):
		"""
		Base class for all game found/lost events.
		"""
		def __init__(self, game):
			Event.__init__(self)

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

	class FinderErrorEvent(Event):
		"""\
		Raised when the finder has an error finding games.
		"""
		pass

	class FinderFinishedEvent(Event):
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

	@thread_safe
	def FoundLocalGame(self, game):
		self.application.Post(FinderThread.FoundLocalGameEvent(game))

	@thread_safe
	def FoundRemoteGame(self, game):
		self.application.Post(FinderThread.FoundRemoteGameEvent(game))

	@thread_safe
	def LostLocalGame(self, game):
		self.application.Post(FinderThread.LostLocalGameEvent(game))

	@thread_safe
	def LostRemoteGame(self, game):
		self.application.Post(FinderThread.LostRemoteGameEvent(game))

	@thread_safe
	def Games(self):
		"""\
		Get all the currently known games.
		"""
		return self.local.games, self.remote.games

	@thread_safe
	def Cleanup(self):
		self.local.exit()
		self.remote.exit()

	@thread_safe
	def Post(self, event):
		"""
		Post an Event the current thread.
		"""
		pass

	@thread_safe	
	def run(self):
		self._thread = threading.currentThread()

		self.local.start()
		self.remote.start()
