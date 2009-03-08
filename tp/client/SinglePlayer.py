# Python imports
import os
import sys
import time
import socket
import urllib
from killableprocess import Popen

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
if sys.platform == 'win32':
	# look for paths in HKLM\Software\Thousand Parsec\SinglePlayer
	import _winreg
	tpsp = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "Software\\Thousand Parsec\\SinglePlayer")
	sharepath = []
	try:
		i = 0
		while True:
			name, value, type = _winreg.EnumValue(tpsp, i)
			sharepath.append(value)
			i += 1
	except WindowsError:
		pass
else:
	# use the default unix paths
	sharepath = ['/usr/share/tp', 
				 '/usr/share/games/tp', 
                 '/usr/local/share/tp', 
                 '/opt/tp', 
                 os.path.join(version.installpath, 'tp/client/singleplayer')]
	# On development platforms also include the directories in the same path as
	# me.
	if hasattr(version, 'version_git'):
		for repo in [os.path.join('..', r) for r in os.listdir('..')]:
			if os.path.isdir(repo):
				sharepath.append(repo)


class _Server(dict):
	def __init__(self):
		for k in ['longname', 'version', 'description', 'commandstring', 'cwd']:
			self[k] = ''
		self['forced'] = []
		self['parameter'] = {}
		self['ruleset'] = {}
		super(_Server, self).__init__()
	
class _AIClient(dict):
	def __init__(self):
		for k in ['longname', 'version', 'description', 'commandstring', 'cwd']:
			self[k] = ''
		self['rules'] = []
		self['forced'] = []
		self['parameter'] = {}
		super(_AIClient, self).__init__()

class _Ruleset(dict):
	def __init__(self):
		for k in ['longname', 'version', 'description']:
			self[k] = ''
		self['forced'] = []
		self['parameter'] = {}
		super(_Ruleset, self).__init__()

class _Parameter(dict):
	def __init__(self):
		for el in ['type', 'longname', 'description', 'default', 'commandstring']:
			self[el] = ''
		super(_Parameter, self).__init__()

class LocalList(dict):
	"""\
	"""

	def __init__(self):
		self['server'] = {}
		self['aiclient'] = {}
		super(LocalList, self).__init__()
	
	def absorb_xml(self, tree, d = None):
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
		"""
		servers = []
		for sname in self['server'].keys():
			if rname in self['server'][sname]:
				servers.append(sname)
		return servers

	def list_aiclients_with_ruleset(self, rname):
		"""\
		Returns a list of available AI clients supporting the specified ruleset.
		"""
		aiclients = []
		for ainame in self['ai'].keys():
			if rname in self['ai'][ainame]:
				aiclients.append(ainame)
		return aiclients

	def linkurl(self, component = None):
		"""\
		Returns the download page URL, optionally for a specific component type.
		"""
		if component in self.keys():
			return self.urldlp + '?category=' + component
		else:
			return self.urldlp

class InitError(Exception):
	pass

class SinglePlayerGame:
	"""\
	A single-player game manager.
	"""

	def __init__(self):
		# build local list
		self.locallist = LocalList()
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

					print "Found xml file at %s/%s" % (sharedir, xmlfile)
					try:
						xmltree = ET.parse(xmlfile)
					except:
						continue

					if not xmltree._root.tag == 'tpconfig':
						continue

					print "Found single player xml file at %s/%s - including" % (sharedir, xmlfile)
					self.locallist.absorb_xml(xmltree)

		# verify existence of command paths referred to in local list
		for t in self.locallist.keys():
			for s in self.locallist[t].keys():
				if not os.path.exists(os.path.join(self.locallist[t][s]['cwd'], self.locallist[t][s]['commandstring'].split()[0])):
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

	@property
	def rulesets(self):
		"""\
		Returns a list of available rulesets from all servers.

		@return A list of rulesets.
		"""
		rulesets = []
		for sname in self.locallist['server'].keys():
			for rname in self.locallist['server'][sname]['ruleset'].keys():
				if rname not in rulesets:
					rulesets.append(rname)
		return rulesets

	def ruleset_info(self, rname = None):
		"""\
		Returns information about a ruleset.

		@param rname Ruleset name (optional).
		@return Current or first found by name ruleset information,
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
		except KeyError:
			return None

	def list_servers_with_ruleset(self, rname = None):
		"""\
		Returns a list of servers supporting the current or specified ruleset.

		@param rname Ruleset name (optional).
		@return A list of servers.
		"""
		if rname is None:
			rname = self.rname
		servers = []
		for sname in self.locallist['server'].keys():
			if self.locallist['server'][sname]['ruleset'].has_key(rname):
				servers.append(sname)
		return servers

	def list_aiclients_with_ruleset(self, rname = None):
		"""\
		Returns a list of AI clients supporting the current or specified ruleset.

		@param rname Ruleset name (optional).
		@return A list of AI clients.
		"""
		if rname is None:
			rname = self.rname
		aiclients = []
		for ainame in self.locallist['aiclient'].keys():
			if rname in self.locallist['aiclient'][ainame]['rules']:
				aiclients.append(ainame)
		return aiclients

	def list_sparams(self, sname = None):
		"""\
		Returns the parameter list for the current or specified server.

		@param sname Server name (optional).
		@return The server parameter list.
		"""
		if sname is None:
			sname = self.sname
		return self.locallist['server'][sname]['parameter']

	def list_rparams(self, sname = None, rname = None):
		"""\
		Returns the parameter list for the current or specified ruleset.

		@param rname Ruleset name (optional).
		@return The ruleset parameter list.
		"""
		if sname is None:
			sname = self.sname
		if rname is None:
			rname = self.rname
		return self.locallist['server'][sname]['ruleset'][rname]['parameter']

	def add_opponent(self, ainame, aiuser, aiparams):
		"""\
		Adds an AI client opponent to the game (before starting).

		@param ainame The name of the AI client.
		@param aiuser The desired username of the opponent.
		@param aiparams A dictionary of parameters in the form {'name', 'value'}.
		"""
		for aiclient in self.opponents:
			if aiclient['user'] is aiuser:
				return False

		aiclient = {
				'name' : ainame,
				'user' : aiuser.translate(''.join([chr(x) for x in range(256)]),' '),
				'parameters' : aiparams,
			}
		self.opponents.append(aiclient)

		return True

	def start(self):
		"""\
		Starts the server and AI clients.

		@return Port number (OK to connect) or False.
		"""
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
			servercmd = server['commandstring'] % {
						'rname': self.rname,
						'port': port,
					}

			# start server - add forced parameters to command line
			for forced in server['forced']:
				servercmd += ' ' + forced

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
				servercmd += ' ' + ruleset['parameter'][pname]['commandstring'] % value

			# start server - call the control script
			# TODO: allow redirection of stdout and stderr
			self.sproc = Popen(servercmd, cwd = servercwd, shell = True)

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
				aicmd = self.locallist['aiclient'][aiclient['name']]['commandstring'] % {
							'port': port,
							'rname': self.rname,
							'user': aiclient['user'],
						}
				
				# add forced parameters to command line
				for forced in self.locallist['aiclient'][aiclient['name']]['forced']:
					aicmd += ' ' + forced

				# add regular parameters to command line
				for pname in self.locallist['aiclient'][aiclient['name']]['parameter'].keys():
					value = self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['default']
					if aiclient['parameter'].has_key(pname):
						value = aiclient['parameter'][pname]
					value = self._format_value(value, self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['type'])
					if value is None:
						continue
					aicmd += ' ' + self.locallist['aiclient'][aiclient['name']]['parameter'][pname]['commandstring'] % value

				# call the control script
				# TODO: allow redirection stdout and stderr
				aiclient['proc'] = Popen(aicmd, cwd = aicwd, shell = True)

			# set active flag
			self.active = True

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
			self.sproc.kill()
			self.sname = ''
			self.rname = ''

		# stop AI clients
		for aiclient in self.opponents:
			aiclient['proc'].kill()
		self.opponents = []

		# reset active flag
		self.active = False

	def _format_value(self, value, type):
		"""\
		Internal: formats a parameter value based on type.

		@oaram value The value to format.
		@param type The target value type (I, S, F, B).
		@return The formatted value or None.
		"""
		if value is None or str(value) == '':
			return None
		elif type == 'I':
			return int(value)
		elif type == 'S' or type == 'F':
			return str(value)
		elif type == 'B':
			return ''
		else:
			return None
