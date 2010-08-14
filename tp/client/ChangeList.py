#! /bin/python
"""

This file includes an implimentation of a datastructure that can handle all the
problems associated with the evil slot interface we use in Thousand Parsec.

"""

import copy
import pickle

class ChangeNode(object):
	NodeCounter = 0

	states = ["creating", "idle", "updating", "removing", "removed"]

	def __init__(self, what):
		# FIXME: Must be a better way to do this...
		ChangeNode.NodeCounter += 1
		self.id = ChangeNode.NodeCounter

		self.left  = None
		self.right = None

		self._what    = what
		self._pending = []

	def AddState(self, state, pending=None):
		if self.LastState in ("removing", "removed"):
			raise SystemError("Can not add new states to the node if it is being removed!")

		self._pending.append([state, pending])

	def UpdatePending(self, pending):
		assert len(self._pending) > 0

		self._pending[0] = (self._pending[0][0], pending)

	@property
	def LastState(self):
		if len(self._pending) == 0:
			return "idle"
		else:
			return self._pending[-1][0]

	@property
	def CurrentState(self):
		if len(self._pending) == 0:
			return "idle"
		else:
			return self._pending[0][0]

	@property
	def ServerOrder(self):
		"""\
		The value as it currently exists on the server.
		"""
		return self._what

	@property
	def PendingOrder(self):
		"""\
		Returns the first pending change.
		"""
		if len(self._pending) == 0:
			return self._what
		else:
			return self._pending[0][1]
	
	@property
	def CurrentOrder(self):
		"""\
		Returns the 'latest' order
		"""
		order = None
		for state, order in reversed(self._pending):
			if not order is None:
				break

		if not order is None:
			return order

		return self._what

	def PopState(self):
		assert len(self._pending) > 0

		state, pending = self._pending.pop(0)

		if state == "updating" or state == "creating":
			assert not pending is None
			self._what = pending

	def inlist(self):
		return \
			(self.left  is None or self.left.right == self) \
				and \
			(self.right is None or self.right.left == self)

	def __repr__(self):
		if self.left is None:
			l = "None"
		else:
			l = hex(self.left.id)

		if self.right is None:
			r = "None"
		else:
			r = hex(self.right.id)

		return "<Node(%x)-%r <%s %s>>" % (self.id, self._what, l, r)
	__str__ = __repr__

	def __eq__(self, other):
		try:
			return self._what is other._what
		except AttributeError:
			return False

	def __neq__(self, other):
		return not self.__eq__(other)

	@property
	def pending(self):
		assert False

	@property
	def what(self):
		assert False

class ChangeHead(ChangeNode):
	def __init__(self):
		ChangeNode.__init__(self, None)

		self.__dict__['CurrentState'] = "head"
		self.__dict__['LastState']    = "head"

	def __repr__(self):
		return ChangeNode.__repr__(self).replace("Node", "Head")
	__str__ = __repr__

	def SetState(self, *args, **kw):
		raise SystemError("Should not be calling this on a head node!")

class ChangeList(object):
	def __init__(self):
		self.head = ChangeHead()

	def __getitem__(self, id):
		if isinstance(id, slice):
			return self.__iter__(id)

		node = self.head.right
		while node != None:
			if node.id == id:
				return node
			node = node.right
		raise KeyError("No node exists with id %s" % id)

	def __getstate__(self):
		l = []
		for i in self:
			l.append(copy.copy(i))
			l[-1].left = None
			l[-1].right = None	

		return pickle.dumps(l)

	def __setstate__(self, args):
		args = pickle.loads(args)

		head = ChangeHead()
		node = head

		while len(args) > 0:
			node.right = args.pop()
			node.right.left = node

			node = node.right

		self.head = head

	def __delitem__(self, id):
		node = self[id]

		node.left.right = node.right
		if not node.right is None:
			node.right.left = node.left

	def __contains__(self, tofind):
		if tofind is self.head:
			return True
		try:
			self[tofind.id]
			return True
		except KeyError:
			return False

	def __len__(self):
		l = 0
	
		node = self.head.right
		while node != None:
			l += 1
			node = node.right

		return l

	def __iter__(self, sliceme=None):
		# FIXME: Should be better way to do this
		if sliceme is None:
			sliceme = slice(0, len(self), 1)

		start = sliceme.start
		stop  = sliceme.stop
		step  = sliceme.step

		if step is None:
			step  = 1
		if start is None:
			start = 0
		if stop is None:
			stop  = len(self)

		if start < 0:
			start += len(self)
		if stop < 0:
			stop  += len(self)

		i = 0

		node = self.head.right
		while node != None:
			if i >= start and i < stop and i % step == 0:
				yield node
			node = node.right

			i += 1

		raise StopIteration

	def index(self, needle):
		if needle is self.head:
			return -1
		for i, node in enumerate(self):
			if node is needle:
				return i
		raise IndexError("%s was not found in the list!" % needle)

	def slot(self, needle):
		if needle is self.head:
			return -1
		i = 0
		for node in self:
			if node is needle:
				return i
			if node.CurrentState != "creating":
				i += 1
		raise IndexError("%s was not found in the list!" % needle)

	def append(self, toappend):
		node = self.head
		while node.right != None:
			node = node.right
		self.insert_after(node, toappend)

	def find(self, what):
		node = self.head
		while node != None:
			if node._what is what:
				return node
			node = node.right

	@property
	def first(self):
		if self.head.right is None:
			return self.head
		return self.head.right

	@property
	def last(self):
		node = self.head
		while node.right != None:
			node = node.right
		assert not node is None
		return node

	def insert_after(self, node, ins):
		before = node
		after  = node.right

		if not node.inlist():
			before = node.right.left

		before.right = ins
		ins.left     = before

		if not after is None:
			after.left = ins
		ins.right = after

	def insert_before(self, node, ins):
		if node == self.head:
			raise "Can't insert before head"

		before = node.left
		after  = node

		if not node.inlist():
			after = node.left.right
		
		after.left = ins
		ins.right  = after

		if not before is None:
			before.right = ins
		ins.left = before

if __name__ == "__main__":

	l = ChangeList()

	n1 = ChangeNode(1)
	n2 = ChangeNode(2)
	nt = ChangeNode('t')

	l.insert_after(l.head, n1)
	print '--', l.head
	for i, node in enumerate(l):
		print '->', i, node
	print

	l.insert_after(n1, n2)
	print '--', l.head
	for i, node in enumerate(l):
		print '->', i, node
	print
	
	l.insert_before(n2, nt)
	print '--', l.head
	for i, node in enumerate(l):
		print '->', i, node
	print

	del l[nt.id]
	print 't', nt
	print
	print '--', l.head
	for i, node in enumerate(l):
		print '->', i, node
	print

	l.insert_after( n1, ChangeNode('>'))
	l.insert_before(n2, ChangeNode('<'))
	print '--', l.head
	for i, node in enumerate(l):
		print '->', i, node
	print

	l.insert_after( nt, ChangeNode("a"))
	l.insert_before(nt, ChangeNode("b"))
	print 't', nt
	print
	print '--', l.head
	for i, node in enumerate(l):
		print i, node
	print

	for i in l[1:-1]:
		print i
	print

	print 0,   l.index(n1), l.first
	print -1,  l.index(n2), l.last

	print
	print '--', l.head
	for i, node in enumerate(l):
		print i, node
	print
	del l[l.last.id]
	print '--', l.head
	for i, node in enumerate(l):
		print i, node
	print

	nodes = []
	for node in l:
		nodes.append(node)

	for node in nodes:
		del l[node.id]

	print '--', l.head
	for i, node in enumerate(l):
		print i, node
	print
	
