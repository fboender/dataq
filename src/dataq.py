#!/usr/bin/python
#
# Copyright (C), 2005 Ferry Boender. Released under the General Public License
# For more information, see the COPYING file supplied with this program.                                                          
#

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
#  1 Incorrect usage
#  2 Fatal system resource problem
#  3 Configuration file problem
#  4 Import error; missing python package

import sys
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
	sys.exit(4);

def str2bool(string):
	retBool = None
	
	if string.lower() == "true":
		retBool = True
	else:
		retBool = False

	return(retBool)
		
class DataqError(Exception):

	""" 
		Generic DataQ Error exception 
	"""

	messages = {
		001: "Error in config",

		101: "Bad syntax in request",
		102: "Unknown request type",

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

class Log:

	""" 
		Console, verbose and system log logger 
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
		information for a single host/user/password.
	"""

	sense = "allow"
	password = ""
	username = ""
	host = ""

	def __init__(self, sense = "allow", password = "", username = "", host = ""):
		# FIXME: Throw errors when wrong types. Use self.set*
		self.sense = sense
		self.password = password
		self.username = username
		self.host = host

	def setSense(self, sense):
		self.sense = sense

	def setQueue(self, queue):
		self.queue = queue

	def setPassword(self, password):
		self.password = password

	def setUsername(self, username):
		self.username = username

	def setHostname(self, hostname):
		self.hostname = hostname

class Queue:

	""" 
		Base queue class that handles generic actions on queues. Derive new 
		queue types (FILO, FIFO, etc) from this class
	"""

	name = ""
	type = ""
	size = 0
	overflow = ""

	def __init__(self, name, type, size, overflow):
		self.name = name
		self.type = type
		self.size = size
		self.overflow = overflow

		Log.verboseMsg("Registered new queue '" + self.name + "' (type:" + self.type + ", size: " + str(self.size) + ", overflow: " + self.overflow + ")")

	def __len__(self):
		return(len(self.queue))

	def push(self, message):
		retResponse = ""
		
		Log.verboseMsg("Pushing to " + self.name + ": " + message)

		if len(self.queue) == self.size:
			if self.overflow == "pop":
				self.pop()
			elif self.overflow == "deny":
				raise DataqError, 203 # Queue is full
				
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

#	def hasAccess(self, password, username, host):
#		retAccess = None
#
#		for access in self.accessList:
#
#			if access.password == password and access.username == username:
#				if (access.host != "" and access.host == host) or (access.host == ""):
#					if access.sense == "allow":
#						retAccess = True
#					else:
#						retAccess = False
#			
#		return(retAccess)

	def hasAccess(self, password, username, host):

		for access in self.accessList:

			print "access.queuename= ", access.queuename
			print "access.sense    = ", access.sense
			print "access.host     = ", access.host
			print "access.username = ", access.username
			print "access.password = ", access.password
			print

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

		
class FifoQueue(Queue):

	"""
		FIFO Queue: First message in is the first message out. (Queue)
	"""
		
	queue = []

	def __init__(self, name, size, overflow):
		self.accessList = []
		Queue.__init__(self, name, "fifo", size, overflow)

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

	queue = []

	def __init__(self, name, size, overflow):
		self.accessList = []
		Queue.__init__(self, name, "filo", size, overflow)

	def pop(self):
		retResponse = ""

		Log.verboseMsg("POPing from " + self.name)

		if len(self.queue) > 0:
			retResponse = self.queue.pop()

		return(retResponse)

class QueuePool:
	
	"""
		Intermediary class between queues and the server's request handler.
		This class takes care of creation, communication and access checking
		for queues.
	"""

	queues = {}

	def __init__(self):
		self.accessList = []
	
	def createQueue(self, name, type, size, overflow):
		if type == "fifo":
			newQueue = FifoQueue(name, size, overflow)
		elif type == "filo":
			newQueue = FiloQueue(name, size, overflow)
		else:
			# FIXME: This raises a DataqError, but it's actually
			# an error in the configuration file. This should
			# probably raise something like ConfigError
			raise DataqError, 001

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
		
class RequestHandler(SocketServer.BaseRequestHandler):

	"""
		Handle a single incomming connection by reading a request, processing 
		it, delegating it to the queuePool and then transmitting the resulting
		data (error, popped message, etc).
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
	
	def __init__(self):

		try: 
			pid = os.fork() 
			if pid > 0:
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
				Log.verboseMsg("PID: " + str(pid))
				sys.exit(0) 
		except OSError, e: 
			print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror) 
			sys.exit(-2) 

class Config:

	"""
		DataQ XML Configuration reader.
	"""
	
	def __init__(self, configfiles, configOverrides):

		finalConfigFile = None

		for configFile in configFiles:
			try:
				f = open(configFile, 'r')
				f.close()
				finalConfigFile = configFile
			except IOError:
				pass
	
		if finalConfigFile:
			document = Sax.Reader().fromStream(open(finalConfigFile,'r'))
			
			dataqNodes = xpath.Evaluate('dataq', document)

			for dataqNode in dataqNodes:
				self.handleDataqNode(dataqNode)

			# FIXME: Free the Sax reader??
		else:
			raise IOError

		for configOverride in configOverrides:
			setattr(self, configOverride, configOverrides[configOverride])

	def handleDataqNode(self, node):
		global queuePool # FIXME: Globals are ugly.

		self.address = ""
		self.port = 50000
		self.verbose = False
		self.daemon = False

		for attribute in node.attributes:
			if attribute.nodeName == "address":
				self.address = str(attribute.nodeValue)
			if attribute.nodeName == "port":
				self.port = int(attribute.nodeValue)
			if attribute.nodeName == "verbose":
				self.verbose = str2bool(attribute.nodeValue)
			if attribute.nodeName == "daemon":
				self.daemon = str2bool(attribute.nodeValue)
			
		queuePool = QueuePool()

		accessNodes = xpath.Evaluate('access', node)
		for accessNode in accessNodes:
			self.handleAccessNode(accessNode, queuePool)

		queueNodes = xpath.Evaluate('queue', node)
		for queueNode in queueNodes:
			self.handleQueueNode(queueNode, queuePool)

	def handleQueueNode(self, node, queuePool):

		name = ""
		type = "fifo"
		size = 10
		overflow = "pop"

		for attribute in node.attributes:
			if attribute.nodeName == "name":
				name = attribute.nodeValue
			if attribute.nodeName == "type":
				type = attribute.nodeValue
			if attribute.nodeName == "size": 
				size = int(attribute.nodeValue)
			if attribute.nodeName == "overflow":
				overflow = attribute.nodeValue

		queue = queuePool.createQueue(name, type, size, overflow)

		accessNodes = xpath.Evaluate('access', node)
		for accessNode in accessNodes:
			self.handleAccessNode(accessNode, queuePool, queue)

	def handleAccessNode(self, node, queuePool, queue = None):

		sense = "allow"
		password = ""
		username = ""
		host = ""

		for attribute in node.attributes:
			if attribute.nodeName == "sense":
				sense = attribute.nodeValue

		passwordText = xpath.Evaluate('password/child::text()', node)
		if len(passwordText) > 0:
			password = passwordText[0].data

		usernameText = xpath.Evaluate('username/child::text()', node)
		if len(usernameText) > 0:
			username = usernameText[0].data

		hostText = xpath.Evaluate('host/child::text()', node)
		if len(hostText) > 0:
			host = hostText[0].data
			
		access = Access(sense, password, username, host)
		if queue != None:
			
			queue.addAccess(access)
		else:
			if queuePool != None:
				queuePool.addAccess(access)
			else:
				# FIXME: Raise error
				pass

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
			configFiles.append(a[1])

		if a[0] == "-a":
			configOverrides["address"] = a[1]
		if a[0] == "-p":
			configOverrides["port"] = int(a[1])
		if a[0] == "-d":
			configOverrides["daemon"] = True

		if a[0] == "-V":
			verbose = True
		if a[0] == "-v":
			print "msgserv v0.2. (C) 2005, Ferry Boender"
			sys.exit(0)

	try:
		config = Config(configFiles, configOverrides)
	except IOError:
		print "No config file found.. Aborting."
		sys.exit(-3)

	Log.verboseMsg("Starting server on address " + config.address + ":" + str(config.port))

	if config.daemon:
		Log.verboseMsg("Running in daemon mode... Detaching from terminal.")
		Daemon()

	try:
		server = Server((config.address, config.port), RequestHandler)
		server.serve_forever()
	except KeyboardInterrupt, e:
		sys.exit(0)
	except socket.error, (errNr, errMsg):
		Log.verboseErr("Socket already in use. Aborting...");
		sys.exit(-2)

