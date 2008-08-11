
import schemepy as scheme

def get(list, id):
	for lid, value in list:
		if lid == id:
			return value
	return None

class DesignCalculator:
	def __init__(self, cache, design):
		self.cache = cache
		self.design = design

		self.__dirty = True

	def rank(self):
		if self.__dirty:
			ranks = {}
			for component_id, number in self.design.components:
				component = self.cache.components[component_id]
	
				for property_id, value in component.properties:
					property = self.cache.properties[property_id]
					
					if not ranks.has_key(property.rank):
						ranks[property.rank] = []
	
					if not property_id in ranks[property.rank]:
						ranks[property.rank].append(property_id)

			self.__ranks = ranks
		return self.__ranks

	def change(self, component, amount):
		"""\
		change(component, amount) -> None
		
		Changes the current design by adding/subtracting the certain amount of a component.
		"""
		self.__dirty = True

		i = 0
		while True:
			# FIXME: There should be a better way to do this.
			if i >= len(self.design.components):
				self.design.components.append([component.id, amount])
				break

			if self.design.components[i][0] == component.id:
				if isinstance(self.design.components[i], tuple):
					self.design.components[i] = list(self.design.components[i])
				self.design.components[i][1] += amount
	
				if self.design.components[i][1] < 0:
					del self.design.components[i]
				break
			i += 1

	def calculate(self):
		"""\
		calculate() -> Interpretor, Properties

		Calculates all the properties on a design. 
		Returns the Interpretor and the object with the Properties.
		"""
		vm = scheme.VM(profile="tpcl")

		# Step 1 -------------------------------------
		ranks = self.rank()
		print "The order I need to calculate stuff in is,", ranks

		# Step 2 -------------------------------------
		# The object which will store the properties calculated
		class Properties(dict):
			pass

		properties = Properties()
		vm.define("design", vm.toscheme(properties))

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
						value = vm.fromscheme(vm.eval(vm.compile("""(%s design)""" % value)))

						print "The value calculated for component %i was %r" % (component_id, value)
					
						for x in range(0, amount):
							bits.append(value)

				print "All the values calculated where", bits
				bits_scheme = "(list"
				for bit in bits:
					bits_scheme += " " + str(bit).replace('L', '')
				bits_scheme += ")"
				print "In scheme that is", bits_scheme
				
				total = vm.fromscheme(vm.eval(vm.compile("""(let ((bits %s)) (%s design bits))""" % \
									 (bits_scheme, property.calculate))))
				value, display = total.car, total.cdr

				print "In total I got '%i' which will be displayed as '%s'" % (value, display)
				properties[property.name] = (property_id, value, display)

				def t(properties, name=property.name):
					return properties[name][1]

				vm.define('designtype.'+property.name, vm.toscheme(t))
				
		print "The final properties we have are", properties.items()
		return vm, properties
	
	def check(self, vm, properties):
		"""\
		check(Interperator, Properties) -> Valid, Feedback

		Checks the requirements of a design.

		Returns if the properties are valid and a string which has human readable feedback.
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
				result = vm.fromscheme(vm.eval(vm.compile("""(%s design)""" % property.requirements)))
				print "Result was:", result
				okay, feedback = result.car, result.cdr

				if okay is not True:
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
			result = vm.fromscheme(vm.eval(vm.compile("""(%s design)""" % component.requirements)))
			print "Result was:", result
			okay, feedback = result.car, result.cdr

			if okay is not True:
				total_okay = False
		
			if feedback != "":
				total_feedback.append(feedback)

		return total_okay, "\n".join(total_feedback)

	def apply(self, properties, okay, feedback):
		"""\
		apply(Properties, 
		Apply the results returned from calculate/check to the design object.
		"""
		self.design.properties = [(x[0], x[2]) for x in properties.values()]
		self.design.feedback = feedback

		self.design.used = (-1, 0)[okay]

	def update(self):
		if self.__dirty:
			vm, p = self.calculate()
			okay, reason = self.check(vm, p)
			self.apply(p, okay, reason)
