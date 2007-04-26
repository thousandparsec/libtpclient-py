
import os, os.path
import shutil
import stat
import string

import socket
import httplib
import urllib, urlparse
import time

import gzip

from cache import Cache

from strptime import strptime

class Media:
	def __init__(self, key, serverurl, configdir=None, mediatypes=[], new=False, noconnect=False):
		"""\
		It is important that key constructed the following way,
			protocol://username@server:port/
		Everything must be there, even if the port is the default.

		serverurl is the URL of the server to download the media from

		configdir is where the cache will be stored.
		mediatypes is the type of media which the client needs.
		"""
		if configdir == None:
			configdir = Cache.configdir()

		if not os.path.exists(configdir):
			os.mkdir(configdir)

		key = Cache.configkey(key)

		self.dir = os.path.join(configdir, "media.%s" % (key,))

		if os.path.exists(self.dir) and new:
			shutil.rmtree(self.dir)
		if not os.path.exists(self.dir):
			os.mkdir(self.dir)

		self.noconnect = noconnect

		self.serverurl = serverurl
		self.connection

		self.gotten = []

	def connection(self):
		if not hasattr(self, '_connection'):
			type, host, self.basepath, t, t, t = urlparse.urlparse(self.serverurl)
			self._connection = getattr(httplib, "%sConnection" % type.upper())(host)
		return self._connection
	connection = property(connection)

	def getter(self):
		if not hasattr(self, '_getter'):
			self._getter = urllib.FancyURLopener()
		return self._getter
	getter = property(getter)

	def getresponse(self, media_remote):
		"""
		"""
		try:
			print "Trying to get data on ", media_remote
			while True:
				self.connection.request("HEAD", media_remote)
				response = self.connection.getresponse()
				self.connection.close()
				if response.status == 301 or response.status == 302:
					media_remote = response.getheader('location')
					print 'Redirected to', media_remote
					self.connection.connect()
				else:
					return response
		except socket.error, e:
			print e
			return None

	def updated(self, media_remote, media_local):
		"""\
		Checks the file's timestamp against the remote's version.
		"""
		try:
			response = self.getresponse(media_remote)
			if response == None:
				return False
			if response.status == 404:
				print 'File not found on server (404)'
				return False
			
			headers = {}
			headers['last-modified'] = response.getheader('last-modified')
			remotedate = strptime(headers['last-modified'], "%a, %d %b %Y %H:%M:%S %Z")[0:5]
			localdate = eval(open(media_local + ".timestamp").read())

			print "Remote Date", remotedate
			print "Local Date ", localdate

			if remotedate <= localdate:
				return False
			return True
		except IOError, e:
			return True
		except socket.error, e:
			print e
			return False

	def ready(self, file, timestamp):
		"""\
		Is a file ready to be used?
		"""
		media_local = os.path.join(self.dir, file)
		media_local_stamp = media_local + ".timestamp"
		if os.path.exists(media_local) and os.path.exists(media_local_stamp):
			if timestamp <= eval(open(media_local_stamp).read()):
				return media_local

	def getfile(self, file, timestamp=None, callback=None):
		"""\
		Get a file, if it exists in the cache it is checked for freshness.
		"""
		if callback is None:
			def callback(*args):
				print args

		media_local = os.path.join(self.dir, file)
		media_remote = urlparse.urljoin(self.basepath, file)
		media_url = urlparse.urljoin(self.serverurl, file)

		print "Local  file", media_local, os.path.exists(media_local)
		print "Remote file", media_remote
		print "URL of file", media_url
		if os.path.exists(media_local):
			if timestamp is None:
				if not self.updated(media_remote, media_local):
					return media_local
			else:
				if not self.ready(file, timestamp) is None:
					return media_local

		if self.noconnect:
			raise IOError("Could not get the file as in no connection mode!")	

		response = self.getresponse(media_remote)
		if response == None or response.status == 404:
			print "No media on remote server"
			return media_local
	
		ldir = os.path.dirname(media_local)
		if not os.path.exists(ldir):
			os.makedirs(ldir)

		try:
			(trash, message) = self.getter.retrieve(media_url, media_local, callback)

			remotedate = strptime(message.getheader('last-modified'), "%a, %d %b %Y %H:%M:%S %Z")[0:5]

			open(media_local + ".timestamp", 'w').write(repr(remotedate))
			return media_local
		except IOError, e:
			print e
			return False

	files = "media.gz"
	def getpossible(self, valid_types, callback=None):
		"""
		Gets the Media description file from the http server.
		"""
		media_local = os.path.join(self.dir, self.files)
		if os.path.exists(media_local):
			for line in gzip.GzipFile(media_local, 'r').readlines():
				line, timestamp = line.strip().split(' ')
				timestamp = strptime(timestamp, "%Y%m%dT%H%M")[0:5]
				for type in valid_types:
					if line.endswith(type):
						yield line, timestamp
		raise IOError("media.gz is not avaliable at this time")

if __name__ == "__main__":
	"""
	media.py <url>
	"""

	import sys
	media_cache = Media("testing", sys.argv[1])
	media_cache.getfile(media_cache.files)

	files = {}
	for file, timestamp in media_cache.getpossible(['png', 'gif', 'jpg']):
		def splitall(start):
			bits = []

			while True:
				start, end = os.path.split(start)
				if end is '':
					break
				bits.append(end)
			bits.reverse()
			return bits

		bits = splitall(file)
		if bits[-2] in ['animation', 'still']:
			type = bits[-2]
			del bits[-2]
		else:
			type = 'still'

		if not bits[-2].endswith("-small"):
			continue
		else:
			key = bits[-2][:-6]
			if not files.has_key(key):
				files[key] = {}
			if not files[key].has_key(type):
				files[key][type] = []
			files[key][type].append((file, timestamp))

	import pprint
	pprint.pprint(files)

