# Python imports
import os
import subprocess
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


# where to look for XML definitions and control scripts
sharepath = ['/usr/share/tp', '/usr/local/share/tp', '/opt/tp']


class ServerList(dict):
	"""\
	Builds a list of servers from multiple XML files.
	Includes rulesets and special parameters.
	"""

	def absorb_xml(self, xmlfile):
		"""\
		Import an XML file describing a server or server component.

		@param xmlfile The XML file to import.
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
				self[sname]['parameters'][pname] = {
						'type' : sparam.attrib['type'],
						'longname' : sparam.find('longname').text,
						'description' : sparam.find('description').text,
						'default' : sparam.find('default').text,
						'commandstring' : sparam.find('commandstring').text
					}
			for ruleset in server.findall('ruleset'):
				rname = ruleset.attrib['name']
				self[sname]['rulesets'][rname] = {
						'longname' : ruleset.find('longname').text,
						'version' : ruleset.find('version').text,
						'description' : ruleset.find('description').text,
						'forced' : [],
						'parameters' : {},
					}
				for forced in ruleset.findall('forced'):
					self[sname]['rulesets'][rname]['forced'].append(forced.text)
				for rparam in ruleset.findall('parameter'):
					pname = rparam.attrib['name']
					self[sname]['rulesets'][rname]['parameters'][pname] = {
							'type' : rparam.attrib['type'],
							'longname' : rparam.find('longname').text,
							'description' : rparam.find('description').text,
							'default' : rparam.find('default').text,
							'commandstring' : rparam.find('commandstring').text
						}

class AIList(dict):
	"""\
	Builds a list of AIs from multiple XML files.
	Includes rulesets and special parameters.
	"""

	def absorb_xml(self, xmlfile):
		"""\
		Import an XML file describing a server or server component.

		@param xmlfile The XML file to import.
		"""
		xmltree = ET.parse(xmlfile)
		for aiclient in xmltree.findall('aiclient'):
			ainame = aiclient.attrib['name']
			if not self.has_key(ainame):
				self[ainame] = {}
				self[ainame]['longname'] = aiclient.find('longname').text
				self[ainame]['version'] = aiclient.find('version').text
				self[ainame]['description'] = aiclient.find('description').text
				self[ainame]['rules'] = []
				self[ainame]['forced'] = []
				self[ainame]['parameters'] = {}
			for rules in aiclient.findall('rules'):
				self[ainame]['rules'].append(rules.text)
			for forced in aiclient.findall('forced'):
				self[ainame]['forced'].append(forced.text)
			for aiparam in aiclient.findall('parameter'):
				pname = aiparam.attrib['name']
				self[ainame]['parameters'][pname] = {
						'type' : aiparam.attrib['type'],
						'longname' : aiparam.find('longname').text,
						'description' : aiparam.find('description').text,
						'default' : aiparam.find('default').text,
						'commandstring' : aiparam.find('commandstring').text,
					}


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

		# build server and AI client lists
		self.serverlist = ServerList()
		self.ailist = AIList()
		for sharedir in sharepath:
			if os.path.isdir(sharedir):
				for xmlfile in os.listdir(os.path.join(sharedir, 'servers')):
					xmlfile = os.path.join(sharedir, 'servers', xmlfile)
					if os.path.isfile(xmlfile) and xmlfile.endswith('xml'):
						self.serverlist.absorb_xml(xmlfile)
				for xmlfile in os.listdir(os.path.join(sharedir, 'aiclients')):
					xmlfile = os.path.join(sharedir, 'aiclients', xmlfile)
					if os.path.isfile(xmlfile) and xmlfile.endswith('xml'):
						self.ailist.absorb_xml(xmlfile)

		# initialize internals
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
		for sname in self.serverlist.keys():
			for rname in self.serverlist[sname]['rulesets'].keys():
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
			sname = self.sname
			rname = self.rname
		else:
			for sname in self.serverlist.keys():
				if self.serverlist[sname]['rulesets'].has_key(rname):
					break
		try:
			return self.serverlist[sname]['rulesets'][rname]
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
		for sname in self.serverlist.keys():
			if self.serverlist[sname]['rulesets'].has_key(rname):
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
		for ainame in self.ailist.keys():
			if rname in self.ailist[ainame]['rules']:
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
		return self.serverlist[sname]['parameters']

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
		return self.serverlist[sname]['rulesets'][rname]['parameters']

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
		# find a free port
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind(('localhost',0))
		port = s.getsockname()[1]
		s.close()

		try:
			# start server
			server = self.serverlist[self.sname]
			ruleset = server['rulesets'][self.rname]

			# start server - create server command line
			servercmd = ''
			for sharedir in sharepath:
				if os.path.isdir(sharedir) and os.path.isfile(os.path.join(sharedir, 'servers', self.sname + '.init')):
					servercmd = "%s start %s %s" % (os.path.join(sharedir, 'servers', self.sname + '.init'), self.rname, port)
					break
			if servercmd == '':
				raise InitError, 'Server control script for ' + self.sname + ' not found'

			# start server - add forced parameters to command line
			for forced in server['forced']:
				servercmd += ' ' + forced

			# start server - add regular parameters to command line
			for pname in server['parameters'].keys():
				value = server['parameters'][pname]['default']
				if self.sparams.has_key(pname):
					value = self.sparams[pname]
				value = self._format_value(value, server['parameters'][pname]['type'])
				if value is None:
					continue
				servercmd += ' ' + server['parameters'][pname]['commandstring'] % value

			# start server - add forced ruleset parameters to command line
			for forced in ruleset['forced']:
				servercmd += ' ' + forced
			
			# start server - add regular ruleset parameters to command line
			for pname in ruleset['parameters'].keys():
				value = ruleset['parameters'][pname]['default']
				if self.rparams.has_key(pname):
					value = self.rparams[pname]
				value = self._format_value(value, ruleset['parameters'][pname]['type'])
				if value is None:
					continue
				servercmd += ' ' + ruleset['parameters'][pname]['commandstring'] % value

			# start server - call the control script
			rc = subprocess.call(servercmd, shell=True)
			if rc is not 0:
				raise InitError, 'Server ' + sname + ' failed to start'

			# wait for the server to initialize
			# FIXME: what is the system is loaded?
			time.sleep(5)
	
			# start AI clients
			for aiclient in self.opponents:
				aicmd = ''
				for sharedir in sharepath:
					if os.path.isdir(sharedir) and os.path.isfile(os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init')):
						aicmd = "%(path)s start %(rname)s %(port)i %(user)s" % {
									'path': os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init'),
									'port': port,
									'rname': self.rname,
									'user': aiclient['user'],
								}
						break
				if aicmd == '':
					raise InitError, 'AI client control script for ' + aiclient['name'] + ' not found'
				
				# add forced parameters to command line
				for forced in self.ailist[aiclient['name']]['forced']:
					aicmd += ' ' + forced

				# add regular parameters to command line
				for pname in self.ailist[aiclient['name']]['parameters'].keys():
					value = self.ailist[aiclient['name']]['parameters'][pname]['default']
					if aiclient['parameters'].has_key(pname):
						value = aiclient['parameters'][pname]
					value = self._format_value(value, self.ailist[aiclient['name']]['parameters'][pname]['type'])
					if value is None:
						continue
					aicmd += ' ' + self.ailist[aiclient['name']]['parameters'][pname]['commandstring'] % value

				# call the control script
				rc = subprocess.call(aicmd, shell=True)
				if rc is not 0:
					raise InitError, 'AI client ' + aiclient['name'] + ' failed to start'

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
		# stop server
		if self.sname is not None:
			servercmd = ''
			for sharedir in sharepath:
				if os.path.isdir(sharedir) and os.path.isfile(os.path.join(sharedir, 'servers', self.sname + '.init')):
					servercmd = os.path.join(sharedir, 'servers', self.sname + '.init') + ' stop'
					break
			if servercmd != '':
				os.system(servercmd)
			self.sname = None

		# stop AI clients
		for aiclient in self.opponents:
			aicmd = ''
			for sharedir in sharepath:
				if os.path.isdir(sharedir) and os.path.isfile(os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init')):
					aicmd = os.path.join(sharedir, 'aiclients', aiclient['name'] + '.init') + ' stop'
			if aicmd != '':
				os.system(aicmd)

		# reset active flag
		self.active = False

	def _format_value(self, value, type):
		"""\
		Internal: formats a parameter value based on type.

		@oaram value The value to format.
		@param type The target value type (I, S, or B).
		@return The formatted value or None.
		"""
		if value is None or str(value) == '':
			return None
		elif type == 'I':
			return int(value)
		elif type == 'S':
			 return str(value)
		elif type == 'B':
			return ''
		else:
			return None
