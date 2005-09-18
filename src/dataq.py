#!/usr/bin/python
#
# DataQ v0.3
#
# DataQ: A simple message/data queueing server.
# 
# 
# Copyright (C) 2005, Ferry Boender 
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

"""
DataQ: A simple message/data queueing server.
"""

usageStr =\
	"""[-v] [-V] [-c path] [-a address] [-p port]

  -c Configuration file to use
  -a IP address to listen on. (overrides config) Default: All IPs
  -p Port to listen on. (overrides config) Default: 50000.
  -d Run in daemon mode (detach from terminal)
  -V Verbose mode. Lots-o-output.
  -v Print version information
"""

#
# Exit codes:
# 
#  -1 Incorrect usage
#  -2 Fatal system resource problem
#  -3 Configuration file problem
#  -4 Import error; missing python package
#  -5 Daemon starting error
#  -6 Couldn't create spool dir 

import sys
import signal
import getopt
import os 
import SocketServer
import socket
import select
from xml.dom.ext.reader import Sax
from xml import xpath
try:
	from xml.parsers.xmlproc import xmlproc
except ImportError:
	sys.stderr.write("Error while importing xmlproc. Is python-xml installed? Aborting.\n");
	sys.exit(-4);

def str2bool(string):
	retBool = None
	
	if string.lower() == "true":
		retBool = True
	else:
		retBool = False

	return(retBool)
		
class DataqError(Exception):

	""" 
	The DataqError exception is thrown whenever a server run-time error is
	detected. For instance, when a client requests a non-existing queue.
	"""

	messages = {
		# Syntactic request errors
		101: "Bad syntax in request",
		102: "Unknown request type",

		# Data errors
		201: "Unknown queue",
		202: "Access denied",
		203: "Queue is full",
	}

	def __init__(self, value):
		self.value = value
		self.message = self.messages[self.value]

	def getValue(self):
		return(self.value)

	def getMessage(self):
		return(self.message)

	def __str__(self):
		return("ERROR " + str(self.value) + " " + self.message)

class ConfigError(Exception):

	""" 
	The ConfigError exception is thrown by the Config class when problems occur
	in the configuration file.
	"""

	messages = {
		# Meta config errors
		001: "No usable config file found",
		002: "Syntax error",

		# Access rule definition errors
		101: "Incorrect access rule position",
		102: "Wrong value for sense",

		# Queue definition errors
		201: "Wrong value for type",
		202: "Wrong value for size",
		203: "Wrong value for overflow",
		204: "Queue name is requird",

		# Queue Pool definition errors
		301: "Wrong value for spool event",

		999: "Undefined exception",
	}

	def __init__(self, value):
		self.value = value
		self.message = self.messages[self.value]

	def getValue(self):
		return(self.value)

	def getMessage(self):
		return(self.message)

	def __str__(self):
		return("ERROR " + str(self.value) + " " + self.message)

class DaemonError(Exception):

	""" 
	The DaemonError exception is thrown when something goes wrong during the
	process of daemonizing (detaching from the console) the dataq server.
	"""

	messages = {
		101: "DataQ server already running",
		102: "Couldn't log PID",
		103: "Couldn't remove PID file",
	}

	def __init__(self, value):
		self.value = value
		self.message = self.messages[self.value]

	def getValue(self):
		return(self.value)

	def getMessage(self):
		return(self.message)

	def __str__(self):
		return("ERROR " + str(self.value) + " " + self.message)

class Log:

	""" 
	Console, verbose and system log logger.
	"""

	def verbose(type, msg):
		global verbose

		if verbose:
			print "[" + type + "] " + msg
		
	def verboseMsg(msg):
		Log.verbose("m", msg)
			
	def verboseWarn(msg):
		Log.verbose("w", msg)

	def verboseErr(msg):
		Log.verbose("e", msg)

	verbose = staticmethod(verbose)
	verboseMsg = staticmethod(verboseMsg)
	verboseWarn = staticmethod(verboseWarn)
	verboseErr = staticmethod(verboseErr)
	
class Access:

	"""
	Access Control class. One instance of this class contains (non) access
	information for a single host/user/password combination.
	"""

	def __init__(self, sense = "allow", password = "", username = "", host = ""):
		if sense != "allow" and sense != "deny":
			raise UserWarning, "Wrong value for sense"
		
		self.sense = sense
		self.password = password
		self.username = username
		self.host = host

class Queue:

	""" 
	Base queue class that handles generic actions on queues. Derive new queue
	types (FILO, FIFO, etc) from this class.
	"""

	def __init__(self, name, type, size, overflow, spooldir):
		if type != "filo" and type != "fifo":
			raise UserWarning, "Wrong value for type"
		if size < 1:
			raise UserWarning, "Wrong value for size"
		if overflow != "deny" and overflow != "pop":
			raise UserWarning, "Wrong value for overflow"
			
		self.name = name
		self.type = type
		self.size = size
		self.overflow = overflow
		self.spooldir = spooldir

		Log.verboseMsg("Registered new queue '" + self.name + "' (type:" + self.type + ", size: " + str(self.size) + ", overflow: " + self.overflow + ")")

		self.readSpool()

	def __len__(self):
		return(len(self.queue))

	def push(self, message):
		retResponse = ""
		
		if len(self.queue) == self.size:
			if self.overflow == "pop":
				self.pop()
			elif self.overflow == "deny":
				raise DataqError, 203 # Queue is full
				
		Log.verboseMsg("Pushing to " + self.name + ": " + message)

		self.queue.append(message)

		return(retResponse)
				
	def stat(self):
		retResponse = ""

		Log.verboseMsg("Statistics for " + self.name)

		retResponse += "name:" + self.name + "\n"
		retResponse += "type:" + self.type + "\n"
		retResponse += "size:" + str(self.size) + "\n"
		retResponse += "overflow:" + self.overflow + "\n"
		retResponse += "messages:" + str(len(self.queue)) + "\n"

		return(retResponse)

	def clear(self):

		retResponse = ""
		self.queue = []

		return(retResponse)

	def addAccess(self, access):

		Log.verboseMsg("Adding '" + (access.sense) + "' access for P:" + str(access.password) + " U:" + str(access.username) + " H: " + str(access.host) + " to queue '" + self.name + "'")
		access.queuename = self.name
		self.accessList.append(access)

	def hasAccess(self, password, username, host):

		for access in self.accessList:

			matchHost = False
			matchUsername = False
			matchPassword = False

			if access.host != "" and host == access.host:
				matchHost = True
			if access.username != "" and username == access.username:
				matchUsername = True
			if access.password != "" and password == access.password:
				matchPassword = True

			if (access.host == "" or matchHost) and (access.username == "" or matchUsername) and (access.password == "" or matchPassword):
				if access.sense == "deny":
					return(False)
				if access.sense == "allow" or access.sense == "":
					return(True)
				
		return(None)

	def writeSpool(self):
		
		Log.verboseMsg("Writing queue '" + self.name + "' to "+self.spooldir+self.name+".")

		try:
			f = open(self.spooldir+self.name, 'w')
			for data in self.queue:
				f.write(data+'\n')
			f.close()
		except IOError, e:
			Log.verboseErr("Couldn't write '"+self.name+"' queue's data to "+self.spooldir+self.name)
		
	def readSpool(self):
		
		Log.verboseMsg("Reading queue '"+self.name+"' from "+self.spooldir+self.name)

		try:
			f = open(self.spooldir+self.name, 'r')
			self.queue = f.readlines()
		except IOError, e:
			Log.verboseWarn("Couldn't read '"+self.name+"' queue's data from "+self.spooldir+self.name)

class FifoQueue(Queue):

	"""
	FIFO Queue: First message in is the first message out. (Queue)
	"""
		
	def __init__(self, name, size, overflow, spooldir):
		self.queue = []
		self.accessList = []

		Queue.__init__(self, name, "fifo", size, overflow, spooldir)

	def pop(self):
		retResponse = ""

		Log.verboseMsg("POPing from " + self.name)

		if len(self.queue) > 0:
			retResponse = self.queue.pop(0)

		return(retResponse)

class FiloQueue(Queue):

	"""
	FILO Queue: First message in is the first out. (Stack)
	"""

	def __init__(self, name, size, overflow, spooldir):
		self.queue = []
		self.accessList = []
		Queue.__init__(self, name, "filo", size, overflow, spooldir)

	def pop(self):
		retResponse = ""

		Log.verboseMsg("POPing from " + self.name)

		if len(self.queue) > 0:
			retResponse = self.queue.pop()

		return(retResponse)

class QueuePool:
	
	"""
	Intermediary class between queues and the server's request handler.  This
	class takes care of creation, communication and access checking for queues.
	"""

	def __init__(self, spoolDir, spoolEvents):
		self.queues = {}
		self.accessList = []

		self.spoolDir = spoolDir
		self.spoolEvents = spoolEvents

		if self.spoolDir[-1] != '/':
			self.spoolDir += '/'

	def createQueue(self, name, type, size, overflow):
		if type == "fifo":
			newQueue = FifoQueue(name, size, overflow, self.spoolDir)
		elif type == "filo":
			newQueue = FiloQueue(name, size, overflow, self.spoolDir)
		else:
			raise UserWarning, "Wrong value for type"

		self.queues[name] = newQueue

		return(newQueue)

	def addAccess(self, access):
		Log.verboseMsg("Adding '" + str(access.sense) + "' access for P:" + str(access.password) + " U:" + str(access.username) + " H: " + str(access.host) + " to queuePool")
		self.accessList.append(access)

	def hasAccess(self, password, username, host):

		for access in self.accessList:

			matchHost = False
			matchUsername = False
			matchPassword = False

			if access.host != "" and host == access.host:
				matchHost = True
			if access.username != "" and username == access.username:
				matchUsername = True
			if access.password != "" and password == access.password:
				matchPassword = True

			if (access.host == "" or matchHost) and (access.username == "" or matchUsername) and (access.password == "" or matchPassword):
				if access.sense == "deny":
					return(False)
				if access.sense == "allow" or access.sense == "":
					return(True)
				
		return(None)

	def checkAccess(self, password, username, host, queue = None):
		qpAccess = queuePool.hasAccess(password, username, host)
		Log.verboseMsg("QueuePoolAccess = " + str(qpAccess))

		if queue != None:
			qAccess = queue.hasAccess(password, username, host)
			Log.verboseMsg("QueueAccess     = " + str(qAccess))

			if qAccess == False:
				raise DataqError, 202

			if qAccess == None:
				if not qpAccess == True:
					raise DataqError, 202
		else:
			if not qpAccess == True:
				raise DataqError, 202
				
	def push(self, host, queueURI, message):
		retResponse = ""
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise DataqError, 201 # Unknown queue

		queue = self.queues[queueName]

		self.checkAccess(password, username, host, queue);

		retResponse = queue.push(message)

		for spoolEvent in self.spoolEvents:
			if spoolEvent == "write":
				self.writeSpool(queueName)

		return(retResponse)

	def pop(self, host, queueURI):
		retResponse = ""
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise DataqError, 201 # Unknown queue

		queue = self.queues[queueName]

		self.checkAccess(password, username, host, queue);

		retResponse = queue.pop()

		for spoolEvent in self.spoolEvents:
			if spoolEvent == "write":
				self.writeSpool(queueName)

		return(retResponse)

	def stat(self, host, queueURI):
		retResponse = ""
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		Log.verboseWarn(queueURI)

		if queueName == "":

			self.checkAccess(password, username, host);

			retResponse = ""

			for queueName in self.queues:
				queue = self.queues[queueName]
				retResponse += "queue:" + queue.name + "\n"
		else:
			if queueName not in self.queues:
				raise DataqError, 201 # Unknown queue

			queue = self.queues[queueName]

			self.checkAccess(password, username, host, queue);

			retResponse = queue.stat()

		return(retResponse)

	def clear(self, host, queueURI):
		retResponse = ""
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise DataqError, 201 # Unknown queue

		queue = self.queues[queueName]

		self.checkAccess(password, username, host, queue);

		retResponse = queue.clear()

		for spoolEvent in self.spoolEvents:
			if spoolEvent == "write":
				self.writeSpool(queueName)

		return(retResponse)

	def parseQueueURI(self, queueURI):
		password = ""
		username = ""
		queueName = ""

		try:
			queueName = queueURI
			authentication, queueName = queueURI.split("@", 1)
			password = authentication
			username, password = authentication.split(":", 1)
		except ValueError:
			pass
			
		return (username, password, queueName)
		
	def writeSpool(self, queueName = None):
		if queueName == None:
			for queueName in self.queues:
				queue = self.queues[queueName]
				queue.writeSpool()
		else:
			self.queues[queueName].writeSpool()

class RequestHandler(SocketServer.BaseRequestHandler):

	"""
	Handle a single incomming connection by reading a request, processing it,
	delegating it to the queuePool and then transmitting the resulting data
	(error, popped message, etc).
	"""
	
	def __init__(self, request, client_address, server):
		SocketServer.BaseRequestHandler.__init__(self, request, client_address, server)

	def handle(self):

		Log.verboseMsg("Connection from " + self.client_address[0] + ":" + str(self.client_address[1]))

		ready_to_read, ready_to_write, in_error = select.select([self.request], [], [], None)

		text = ''
		done = False
		while not done:

			if len(ready_to_read) == 1 and ready_to_read[0] == self.request:
				data = self.request.recv(1024)

				if not data:
					break
				elif len(data) > 0:
					text += str(data)

					while text.find("\n") != -1:
						line, text = text.split("\n", 1)
						line = line.rstrip()
						
						Log.verboseMsg(
							self.client_address[0] + \
							": Raw command '" + \
							line + \
							"'")

						try:
							response = self.process(line)
						except DataqError, e:
							response = str(e) + "\n"

						self.request.send(response)

						done = True

		self.request.close()
		Log.verboseMsg("Connection closed from " + self.client_address[0] + ":" + str(self.client_address[1]))

	def finish(self):
		"""Nothing"""

	def process(self, data):

		retResponse = ""
		
		try:
			requestType = data
			requestType, data = data.split(" ", 1)
		except ValueError:
			data = ""
			pass

		if requestType.upper() == "PUSH":
			retResponse = self.processPush(data)
		elif requestType.upper() == "POP":
			retResponse = self.processPop(data)
		elif requestType.upper() == "STAT":
			retResponse = self.processStat(data)
		elif requestType.upper() == "CLEAR":
			retResponse = self.processClear(data)
		else:
			raise DataqError, 102 # Unknown request type

		return retResponse
	
	def processPush(self, data):
		global queuePool
		
		retResponse = ""
		
		try:
			queueURI, data = data.split(" ", 1)
			retResponse = queuePool.push(self.client_address[0], queueURI, data)
		except ValueError:
			raise DataqError, 101 # Bad syntax in request

		return retResponse

	def processPop(self, data):
		global queuePool
		
		retResponse = ""
		
		try:
			queueURI = data
			retResponse = queuePool.pop(self.client_address[0], queueURI)
		except ValueError:
			raise DataqError, 101 # Bad syntax in request

		return retResponse

	def processStat(self, data):
		global queuePool

		retResponse = ""

		queueURI = data

		retResponse = queuePool.stat(self.client_address[0], queueURI)

		return(retResponse)

	def processClear(self, data):
		global queuePool
		
		retResponse = ""
		
		try:
			queueURI = data
			retResponse = queuePool.clear(self.client_address[0], queueURI)
		except ValueError:
			raise DataqError, 101 # Bad syntax in request

		return retResponse

class Server(SocketServer.ThreadingMixIn, SocketServer.TCPServer):

	"""
	Basic socket server
	"""

	daemon_threads = True
	allow_reuse_address = True

	def __init__(self, server_address, RequestHandlerClass):
		SocketServer.TCPServer.__init__(self, server_address, RequestHandlerClass)

class Daemon:

	"""
	Daemonize the current process (detach it from the console).
	"""
	
	def __init__(self, pidfile):
		
		self.pidfile = pidfile

		# Check if a previous daemon is running
		if os.path.exists(self.pidfile):
			raise DaemonError, 101

		try: 
			pid = os.fork() 
			if pid > 0:
				# Parent
				sys.exit(0) 
		except OSError, e: 
			print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror) 
			sys.exit(-2)

		os.chdir("/") 
		os.setsid() 
		os.umask(0) 

		try: 
			pid = os.fork() 
			if pid > 0:
				# parent
				sys.exit(0) 
		except OSError, e: 
			print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror) 
			sys.exit(-2) 

		self.logPID(os.getpid())

	def logPID(self, pid):
		Log.verboseMsg("PID: " + str(pid))
		# Write the daemon PID to the PID file (default /var/run/dataq.pid)
		try:
			f = open(self.pidfile, 'w')
			f.write(str(pid))
			f.close()
		except IOError, e:
			raise DaemonError, 102 # Couldn't log PID

		
	def cleanup(self):

		# Clean up PID file
		Log.verboseMsg("Cleaning up daemon process")
		try:
			os.remove(self.pidfile)
		except IOError, e:
			raise DaemonError, 103 # Couldn't remove PID file

class Config:

	"""
	The Config class takes a list of possible configuration files and a
	dictionary of configuration values that need to be overridden (i.e.
	options set on the commandline always override options set in the
	configuration file). 

	First, Config tries all configuration files in configFiles. The last one
	that can be read will be used. After reading that file, it will check for
	unspecified but required options and fill them in from defaults. Then the
	options are overridden using configOverrides.  Last comes the verification
	of config options to see if everything is valid.
	"""
	
	def __init__(self, configFiles, configOverrides):

		self.dataq = {}
		self.queuePool = {}
		self.queuePool["access"] = []

		self.queues = []

		# Find the first valid configuration file and use it.
		finalConfigFile = self.findConfigFile(configFiles)
		if not finalConfigFile:
			raise ConfigError, 001 # No usable config file found

		# Read information from the configuration file
		self.readConfigFile(finalConfigFile)

		# Fill in anything left out in the configuration file
		self.applyDefaults()

		# Apply all manual overrides from, for instance, the commandline
		self.override(configOverrides)

		# Verify the resulting configuration values
		self.verify()

	def findConfigFile(self, configFiles):
		retFinalConfigFile = None

		for configFile in configFiles:
			Log.verboseMsg("Trying config " + configFile);
			try:
				f = open(configFile, 'r')
				f.close()
				retFinalConfigFile = configFile
			except IOError:
				pass
	
		if not retFinalConfigFile:
			raise ConfigError, 001 # No usable config file found

		Log.verboseMsg("Using config " + retFinalConfigFile);
		return(retFinalConfigFile)

	def readConfigFile(self, configFile):
		try:
			document = Sax.Reader().fromStream(open(configFile,'r'))
		except Exception, e:
			raise ConfigError, 002 # Syntax error

		# <dataq>
		dataqNodes = xpath.Evaluate('dataq', document)
		for dataqNode in dataqNodes:
			
			for attribute in dataqNode.attributes:
				if attribute.nodeName == "port":
					self.dataq["port"] = int(attribute.nodeValue)
				if attribute.nodeName == "daemon":
					self.dataq["daemon"] = str2bool(attribute.nodeValue)

			# <pidfile>
			pidFileNodes = xpath.Evaluate('pidfile', dataqNode)
			for pidFileNode in pidFileNodes:
				if pidFileNode.firstChild != None:
					self.dataq["pidFile"] = pidFileNode.firstChild.data

			# <spool>
			spoolNodes = xpath.Evaluate('spool', dataqNode)
			for spoolNode in spoolNodes:

				# <event>
				eventNodes = xpath.Evaluate('event', spoolNode)

				if len(eventNodes) > 0: 
					self.queuePool["spoolEvents"] = [] # Clear defaults

				for eventNode in eventNodes:
					if eventNode.firstChild != None:
						self.queuePool["spoolEvents"].append(eventNode.firstChild.data)

				# <spooldir>
				spoolDirNodes = xpath.Evaluate('spooldir', spoolNode)
				for spoolDirNode in spoolDirNodes:
					if spoolDirNode.firstChild != None:
						self.queuePool["spoolDir"] = str(spoolDirNode.firstChild.data)
				
			# <access>
			accessNodes = xpath.Evaluate('access', dataqNode)
			for accessNode in accessNodes:
				
				access = {}

				for attribute in accessNode.attributes:
					if attribute.nodeName == "sense":
						access["sense"] = attribute.nodeValue

				# <password>
				passwordNodes = xpath.Evaluate('password', accessNode)
				for passwordNode in passwordNodes:
					if passwordNode.firstChild != None:
						access["password"] = str(passwordNode.firstChild.data)

				# <username>
				usernameNodes = xpath.Evaluate('username', accessNode)
				for usernameNode in usernameNodes:
					if usernameNode.firstChild != None:
						access["username"] = str(usernameNode.firstChild.data)

				# <host>
				hostNodes = xpath.Evaluate('host', accessNode)
				for hostNode in hostNodes:
					if hostNode.firstChild != None:
						access["host"] = str(hostNode.firstChild.data)

				self.queuePool["access"].append(access)

			# <queue>
			queueNodes = xpath.Evaluate('queue', dataqNode)
			for queueNode in queueNodes:
				
				queue = {}
				queue["access"] = []

				#if not "name" in queue:
				#	raise ConfigError, 999 # Missing queue name

				for attribute in queueNode.attributes:
					if attribute.nodeName == "name":
						queue["name"] = str(attribute.nodeValue)
					if attribute.nodeName == "type":
						type = str(attribute.nodeValue)
						#if type != "fifo" and type != "filo":
						#	raise ConfigError, 999 # Wrong type for queue type
						queue["type"] = type
					if attribute.nodeName == "size": 
						queue["size"] = int(attribute.nodeValue)
					if attribute.nodeName == "overflow":
						overflow = str(attribute.nodeValue)
						#if overflow != "deny" and overflow != "pop":
						#	raise ConfigError, 999 # Wrong type for overflow
						queue["overflow"] = overflow

				# <access>
				accessNodes = xpath.Evaluate('access', queueNode)
				for accessNode in accessNodes:
					
					access = {}

					for attribute in accessNode.attributes:
						if attribute.nodeName == "sense":
							sense = str(attribute.nodeValue)
							#if sense != "allow" and sense != "deny":
							#	raise ConfigError, 999 # Wrong type for sense
							access["sense"] = str(attribute.nodeValue)

					# <password>
					passwordNodes = xpath.Evaluate('password', accessNode)
					for passwordNode in passwordNodes:
						if passwordNode.firstChild != None:
							access["password"] = str(passwordNode.firstChild.data)

					# <username>
					usernameNodes = xpath.Evaluate('username', accessNode)
					for usernameNode in usernameNodes:
						if usernameNode.firstChild != None:
							access["username"] = str(usernameNode.firstChild.data)

					# <host>
					hostNodes = xpath.Evaluate('host', accessNode)
					for hostNode in hostNodes:
						if hostNode.firstChild != None:
							access["host"] = str(hostNode.firstChild.data)

					queue["access"].append(access)

				self.queues.append(queue)

	def applyDefaults(self):
		# <dataq>
		if not "address" in self.dataq:
			self.dataq["address"] = ""
		if not "port" in self.dataq:
			self.dataq["port"] = 50000
		if not "daemon" in self.dataq:
			self.dataq["daemon"] = False

		# <pidfile>
		if not "pidFile" in self.dataq:
			self.dataq["pidFile"] = "/var/run/dataq.pid"

		# <spooldir>
		if not "spoolDir" in self.queuePool:
			self.queuePool["spoolDir"] = "/var/spool/dataq/"

		# <spoolevents>
		if not "spoolEvents" in self.queuePool:
			self.queuePool["spoolEvents"] = []

		# <access>
		for access in self.queuePool["access"]:
			if not "sense" in access:
				access["sense"] = "allow"
			if not "username" in access:
				access["username"] = ""
			if not "password" in access:
				access["password"] = ""
			if not "host" in access:
				access["host"] = ""

		# <queue>
		for queue in self.queues:

			if not "type" in queue:
				queue["type"] = "fifo"
			if not "size" in queue:
				queue["size"] = 10
			if not "overflow" in queue:
				queue["overflow"] = "deny"
				
			# <access>
			for access in queue["access"]:
				if not "sense" in access:
					access["sense"] = "allow"
				if not "username" in access:
					access["username"] = ""
				if not "password" in access:
					access["password"] = ""
				if not "host" in access:
					access["host"] = ""

	def override(self, configOverrides):
		for key in configOverrides:
			if key == "address":
				self.dataq["address"] = configOverrides[key]
			if key == "port":
				self.dataq["port"] = configOverrides[key]
			if key == "daemon":
				self.dataq["daemon"] = configOverrides[key]
		
	def verify(self):
		for spoolEvent in self.queuePool["spoolEvents"]:
			if spoolEvent != "write" and spoolEvent != "shutdown":
				raise ConfigError, 301 # Wrong value for spool event

		for access in self.queuePool["access"]:
			if access["sense"] != "allow" and access["sense"] != "deny":
				raise ConfigError, 102 # Wrong value for sense

		for queue in self.queues:
			if not "name" in queue:
				raise ConfigError, 204 # Queue name required
			for access in queue["access"]:
				if access["sense"] != "allow" and access["sense"] != "deny":
					raise ConfigError, 102 # Wrong value for sense


def handler(signum, frame):
	global config, daemon, queuePool
	
	Log.verboseMsg("Received signal %i: Shutting down." % signum)

	if config.dataq["daemon"]:
		daemon.cleanup()

	for spoolEvent in queuePool.spoolEvents:
		if spoolEvent == "shutdown":
			queuePool.writeSpool()

	sys.exit(0)

if __name__ == "__main__":
	global verbose
	global optlist 

	try:
		params, args = getopt.getopt(sys.argv[1:], 'a:p:c:vVd')
	except getopt.error, errMsg:
		print errMsg
		print __doc__
		print 'usage : %s %s' % (sys.argv[0], usageStr)
		sys.exit(-1)    

	verbose = False

	configFiles = ["/etc/dataq.xml", "dataq.xml"]
	configOverrides = {}

	for a in params:
		if a[0] == "-c":
			# Only try configuration file on commandline
			configFiles = [a[1]] 

		if a[0] == "-a":
			configOverrides["address"] = a[1]
		if a[0] == "-p":
			configOverrides["port"] = int(a[1])
		if a[0] == "-d":
			configOverrides["daemon"] = True

		if a[0] == "-V":
			verbose = True
		if a[0] == "-v":
			print "msgserv v0.3. (C) 2005, Ferry Boender"
			sys.exit(0)

	try:
		config = Config(configFiles, configOverrides)
	except IOError:
		print "No config file found.. Aborting."
		sys.exit(-3)
	except ConfigError, e:
		print "Error in configuration:", e.getMessage()
		sys.exit(-3)


	# Try to create the spool directory
	try:
		if not os.access(config.queuePool["spoolDir"], os.F_OK):
			os.makedirs(config.queuePool["spoolDir"])
	except OSError, e:
		print "Couldn't create spool directory."
		sys.exit(-6);

	# Create queue pool
	queuePool = QueuePool(config.queuePool["spoolDir"], config.queuePool["spoolEvents"])

	for access in config.queuePool["access"]:
		queuePoolAccess = Access(access["sense"], access["password"], access["username"], \
			access["host"])
		queuePool.addAccess(queuePoolAccess)

	# Create queues
	for queue in config.queues:

		newQueue = queuePool.createQueue(queue["name"], queue["type"], queue["size"], queue["overflow"])

		for access in queue["access"]:
			queueAccess = Access(access["sense"], access["password"], access["username"], \
				access["host"])
			newQueue.addAccess(queueAccess)
		
	Log.verboseMsg("Starting server on address " + config.dataq["address"] + ":" + str(config.dataq["port"]))

	# Daemonize process
	if config.dataq["daemon"]:
		Log.verboseMsg("Running in daemon mode... Detaching from terminal.")
		try:
			daemon = Daemon(config.dataq["pidFile"])
		except DaemonError, e:
			print "Couldn't start the daemon process: " + e.getMessage()
			if e.getValue() == 101:
				print "If it's not, remove the PID file " + config.dataq["pidFile"]
			sys.exit(-5)

	# Start catching signals
	for s in [signal.SIGABRT, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM]:
		signal.signal(s, handler)

	# Start server
	try:
		server = Server((config.dataq["address"], config.dataq["port"]), RequestHandler)
		server.serve_forever()
	except socket.error, (errNr, errMsg):
		Log.verboseErr("Socket already in use. Aborting...");
		if config.dataq["daemon"]:
			daemon.cleanup()
		sys.exit(-2)

