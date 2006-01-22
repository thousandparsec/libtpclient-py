
import pyscheme as scheme

def get(list, id):
	for lid, value in list:
		if lid == id:
			return value
	return None

class DesignCalculator:
	def __init__(self, cache, design):
		self.cache = cache
		self.design = design

	def rank(self):
		if len(self.design.components) <= 0:
			return {}

		ranks = {}
		for component_id, number in self.design.components:
			component = self.cache.components[component_id]

			for property_id, value in component.properties:
				property = self.cache.properties[property_id]
				
				if not ranks.has_key(property.rank):
					ranks[property.rank] = []

				if not property_id in ranks[property.rank]:
					ranks[property.rank].append(property_id)

		return ranks

	def calculate(self):
		"""\
		calculate() -> Interpretor, Design

		Calculates all the properties on a design. 
		Returns the Interpretor (used to create the design and the actual design).
		"""
		i = scheme.make_interpreter()

		# Step 1 -------------------------------------
		ranks = self.rank()
		print "The order I need to calculate stuff in is,", ranks

		# Step 2 -------------------------------------
		# The design object
		class Design(dict):
			pass

		design = Design()
		scheme.environment.defineVariable(scheme.symbol.Symbol('design'), design, i.get_environment())

		# Step 3 -------------------------------------
		for rank in ranks.keys():
			for property_id in ranks[rank]:
				property = self.cache.properties[property_id]

				# Where we will store the values as calculated
				bits = []
		
				# Get all the components we contain
				for component_id, amount in self.design.components:
					# Create the component object
					component = self.cache.components[component_id] 

					# Calculate the actual value for this design
					value = get(component.properties, property_id)
					if value:
						print "Now evaluating", value
						value = i.eval(scheme.parse("""(%s design)""" % value))

						print "The value calculated for component %i was %r" % (component_id, value)
					
						for x in range(0, amount):
							bits.append(value)

				print "All the values calculated where", bits
				bits_scheme = "(list"
				for bit in bits:
					bits_scheme += " " + str(bit).replace('L', '')
				bits_scheme += ")"
				print "In scheme that is", bits_scheme
				
				total = i.eval(scheme.parse("""(let ((bits %s)) (%s design bits))""" % (bits_scheme, property.calculate)))
				value, display = scheme.pair.car(total), scheme.pair.cdr(total)

				print "In total I got '%i' which will be displayed as '%s'" % (value, display)
				design[property.name] = (property_id, value, display)

				def t(design, name=property.name):
					return design[name][1]
				
				i.install_function('designtype.'+property.name, t)
				
		print "The final properties we have are", design.items()
		return i, design
	
	def check(self, i, design):
		"""\
		check() -> Valid, Feedback

		Checks the requirements of a design.

		Returns if the design is valid and a string which has human readable feedback.
		"""
		total_okay = True
		total_feedback = []

		# Step 2, calculate the requirements for the properties
		ranks = self.rank()
		for rank in ranks.keys():
			for property_id in ranks[rank]:

				property = self.cache.properties[property_id]
				if property.requirements == '':
					print "Property with id (%i) doesn't have any requirements" % property_id
					continue
			
				print "Now checking the following requirement"
				print property.requirements
				result = i.eval(scheme.parse("""(%s design)""" % property.requirements))
				print "Result was:", result
				okay, feedback = scheme.pair.car(result), scheme.pair.cdr(result)

				if okay != scheme.symbol.Symbol('#t'):
					total_okay = False
		
				if feedback != "":
					total_feedback.append(feedback)
				
		# Step 3, calculate the requirements for the components
		for component_id, amount in self.design.components:
			component = self.cache.components[component_id]
			if component.requirements == '':
				print "Component with id (%i) doesn't have any requirements" % property_id
				continue
			
			print "Now checking the following requirement"
			print component.requirements
			result = i.eval(scheme.parse("""(%s design)""" % component.requirements))
			print "Result was:", result
			okay, feedback = scheme.pair.car(result), scheme.pair.cdr(result)

			if okay != scheme.symbol.Symbol('#t'):
				total_okay = False
		
			if feedback != "":
				total_feedback.append(feedback)

		return total_okay, "\n".join(total_feedback)

	def apply(self, details, okay, feedback):
		"""\
		Apply the results returned from calculate/check to the design object.
		"""
		self.design.properties = [(x[0], x[2]) for x in details.values()]
		self.design.feedback = feedback

		self.design.used = (-1, 0)[okay]
