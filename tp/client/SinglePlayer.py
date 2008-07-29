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


class ServerList(dict):
	"""\
	Builds a list of servers from multiple XML files.
	Includes rulesets and special parameters.
	"""

	def absorb_xml(self, xmlfile):
		xmltree = ET.parse(xmlfile)
		for server in xmltree.findall('server'):
			sname = server.attrib['name']
			if not self.has_key(sname):
				self[sname] = {}
				self[sname]['parameters'] = {}
				self[sname]['rulesets'] = {}
			if not self[sname].has_key('longname'):
				self[sname]['longname'] = server.find('longname').text
			if not self[sname].has_key('version'):
				self[sname]['version'] = server.find('version').text
			if not self[sname].has_key('description'):
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
