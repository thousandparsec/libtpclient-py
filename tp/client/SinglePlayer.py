# Python imports
import os
import time
import socket

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


# TODO: do this properly
sharedir = '/usr/share/tp'


class ServerList(dict):
	"""\
	Builds a list of servers from multiple XML files.
	Includes rulesets and special parameters.
	"""

	def absorb_xml(self, xmlfile):
		"""\
		Import an XML file describing a server or server component.
		"""
		xmltree = ET.parse(xmlfile)
		for server in xmltree.findall('server'):
			sname = server.attrib['name']
			if not self.has_key(sname):
				self[sname] = {}
				self[sname]['forced'] = []
				self[sname]['parameters'] = {}
				self[sname]['rulesets'] = {}
			if not self[sname].has_key('longname') and server.find('longname') is not None:
				self[sname]['longname'] = server.find('longname').text
			if not self[sname].has_key('version') and server.find('version') is not None:
				self[sname]['version'] = server.find('version').text
			if not self[sname].has_key('description') and server.find('description') is not None:
				self[sname]['description'] = server.find('description').text
			for forced in server.findall('forced'):
				self[sname]['forced'].append(forced.text)
			for sparam in server.findall('parameter'):
				pname = sparam.attrib['name']
				self[sname]['parameters'][pname] = { \
					'type' : sparam.attrib['type'],
					'longname' : sparam.find('longname').text,
					'description' : sparam.find('description').text,
					'default' : sparam.find('default').text,
					'commandstring' : sparam.find('commandstring').text }
			for ruleset in server.findall('ruleset'):
				rname = ruleset.attrib['name']
				self[sname]['rulesets'][rname] = { \
					'longname' : ruleset.find('longname').text,
					'version' : ruleset.find('version').text,
					'description' : ruleset.find('description').text,
					'forced' : [],
					'parameters' : {} }
				for forced in ruleset.findall('forced'):
					self[sname]['rulesets'][rname]['forced'].append(forced.text)
				for rparam in ruleset.findall('parameter'):
					pname = rparam.attrib['name']
					self[sname]['rulesets'][rname]['parameters'][pname] = { \
						'type' : rparam.attrib['type'],
						'longname' : rparam.find('longname').text,
						'description' : rparam.find('description').text,
						'default' : rparam.find('default').text,
						'commandstring' : rparam.find('commandstring').text }

class AIList(dict):
	"""\
	Builds a list of AIs from multiple XML files.
	Includes rulesets and special parameters.
	"""

	def absorb_xml(self, xmlfile):
		"""\
		Import an XML file describing a server or server component.
		"""
		xmltree = ET.parse(xmlfile)
		for aiclient in xmltree.findall('aiclient'):
			ainame = aiclient.attrib['name']
			if not self.has_key(ainame):
				self[ainame] = {}
				self[ainame]['rules'] = []
				self[ainame]['forced'] = []
				self[ainame]['parameters'] = {}
			for rules in aiclient.findall('rules'):
				self[ainame]['rules'].append(rules.text)
			for forced in aiclient.findall('forced'):
				self[ainame]['forced'].append(forced.text)
			for aiparam in aiclient.findall('parameter'):
				pname = aiparam.attrib['name']
				self[ainame]['parameters'][pname] = { \
					'type' : aiparam.attrib['type'],
					'longname' : aiparam.find('longname').text,
					'description' : aiparam.find('description').text,
					'default' : aiparam.find('default').text,
					'commandstring' : aiparam.find('commandstring').text }


class InitError(Exception):
	pass

class SinglePlayerGame:
	"""\
	A single-player game manager.
	"""

	def __init__(self):
		#reset active flag
		self.active = False
		self.sname = None

		# build a server list
		self.serverlist = ServerList()
		for xmlfile in os.listdir(os.path.join(sharedir, 'servers')):
			xmlfile = os.path.join(sharedir, 'servers', xmlfile)
			if os.path.isfile(xmlfile) and xmlfile.endswith('xml'):
				self.serverlist.absorb_xml(xmlfile)

		# build an AI client list
		self.ailist = AIList()
		for xmlfile in os.listdir(os.path.join(sharedir, 'aiclients')):
			xmlfile = os.path.join(sharedir, 'aiclients', xmlfile)
			if os.path.isfile(xmlfile) and xmlfile.endswith('xml'):
				self.ailist.absorb_xml(xmlfile)

		# prepare internals
		self.opponents = []

	def __del__(self):
		if self.active:
			self.stop()

	def list_rulesets(self):
		"""\
		Returns a list of available rulesets from all servers.
		"""
		rulesets = []
		for sname in self.serverlist.keys():
			for rname in self.serverlist[sname]['rulesets'].keys():
				if rname not in rulesets:
					rulesets.append(rname)
		return rulesets

	def list_servers_with_ruleset(self, rname):
		"""\
		Returns a list of servers supporting a given ruleset.
		"""
		servers = []
		for sname in self.serverlist.keys():
			if self.serverlist[sname]['rulesets'].has_key(rname):
				servers.append(sname)
		return servers

	def list_aiclients_with_ruleset(self, rname):
		"""\
		Returns a list of AI clients supporting a given ruleset.
		"""
		aiclients = []
		for ainame in self.ailist.keys():
			if rname in self.ailist[ainame]['rules']:
				aiclients.append(ainame)
		return aiclients

	def add_opponent(self, ainame, aiparams):
		"""\
		Adds an AI client opponent to the game (before starting).

		Parameters:
		ainame (string) - the name of the AI client
		aiparams (dict) - parameters {'name', 'value'}
		"""
		aiclient = { \
			'name' : ainame,
			'parameters' : aiparams }
		self.opponents.append(aiclient)

	def start(self, sname, sparams, rname, rparams):
		"""\
		Starts the server and AI clients.
		Returns True if successful (OK to connect).

		Parameters:
		sname (string) - the name of the server to start
		sparams (dict) - server parameters {'name', 'value'}
		rname (string) - the name of the ruleset to use
		rparams (dict) - ruleset parameters {'name', 'value'}
		"""
		# find a free port
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind(('localhost',0))
		port = s.getsockname()[1]
		s.close()

		try:
			# start server
			self.sname = sname
			servercmd = os.path.join(sharedir, 'servers', sname + '.init') + ' start ' + str(port) + ' ' + rname
			for forced in self.serverlist[sname]['forced']:
				servercmd += ' ' + forced
			for pname in self.serverlist[sname]['parameters'].keys():
				value = self.serverlist[sname]['parameters'][pname]['default']
				if sparams.has_key(pname):
					value = sparams[pname]
				value = self._format_value(value, self.serverlist[sname]['parameters'][pname]['type'])
				if value is None:
					continue
				servercmd += ' ' + self.serverlist[sname]['parameters'][pname]['commandstring'] % value
			for forced in self.serverlist[sname]['rulesets'][rname]['forced']:
				servercmd += ' ' + forced
			for pname in self.serverlist[sname]['rulesets'][rname]['parameters'].keys():
				value = self.serverlist[sname]['rulesets'][rname]['parameters'][pname]['default']
				if rparams.has_key(pname):
					value = rparams[pname]
				value = self._format_value(value, self.serverlist[sname]['rulesets'][rname]['parameters'][pname]['type'])
				if value is None:
					continue
				servercmd += ' ' + self.serverlist[sname]['rulesets'][rname]['parameters'][pname]['commandstring'] % value
			if os.system(servercmd) is not 0:
				raise InitError, 'Server ' + sname + ' failed to start'

			# wait for the server to initialize
			time.sleep(5)
	
			# start AI clients
			for aiclient in self.opponents:
				aicmd = os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init') + ' start ' + str(port) + ' ' + rname
				for forced in self.ailist[aiclient['name']]['forced']:
					aicmd += ' ' + forced
				for pname in self.ailist[aiclient['name']]['parameters'].keys():
					value = self.ailist[aiclient['name']]['parameters'][pname]['default']
					if aiclient['parameters'].has_key(pname):
						value = aiclient['parameters'][pname]
					value = self._format_value(value, self.ailist[aiclient['name']]['parameters'][pname]['type'])
					if value is None:
						continue
					aicmd += ' ' + self.ailist[aiclient['name']]['parameters'][pname]['commandstring'] % value
				if os.system(aicmd) is not 0:
					raise InitError, 'AI client ' + aiclient['name'] + ' failed to start'

			# set active flag
			self.active = True

		except:
			self.stop()

		return self.active

	def stop(self):
		"""\
		Stops the server and AI clients.
		Should be called by the client when disconnecting/closing.
		"""
		# stop server
		if self.sname is not None:
			servercmd = os.path.join(sharedir, 'servers', self.sname + '.init') + ' stop'
			os.system(servercmd)
			self.sname = None

		# stop AI clients
		for aiclient in self.opponents:
			aicmd = os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init') + ' stop'
			os.system(aicmd)

		# reset active flag
		self.active = False

	def _format_value(self, value, type):
		"""\
		Internal: formats a parameter value based on type.
		"""
		if value is None:
			return None
		elif type is 'I':
			return int(value)
		elif type is 'S':
			return str(value)
		elif type is 'B':
			return ''
		else:
			return None
