"""
A class which uses threads to launch and watch the output.
"""

import os
import time
import subprocess
import threading
from threadcheck import thread_checker, thread_safe

from cStringIO import StringIO

class Launcher(threading.Thread):
	def __init__(self, torun, cwd, scrollback=1000, onexit=None, onready=None):
		"""
		A class which starts another process and stores the stdout out.
		(stderr is redirect to stdout.)

		Args:
			cwd:   Location where to start the program.
			torun: Program (with full path) and args to start.
			scrollback: The number of lines to store in scrollback (defaults to 1000).

			onready: Tuple of 
					  (Regex object to match,
					   Function to be called when the program output matches regex.)

			onexit: Function to be called when the program exits.
					The function takes a single argument, the return code of
					the process.  
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
		"""Start the process."""

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
		"""*Internal*"""
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
			self.onexit(self.process.returncode)

	def kill(self, waitfor=30):
		"""Kill the process.

		Firsts tries a soft kill (SIGTERM) and if the process does not die,
		then a hard kill (SIGKILL).

		Args:
			waitfor: How long to wait between the two kills.
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

