# Python imports
import os

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
				self[sname]['parameters'] = {}
				self[sname]['rulesets'] = {}
			if not self[sname].has_key('longname') and server.find('longname') != None:
				self[sname]['longname'] = server.find('longname').text
			if not self[sname].has_key('version') and server.find('version') != None:
				self[sname]['version'] = server.find('version').text
			if not self[sname].has_key('description') and server.find('description') != None:
				self[sname]['description'] = server.find('description').text
			for sparam in server.findall('parameter'):
				pname = sparam.attrib['name']
				self[sname]['parameters'][pname] = { \
					'type' : sparam.attrib['type'], \
					'longname' : sparam.find('longname').text, \
					'description' : sparam.find('description').text, \
					'default' : sparam.find('default').text, \
					'commandstring' : sparam.find('commandstring').text \
					}
			for ruleset in server.findall('ruleset'):
				rname = ruleset.attrib['name']
				self[sname]['rulesets'][rname] = { \
					'longname' : ruleset.find('longname').text, \
					'version' : ruleset.find('version').text, \
					'description' : ruleset.find('description').text, \
					'parameters' : {} \
					}
				for rparam in ruleset.findall('parameter'):
					pname = rparam.attrib['name']
					self[sname]['rulesets'][rname]['parameters'][pname] = { \
						'type' : rparam.attrib['type'], \
						'longname' : rparam.find('longname').text, \
						'description' : rparam.find('description').text, \
						'default' : rparam.find('default').text, \
						'commandstring' : rparam.find('commandstring').text \
						}

class SinglePlayerGame:
	"""\
	A single-player game manager.
	"""
	def __init__(self):
		# build a server list
		self.servers = ServerList()
		for xmlfile in os.listdir(os.path.join(sharedir, 'servers')):
			xmlfile = os.path.join(sharedir, 'servers', xmlfile)
			if os.path.isfile(xmlfile) and xmlfile.endswith('xml'):
				self.servers.absorb_xml(xmlfile)

	def start(self, sname, port, sparams, ruleset, rparams, ainame, ainum, aiparams):
		pass
	
	def stop(self):
		pass
