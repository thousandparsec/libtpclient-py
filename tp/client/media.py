
import os, os.path
import shutil
import stat
import string

import socket
import httplib
import urllib, urlparse
import time

import gzip

#from cache import Cache

from strptime import strptime

"""
Format for media repositories are the following,

media-new.gz
directory1/mediafile.png
directory1/mediafile.mesh

All media which is the same but in a different format must have the same 
basename. See the above example where the file "mediafile" is avaliable in 
both png and mesh format.

The MEDIA is a compressed text file which describes all the media 
avaliable on the server and some metadata about it.
It has the following format
<media file> <last modtime YYYYMMddThhmm> <filesize bytes> <checksumtype>-<checksum>
directory1/mediafile.png 	20060614T0923 1789345 md5-318424ccbd97c644d6baa594284fefe3
directory1/mediafile.mesh 	20060614T0923 7623748 md5-1505b14a78c9e5858edd0f044c4e0062

URLs of media locations are escaped locally using the following system
re.sub('[^a-zA-Z0-9_]', '-', url)
This means that the url "http://media.thousandparsec.net:80/client"
would be escape as      "http---media.thousandparsec.net-80-client"
The URL should always be in full format including the port.

When media is downloaded locally (or distributed via packages) a meta file
is created for each file. This file allows the client to check if the
graphic is up to date. The meta file contains,
<last modtime YYYYMMddThhmm> <filesize bytes> <checksumtype>-<checksum>
20060614T0923 1789345 md5-318424ccbd97c644d6baa594284fefe3

Media can also be distributed via packages. This should be installed in
a shared location such as /usr/share/games/tp, the MEDIA should be 
distributed with the data where the data is split may have to be merged
together (say if the 3d and 2d data from a URL is distributed seperately).

/usr/share/games/tp/http---media.thousandparsec.net-80-client/MEDIA
/usr/share/games/tp/http---media.thousandparsec.net-80-client/mediafile.png
/usr/share/games/tp/http---media.thousandparsec.net-80-client/directory1/mediafile.png.meta
/usr/share/games/tp/ftp---someotherplace.net-21-pub/media-new.gz
...

When a new media is avaliable it will be downloaded to the local 
users home directory.

~/.tp/media/http---media.thousandparsec.net-80-client/media-new.gz
~/.tp/media/http---media.thousandparsec.net-80-client/directory1/mediafile.png
~/.tp/media/http---media.thousandparsec.net-80-client/directory1/mediafile.png.meta
~/.tp/media/ftp---someotherplace.net-21-pub/media-new.gz

If a media file is found in the distribution search locations that is the 
same or newer then the users version. The users version should be removed.
"""

# FIXME: This should be different for different types of file systems.
# FIXME: This should 
searchdirs = [
	os.path.join("usr", "share", "tp"),
	os.path.join("usr", "share", "games", "tp"),
	os.path.join("usr", "local", "share", "tp"),
	os.path.join("usr", "local", "share", "games", "tp"),
	os.path.join("Program Files", "Thousand Parsec", "Media"),
	os.path.join("media"),
	# FIXME: This should only be searched in the development version
	os.path.join("..", "media"),
	"/home/tim/oss/tp/media",
]

import re
def filesafe(url):
	""" Make a URL safe for the filesystem """
	return re.sub('[^a-zA-Z0-9_]', '-', url)

def totime(s):
	return "%02.0f%02.0f%02.0fT%02.0f%02.0f" % strptime(s, "%a, %d %b %Y %H:%M:%S %Z")[0:5]

MEDIA="media-new.gz"

class URLOpener(urllib.FancyURLopener):
	def http_error_default(self, file, socket, code, reason, message):
		raise IOError(code, reason)

class CallbackLimiter(object):
	def __init__(self, realcallback):
		self.realcallback = realcallback
		self.last = 0


	def __call__(self, i, chunksize, maxsize):
		if self.realcallback is None:
			return

		downloaded = chunksize*i
		if not (i == 0 or downloaded == maxsize):
			# Skip if we have had a call back in the last 2 seconds
			if self.last + 2 > time.time():
				return

		self.realcallback(i, chunksize, maxsize)
		self.last  = time.time()

class Media(object):

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

	def hash(self, s):
		"""\
		Get the function needed to do a hash
		"""
		alog, hash = s.split(':')
		if alog == 'md5':
			import md5
			checksum = (md5.new, hash)
		elif alog == 'sha1':
			import sha
			checksum = (sha.new, hash)
		else:
			raise IOError("Unknown hash algorithm.")
		return checksum

	def metainfo(self, file):
		"""\
		Return the info in the metafile.
		"""
		if not os.path.isfile(file+'.meta'):
			return (0, 0, None)
		modtime, size, checksum = open(file+'.meta', 'r').read().strip().split(' ')
		return modtime, long(size), checksum

	def locate(self, file):
		"""\
		Locates a file with a given filename on the filesystem.
		"""
		# Search through the local filesystem and see if we can find the file
		foundhere = []
		if file == None:
			return None
		for location in self.locations:
			possible = os.path.join(location, file)
			if os.path.exists(possible):
				foundhere.append(possible)
		return foundhere

	def newest(self, file):
		"""\
		Returns the newest version of a file.
		"""
		location = None
		curtime = 0
		possiblefiles = self.locate(file);
		if possiblefiles == None:
			return None
		
		for possible in possiblefiles:
			try:
				modtime, size, checksum = self.metainfo(possible)
				if modtime > curtime:
					location = possible
					curtime  = modtime
			except (IOError, OSError), e:
				print e
		return location

	def remotetime(self, file):
		"""\
		Gets the remote time of a file.

		Needed to find out if we need to update media-new.gz
		"""
		self.connection.request("HEAD", self.url + file)

		headers = {}
		headers['last-modified'] = self.connection.getresponse().getheader('last-modified')
		return totime(headers['last-modified'])

	def media(self):
		"""\
		"""
		# Use the cached version if it's avaliable
		if hasattr(self, '_media'):
			return self._media
	
	def update_media(self):
		file = self.newest(MEDIA)
	
		if file is None:
			# Need to get a version
			file = self.get(MEDIA)
		elif self.connection is not None:
			modtime, size, checksum = self.metainfo(file)
			# Check if there is a remote version which is new...
			remotetime = self.remotetime(MEDIA)
			if remotetime > modtime:
				# Need to get a new version
				file = self.get(MEDIA)
		
		media = {}
		for line in gzip.open(file).readlines():
			file, timestamp, size, checksum = line.strip().split()

			media[file] = (timestamp, int(size), checksum)

		# Cache the data so we don't need to reload all the time
		self._media = media

		return media

	def local(self, media, newtime):
		"""\
		Finds a file which is local which has a modtime greater then the give time.
		"""
		foundhere = self.locate(media)

		while len(foundhere) > 0:
			possible = foundhere.pop(0)

			try:
				modtime, size, checksum = self.metainfo(possible)
				if modtime < newtime:
					continue
			except IOError:
				pass

			return possible
		return False

	def give(self, media):
		"""\
		Gets a file to be used. Will use a local version or will download one.
		"""
		mediagz = self.media()
		if not mediagz.has_key(media):
			raise IOError("No such media file exists!")

		modtime = mediagz[media][0]
		# See if we have a local version we can use
		location = self.local(media, modtime)
		if not location is False:
			return location	
		
		# Looks like we will have to download a peice of media
		return self.get(media)
	
	def recreatefile(self, local_location):
		"""\
		Creates a file at a given location, removing the old one if necessary.
		"""
		# If the file already exists we better remove it
		if os.path.exists(local_location):
			os.unlink(local_location)

		dir = os.path.dirname(local_location)
		if not os.path.exists(dir):
			os.makedirs(dir)
	
	def get(self, file, callback=None):
		"""\
		Gets a file from the remote server.
		"""
		# Where the file will be downloaded too
		local_location  = os.path.join(self.locations[-1], file)
		# Where the file is on the remote server
		remote_location = urlparse.urljoin(self.url, file)

		self.recreatefile(local_location)
		
		# Download the file
		(trash, message) = self.getter.retrieve(remote_location, local_location, CallbackLimiter(callback))

		if file != MEDIA:
			mediagz = self.media()

			# Create the metafile from the mediagz info
			open(local_location+".meta", 'w').write("%s %s %s" % mediagz[file])
			
			modtime, size, testsum = self.metainfo(local_location)
			
			if size != 0 and os.path.getsize(local_location) != size:
				raise IOError("File size of downloaded file " + file + " does not match the expected filesize.");
			
			# Check the checksum
			import hashlib
			
			if not "None" in testsum and testsum is not None:
				checksumtype, testchecksum = self.hash(testsum)
			
				newfile = open(local_location).read()
			
				localchecksum = checksumtype(newfile)
			
				if testchecksum != localchecksum:
					raise IOError("Checksum of downloaded file " + file + " does not match!")
		else:
			# Have to generate our own data
			open(local_location + ".meta", 'w').write("%s %s %s" % (totime(message.getheader('last-modified')), 0, 'None'))
		return local_location

	def __init__(self, url, username, password, configdir=None):
		"""\
		Everything must be there, even if the port is the default.

		serverurl is the URL of the server to download the media from

		configdir is where the cache will be stored.
		mediatypes is the type of media which the client needs.
		"""
		scheme, netloc, path, query, fragment = urlparse.urlsplit(url)

		username = urllib.quote(username.encode('utf-8'))
		password = urllib.quote(password.encode('utf-8'))

		self.url = scheme + "://" + username + ":" + password + "@" + netloc + path
		# Make the URL safe for filesystems
		safeurl = filesafe(url)

		# FIXME: Check the serverurl is valid, IE It's in the full form.
		if configdir == None:
			configdir = self.configdir()
		userdir = os.path.join(configdir, "media", safeurl)

#		# Make sure the user dir exists
#		if os.path.exists(userdir) and new:
#			shutil.rmtree(userdir)
		if not os.path.exists(userdir):
			os.makedirs(userdir)

		# Find all the locations which have media relavent to this URL.
		self.locations = []
		global searchdirs
		for location in searchdirs:
			full = os.path.join(location, safeurl)
			if os.path.exists(full):
				self.locations.append(full)

		# Append the users "localdir"
		self.locations.append(userdir)
	
	@property
	def connection(self):
		if not hasattr(self, '_connection'):
			type, host, self.basepath, t, t, t = urlparse.urlparse(self.url)
			# If we're logging in, remove the username and password so httplib doesn't
			# think that the colon signifies a port number.
			if "@" in host:
				login, host = host.split("@")
			self._connection = getattr(httplib, "%sConnection" % type.upper())(host)
		return self._connection

	@property
	def getter(self):
		if not hasattr(self, '_getter'):
			self._getter = URLOpener()
		return self._getter

	def getpossible(self, media_types):
		"""
		Gets the Media description file from the http server.
		"""
		for file in self.media():
			for possible in media_types:
				if file.endswith(possible):
					yield file

if __name__ == "__main__":
	import sys
	media_cache = Media(sys.argv[1])

	files = {}
	for file in media_cache.getpossible(['png', 'gif', 'jpg']):
		print file
		media_cache.give(file)
