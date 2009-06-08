"""\
A class which uses threads to launch and watch the output.

@author: Tim Ansell (mithro)
@organization: Thousand Parsec
@license: GPL-2
"""

import os
import time
import subprocess
import threading
from threadcheck import thread_checker, thread_safe

from cStringIO import StringIO

class Launcher(threading.Thread):
	def __init__(self, torun, cwd, scrollback=1000, onexit=None, onready=None):
		"""\
		A class which starts another process and stores the stdout out.
		(stderr is redirect to stdout.)

		@param cwd: Location where to start the program.
		@type cwd: C{string}
		@param torun: Program (with full path) and args to start.
		@type torun: C{string}
		@param scrollback: The number of lines to store in scrollback (default 1000).
		@type scrollback: C{int}
		@param onready: Tuple of (regex object to match, function to be called when
		the program output matches regex).
		@type onready: C{tuple}
		@param onexit: Function to be called when the program exits, taking
		a reference to this launcher instance as an argument.
		@type onexit: C{function}
		"""
		threading.Thread.__init__(self)

		# Check the program we are going to start exists
		self.torun = torun.split()
		if not os.path.exists(self.torun[0]):
			raise OSError("No such program exists.")

		# Check where we are going to start it exists.
		self.cwd = cwd
		if not os.path.exists(cwd):
			raise OSError("Working directory does not exist.")

		# We are we stored the scrollback 
		self.scrollback = scrollback
		self.stdout = []

		# Exit Callback
		self.onexit = onexit
		self.onready = onready

	def launch(self):
		"""\
		Start the process.
		"""
		self.process = subprocess.Popen(
			self.torun,
			bufsize=0,
			stdin=subprocess.PIPE,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			close_fds=True,
			shell=False,
			cwd=self.cwd)

		# Close stdout so it doesn't have an error.	
		self.process.stdin.close()

		self.start()
	
	def run(self):
		"""\
		Internal - overrides Thread.run().
		"""
		while self.process.poll() is None:
			self.stdout.append(self.process.stdout.readline()[:-1])
	
			# Check if the system has entered the "ready" state.	
			if self.onready and self.onready[0].match(self.stdout):
				self.onready[1]()

			# Cull the excess scrollback	
			while len(self.stdout) > self.scrollback:
				self.stdout.pop(0)

		# Exit Callback
		if self.onexit is not None:
			self.onexit(self)

	def kill(self, waitfor=30):
		"""\
		Kill the process. First tries a soft kill (SIGTERM) and if the process
		does not die, then a hard kill (SIGKILL).

		@param waitfor: Time in seconds to wait between the two kills.
		@type waitfor: C{int}
		"""
		self.process.terminate()

		# Wait for the process to die
		termtime = time.time()
		while self.process.poll() is None:
			# Kill it if we have been waiting too long.
			if time.time() - termtime > waitfor:
				self.process.kill()


if __name__ == "__main__":
	def yexit(r):
		print time.time(), "y", r
	def nexit(r):
		print time.time(), "n", r

	y = Launcher("/usr/bin/yes", "/", onexit=yexit)
	y.launch()
	n = Launcher("/usr/bin/nohup /usr/bin/yes n", "/", onexit=nexit)
	n.launch()

	start = time.time()
	while (time.time() - start) < 10:
		print 'y', len(y.stdout), y.stdout[:10]
		print 'n', len(n.stdout), n.stdout[:10]
		time.sleep(5)

	time.time()
	y.kill()
	n.kill()
