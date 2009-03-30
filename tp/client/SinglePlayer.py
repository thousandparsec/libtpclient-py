"""\
Single player system support module.

@author: Aaron Mavrinac (ezod)
@organization: Thousand Parsec
@license: GPL-2
"""

# Python imports
import os
import sys
import time
import socket
import urllib
from subprocess import Popen

# find an elementtree implementation
ET = None
errors = []
try:
    import elementtree.ElementTree as ET
except ImportError, e:
    errors.append(e)
try:
    import cElementTree as ET
except ImportError, e:
    errors.append(e)
try:
    import lxml.etree as ET
except ImportError, e:
    errors.append(e)
try:
    import xml.etree.ElementTree as ET
except ImportError, e:
    errors.append(e)
if ET is None:
    raise ImportError(str(errors))

# local imports
import version

# where to look for XML definitions and control scripts
ins_sharepath = []
inp_sharepath = []
if sys.platform == 'win32':
	# look for paths in HKLM\Software\Thousand Parsec\SinglePlayer
	import _winreg
	tpsp = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "Software\\Thousand Parsec\\SinglePlayer")
	try:
		i = 0
		while True:
			name, value, t = _winreg.EnumValue(tpsp, i)
			ins_sharepath.append(value)
			i += 1
	except WindowsError:
		pass
else:
	# use the default unix paths
	ins_sharepath = ['/usr/share/tp', 
		 			 '/usr/share/games/tp', 
           			 '/usr/local/share/tp', 
           			 '/opt/tp', 
           			 os.path.join(version.installpath, 'tp/client/singleplayer'),
		]
	# On development platforms also include the directories in the same path as
	# me.
	if hasattr(version, 'version_git'):
		for repo in [os.path.join('..', r) for r in os.listdir('..')]:
			if os.path.isdir(repo):
				inp_sharepath.append(repo)


class _Server(dict):
	"""\
	Dictionary subclass for server descriptions.
	"""
	def __init__(self):
		for k in ['longname', 'version', 'description', 'commandstring', 'cwd']:
			self[k] = ''
		self['forced'] = []
		self['parameter'] = {}
		self['ruleset'] = {}
		super(_Server, self).__init__()
	
class _AIClient(dict):
	"""\
	Dictionary subclass for AI client descriptions.
	"""
	def __init__(self):
		for k in ['longname', 'version', 'description', 'commandstring', 'cwd']:
			self[k] = ''
		self['rules'] = []
		self['forced'] = []
		self['parameter'] = {}
		super(_AIClient, self).__init__()

class _Ruleset(dict):
	"""\
	Dictionary subclass for ruleset descriptions.
	"""
	def __init__(self):
		for k in ['longname', 'version', 'description']:
			self[k] = ''
		self['forced'] = []
		self['parameter'] = {}
		super(_Ruleset, self).__init__()

class _Parameter(dict):
	"""\
	Dictionary subclass for parameter descriptions.
	"""
	def __init__(self):
		for el in ['type', 'longname', 'description', 'default', 'commandstring']:
			self[el] = ''
		super(_Parameter, self).__init__()

class LocalList(dict):
	"""\
	Local list of servers, rulesets, and AI clients.
	"""

	def __init__(self):
		self['server'] = {}
		self['aiclient'] = {}
		super(LocalList, self).__init__()
	
	def absorb_xml(self, tree, d = None):
		"""\
		Recursively import an XML element tree into the local list. When called
		externally, the tree passed in should be an entire XML file parsed from
		the root, and the d parameter should not be specified. This implementation
		reads documents using the tpconfig DTD, and the classdict classes are the
		major (i.e. with sub-elements) element types specified in that DTD.

		@param tree: The XML element tree to import.
		@type tree: L{ET.ElementTree}
		@param d: A dictionary subclass instance for this type of tree (optional).
		@type d: C{dict}
		"""
		if d is None:
			d = self

		classdict = { 'server' : _Server,
					  'aiclient' : _AIClient,
					  'ruleset' : _Ruleset,
					  'parameter' : _Parameter,
					}

		for k in d.keys():
			if type(d[k]) is dict:
				for s in tree.findall(k):
					sname = s.attrib['name']
					if not d[k].has_key(sname):
						d[k][sname] = classdict[k]()
					self.absorb_xml(s, d[k][sname])
			elif type(d[k]) is list:
				for e in tree.findall(k):
					d[k].append(e.text)
			elif d[k] == '':
				if tree.attrib.has_key(k):
					d[k] = tree.attrib[k]
				elif tree.find(k) is not None:
					d[k] = tree.find(k).text


class DownloadList(dict):
	"""\
	Builds a list of potentially downloadable servers and AI clients.
	"""

	def __init__(self,
				 urlxml = 'http://thousandparsec.net/tp/downloads.xml',
				 urldlp = 'http://thousandparsec.net/tp/downloads.php'):
		super(DownloadList, self).__init__()
		self.urlxml = urlxml
		self.urldlp = urldlp
		self['server'] = {}
		self['ai']  = {}
		self.rulesets = []
		self.got = self.get_list()

	def get_list(self):
		"""\
		Fetch and parse the XML list of available downloads from TP web.

		@return: True if successful, false otherwise.
		@rtype: C{bool}
		"""
		try:
			dlxml = urllib.urlopen(self.urlxml)
			if not dlxml.info()['content-type'] == 'application/xml':
				return False
			xmltree = ET.parse(dlxml)
			for category in xmltree.findall('products/category'):
				cname = category.attrib['name']
				if not cname in self.keys():
					continue

				self[cname] = {}
				for product in category.findall('product'):
					if product.attrib['visible'] == 'no':
						continue

					self[cname][product.attrib['name']] = []
					for rules in product.findall('rules'):
						self[cname][product.attrib['name']].append(rules.text)
						if not rules.text in self.rulesets:
							self.rulesets.append(rules.text)
		# FIXME: Bare excepts are bad.
		except:
			return False
		return True

	def list_servers_with_ruleset(self, rname):
		"""\
		Returns a list of available servers supporting the specified ruleset.

		@param rname: The ruleset name.
		@type rname: C{string}
		@return: A list of servers supporting the ruleset.
		@rtype: C{list} of C{string}
		"""
		servers = []
		for sname in self['server'].keys():
			if rname in self['server'][sname]:
				servers.append(sname)
		return servers

	def list_aiclients_with_ruleset(self, rname):
		"""\
		Returns a list of available AI clients supporting the specified ruleset.

		@param rname: The ruleset name.
		@type rname: C{string}
		@return: A list of AI clients supporting the ruleset.
		@rtype: C{list} of C{string}
		"""
		aiclients = []
		for ainame in self['ai'].keys():
			if rname in self['ai'][ainame]:
				aiclients.append(ainame)
		return aiclients

	def linkurl(self, component = None):
		"""\
		Returns the download page URL, optionally for a specific component type.

		@param component: The component type (optional).
		@type component: C{string}
		@return: A download URL (for component type or all).
		@rtype: C{string}
		"""
		if component in self.keys():
			return self.urldlp + '?category=' + component
		else:
			return self.urldlp

class InitError(Exception):
	"""\
	Generic initialization error, thrown to allow cleanup in certain situations.
	"""
	pass

class SinglePlayerGame:
	"""\
	The single-player game manager. This is the object which should be
	instantiated externally to create a single player game.
	"""

	def __init__(self):
		# build local list
		self.locallist = LocalList()
		self.import_locallist(ins_sharepath, 'installed')
		if hasattr(version, 'version_git'):
			self.import_locallist(inp_sharepath, 'inplace')

		# verify existence of command paths referred to in local list
		for t in self.locallist.keys():
			for s in self.locallist[t].keys():
				exe = self.locallist[t][s]['commandstring'].split()[0]
				found = False
				if self.locallist[t][s]['cwd']:
					if os.path.exists(os.path.join(self.locallist[t][s]['cwd'], exe)) \
					or os.path.exists(os.path.join(self.locallist[t][s]['cwd'], exe + '.exe')):
						found = True
				else:
					for dir in os.environ.get('PATH').split(':'):
						if os.path.exists(os.path.join(dir, exe)):
							found = True
							break
				if not found:
					print "Removing %s as command %s was not found." % (
						self.locallist[t][s]['longname'], exe)
					del self.locallist[t][s]

		# initialize internals
		self.active = False
		self.sname = ''
		self.rname = ''
		self.sparams = {}
		self.rparams = {}
		self.opponents = []

	def __del__(self):
		if self.active:
			self.stop()

	def import_locallist(self, sharepath, stype):
		"""\
		Build the local list from various XML files on the system.

		@param sharepath: A list of search paths for single player XML files.
		@type sharepath: C{list} of C{string}
		@param stype: The type of files to import ('installed' or 'inplace').
		@type stype: C{string}
		"""
		for sharedir in sharepath:
			for dir in [sharedir, os.path.join(sharedir, 'servers'), os.path.join(sharedir, 'aiclients')]:
				if not os.path.isdir(dir):
					print "Warning search directory %s does not exist" % dir
					continue

				print "Searching in directory: %s" % dir

				for xmlfile in os.listdir(dir):
					xmlfile = os.path.join(dir, xmlfile)
					if not os.path.isfile(xmlfile):
						continue

					if not xmlfile.endswith('xml'):
						continue

					print "Found xml file at %s" % (xmlfile)
					try:
						xmltree = ET.parse(xmlfile)
					except:
						continue

					# ensure this is a tpconfig document
					if not xmltree._root.tag == 'tpconfig':
						continue

					# ensure it is of the type we are looking for
					if (not xmltree._root.attrib.has_key('type') and stype != 'installed') \
					or xmltree._root.attrib.has_key('type') and xmltree._root.attrib['type'] != stype:
						continue

					print "Found single player xml file at %s/%s - including" % (sharedir, xmlfile)
					self.locallist.absorb_xml(xmltree)

	@property
	def servers(self):
		"""\
		Returns a list of available servers.

		@return: A list of servers.
		@rtype: C{list} of C{string}
		"""
		return self.locallist['server'].keys()
	
	@property
	def aiclients(self):
		"""\
		Returns a list of available AI clients.

		@return: A list of AI clients.
		@rtype: C{list} of C{string}
		"""
		return self.locallist['aiclient'].keys()

	@property
	def rulesets(self):
		"""\
		Returns a list of available rulesets from all servers.

		@return: A list of rulesets.
		@rtype: C{list} of C{string}
		"""
		rulesets = []
		for sname in self.locallist['server'].keys():
			for rname in self.locallist['server'][sname]['ruleset'].keys():
				if rname not in rulesets:
					rulesets.append(rname)
		rulesets.sort()
		return rulesets

	def server_info(self, sname = None):
		"""\
		Returns information about a server.

		@param sname: Server name (optional).
		@type sname: C{string}
		@return Information about current or specified server.
		@rtype: C{dict}
		"""
		if sname is None:
			sname = self.sname
		try:
			return self.locallist['server'][sname]
		except KeyError, e:
			return None

	def aiclient_info(self, ainame = None):
		"""\
		Returns information about an AI client.

		@param ainame: AI client name.
		@type ainame: C{string}
		@return: Information about specified AI client.
		@rtype: C{dict}
		"""
		try:
			return self.locallist['aiclient'][ainame]
		except KeyError, e:
			return None

	def ruleset_info(self, rname = None):
		"""\
		Returns information about a ruleset.

		@param rname Ruleset name (optional).
		@return Information about current or specified ruleset.
		"""
		if rname is None:
			rname = self.rname
		if self.sname:
			sname = self.sname
		else:
			for sname in self.locallist['server'].keys():
				if self.locallist['server'][sname]['ruleset'].has_key(rname):
					break
		try:
			return self.locallist['server'][sname]['ruleset'][rname]
		except KeyError, e:
			return None

	def list_servers_with_ruleset(self, rname = None):
		"""\
		Returns a list of servers supporting the current or specified ruleset.

		@param rname: Ruleset name (optional).
		@type rname: C{string}
		@return: A list of servers.
		@rtype: C{list} of C{string}
		"""
		if rname is None:
			rname = self.rname
		servers = []
		for sname in self.locallist['server'].keys():
			if self.locallist['server'][sname]['ruleset'].has_key(rname):
				servers.append(sname)
		servers.sort()
		return servers

	def list_aiclients_with_ruleset(self, rname = None):
		"""\
		Returns a list of AI clients supporting the current or specified ruleset.

		@param rname: Ruleset name (optional).
		@type rname: C{string}
		@return: A list of AI clients.
		@rtype: C{list} of C{string}
		"""
		if rname is None:
			rname = self.rname
		aiclients = []
		for ainame in self.locallist['aiclient'].keys():
			if rname in self.locallist['aiclient'][ainame]['rules']:
				aiclients.append(ainame)
		aiclients.sort()
		return aiclients

	def list_sparams(self, sname = None):
		"""\
		Returns the parameter list for the current or specified server.

		@param sname: Server name (optional).
		@type sname: C{string}
		@return: The server parameter list.
		@rtype: C{dict}
		"""
		if sname is None:
			sname = self.sname
		return self.locallist['server'][sname]['parameter']

	def list_aiparams(self, ainame):
		"""\
		Returns the parameter list for the specified AI client.

		@param ainame: AI client name.
		@type ainame: C{string}
		@return: The AI client parameter list.
		@rtype: C{dict}
		"""
		return self.locallist['aiclient'][ainame]['parameter']

	def list_rparams(self, sname = None, rname = None):
		"""\
		Returns the parameter list for the current or specified ruleset.

		@param rname: Ruleset name (optional).
		@type rname: C{string}
		@return: The ruleset parameter list.
		@rtype: C{dict}
		"""
		if sname is None:
			sname = self.sname
		if rname is None:
			rname = self.rname
		return self.locallist['server'][sname]['ruleset'][rname]['parameter']
	
	def add_opponent(self, name, user, parameters):
		"""\
		Adds an AI client opponent to the game (before starting).

		@param name: The name of the AI client.
		@type name: C{string}
		@param user: The desired username of the opponent.
		@type user: C{string}
		@param parameters: A dictionary of parameters in the form {'name', 'value'}.
		@type parameters: C{dict}
		@return: True if successful, false otherwise.
		@rtype: C{bool}
		"""
		for aiclient in self.opponents:
			if aiclient['user'] is user:
				return False

		aiclient = {
				'name' : name,
				'user' : user,
				'parameters' : parameters,
			}
		self.opponents.append(aiclient)

		return True

	def start(self):
		"""\
		Starts the server and AI clients.

		@return: Port number (OK to connect) or False.
		@rtype: C{int}
		"""
		import atexit
		atexit.register(self.stop)

		if self.active:
			return

		# find a free port
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind(('localhost',0))
		port = s.getsockname()[1]
		s.close()

		try:
			# start server
			server = self.locallist['server'][self.sname]
			ruleset = server['ruleset'][self.rname]
			
			# start server - set working directory
			servercwd = server['cwd']
			if servercwd == '':
				servercwd = None

			# start server - create server command line
			servercmd = server['commandstring']

			# start server - add forced parameters to command line
			for forced in server['forced']:
				servercmd += ' ' + forced

			# start server - set ruleset and port
			servercmd = servercmd % {
						'rname' : self.rname,
						'port' : port,
					}

			# start server - add regular parameters to command line
			for pname in server['parameter'].keys():
				value = server['parameter'][pname]['default']
				if self.sparams.has_key(pname):
					value = self.sparams[pname]
				value = self._format_value(value, server['parameter'][pname]['type'])
				if value is None:
					continue
				servercmd += ' ' + server['parameter'][pname]['commandstring'] % value

			# start server - add forced ruleset parameters to command line
			for forced in ruleset['forced']:
				servercmd += ' ' + forced
			
			# start server - add regular ruleset parameters to command line
			for pname in ruleset['parameter'].keys():
				value = ruleset['parameter'][pname]['default']
				if self.rparams.has_key(pname):
					value = self.rparams[pname]
				value = self._format_value(value, ruleset['parameter'][pname]['type'])
				if value is None:
					continue
				elif value == '':
					servercmd += ' ' + ruleset['parameter'][pname]['commandstring']
				else:
					servercmd += ' ' + ruleset['parameter'][pname]['commandstring'] % value

			# start server - call the control script
			# TODO: allow redirection of stdout and stderr
			try:
				self.sproc = Popen(servercmd.split(), cwd = servercwd)
			except OSError, e:
				raise InitError(e)

			print "Running server with cmd:", servercmd

			# wait for the server to initialize
			# FIXME: use admin protocol if available to check this (loop)
			time.sleep(5)
	
			# start AI clients
			for aiclient in self.opponents:
				# set working directory
				aicwd = self.locallist['aiclient'][aiclient['name']]['cwd']
				if aicwd == '':
					aicwd = None

				# create ai client command line
				aicmd = self.locallist['aiclient'][aiclient['name']]['commandstring']
				
				# add forced parameters to command line
				for forced in self.locallist['aiclient'][aiclient['name']]['forced']:
					aicmd += ' ' + forced

				# set port, ruleset and username
				aicmd = aicmd % {
						'port' : port,
						'rname' : self.rname,
						'user' : aiclient['user'],
					}

				# add regular parameters to command line
				for pname in self.locallist['aiclient'][aiclient['name']]['parameter'].keys():
					value = self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['default']
					if aiclient['parameter'].has_key(pname):
						value = aiclient['parameter'][pname]
					value = self._format_value(value, self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['type'])
					if value is None:
						continue
					aicmd += ' ' + self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['commandstring'] % value

				print "Running AI (%s) with cmd: %s" % (aiclient['name'], aicmd)

				# call the control script
				# TODO: allow redirection stdout and stderr
				try:
					aiclient['proc'] = Popen(aicmd.split(), cwd = aicwd)
				except OSError, e:
					raise InitError(e)

			# set active flag
			self.active = True

			# ensure that processes stay alive
			time.sleep(2)
			if not self.sproc.poll() is None:
				raise InitError
			for aiclient in self.opponents:
				if not aiclient['proc'].poll() is None:
					raise InitError

		except InitError, e:
			print e
			self.stop()
			return False

		return port

	def stop(self):
		"""\
		Stops the server and AI clients.
		Should be called by the client when disconnecting/closing.
		"""
		if not self.active:
			return

		# stop server
		if self.sname != '':
			try:
				self.sproc.kill()
			except OSError, e:
				pass
			self.sname = ''
			self.rname = ''

		# stop AI clients
		for aiclient in self.opponents:
			try:
				aiclient['proc'].kill()
			except OSError, e:
				pass
		self.opponents = []

		# reset active flag
		self.active = False

	def _format_value(self, value, ptype):
		"""\
		Internal: formats a parameter value based on type.

		@oaram value: The value to format.
		@type value: C{string}
		@param ptype: The target value type (I, S, F, B).
		@type ptype: C{string}
		@return: The formatted value or None.
		"""
		if value is None or str(value) == '':
			return None
		elif ptype == 'I':
			return int(value)
		elif ptype == 'S' or type == 'F':
			return str(value)
		elif ptype == 'B' and str(value) == 'True':
			return ''
		else:
			return None
