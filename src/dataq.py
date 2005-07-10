#!/usr/bin/python

"""
DataQ: A simple message/data queueing server.
"""

usageStr =\
	"""[-v] [-V] [-a address] [-p port]

  -c Configuration file to use
  -a IP address to listen on. (overrides config) Default: All IPs
  -p Port to listen on. (overrides config) Default: 50000.
  -d Run in daemon mode (detach from terminal)
  -V Verbose mode. Lots-o-output.
  -v Print version information
"""

import sys
import getopt
import os 
import SocketServer
import socket
import select
from xml.parsers.xmlproc import xmlproc
from xml.parsers.xmlproc import xmlval
from xml.parsers.xmlproc import xmldtd

class QueueError(Exception):
	messages = {
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

	def verbose(type, msg):
		global verbose

		#if verbose:
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
	

class Queue:

	name = ""
	type = ""
	size = 0
	overflow = ""

	queue = []

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
		self.queue.append(message)

		return(retResponse)
				
class FifoQueue(Queue):

	def __init__(self, name, size, overflow):
		Queue.__init__(self, name, "fifo", size, overflow)

	def pop(self, password=None):
		retResponse = ""

		if len(self.queue) > 0:
			retResponse = self.queue.pop(0)

		return(retResponse)

class FiloQueue(Queue):

	def __init__(self, name, size, overflow):
		Queue.__init__(self, name, "filo", size, overflow)

	def pop(self, password=None):
		retResponse = ""

		if len(self.queue) > 0:
			retResponse = self.queue.pop()

		return(retResponse)

class Message:

	def __init__(self, type, publishDate):

		self.type = type
		self.publishDate = publishDate
		
class QueuePool:

	queues = {}

	def __init__(self):
		pass
	
	def createQueue(self, name, type, size, overflow):
		if type == "fifo":
			newQueue = FifoQueue(name, size, overflow)
		if type == "filo":
			newQueue = FiloQueue(name, size, overflow)

		self.queues[name] = newQueue

	def push(self, queueURI, message):
		retResponse = None
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise QueueError, 201 # Unknown queue

		queue = self.queues[queueName]
		retResponse = queue.push(message)

		return(retResponse)

	def pop(self, queueURI):
		retResponse = None
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise QueueError, 201 # Unknown queue

		queue = self.queues[queueName]
		retResponse = queue.pop()

		return(retResponse)

	def stat(self, queueURI):
		retResponse = None
		queue = None
		username, password, queueName = self.parseQueueURI(queueURI)
		
		if queueName not in self.queues:
			raise QueueError, 201 # Unknown queue

		queue = self.queues[queueName]

		retResponse += "name:" + queue.getName()+"\n"
		retResponse += "type:" + queue.getType()+"\n"

		return(retResponse)

	def parseQueueURI(self, queueURI):
		username = ""
		password = ""
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
						except QueueError, e:
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
			raise QueueError, 102 # Unknown request type

		return retResponse
	
	def processPush(self, data):
		global queuePool
		
		retResponse = ""
		
		try:
			queueURI, data = data.split(" ", 1)
			retResponse = queuePool.push(queueURI, data)
		except ValueError:
			raise QueueError, 101 # Bad syntax in request

		return retResponse

	def processPop(self, data):
		global queuePool
		
		retResponse = ""
		
		try:
			queueURI = data
			retResponse = queuePool.pop(queueURI)
		except ValueError:
			raise QueueError, 101 # Bad syntax in request

		return retResponse

	def processStat(self, data):
		print "STAT: ", data

	def processClear(self, data):
		print "CLEAR: ", data

class Server(SocketServer.ThreadingMixIn, SocketServer.TCPServer):

	daemon_threads = True
	allow_reuse_address = True

	def __init__(self, server_address, RequestHandlerClass):
		SocketServer.TCPServer.__init__(self, server_address, RequestHandlerClass)

class Daemon:
	def __init__(self):

		try: 
			pid = os.fork() 
			if pid > 0:
				sys.exit(0) 
		except OSError, e: 
			print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror) 
			sys.exit(1)

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
			sys.exit(1) 

class ConfigParser(xmlproc.Application):

	def handle_start_tag(self,name,attrs):
		if (name == "dataq"):
			self.handle_dataq_tag(attrs)
		if (name == "queue"):
			self.handle_queue_tag(attrs)

	def handle_end_tag(self,name):
		pass

	def handle_data(self,data,start,end):
		pass

	def handle_dataq_tag(self, attrs):
		global queuePool

		self.config.address = attrs.get("address", "")
		self.config.port = int(attrs.get("port", "50000"))
		self.config.verbose = bool(attrs.get("verbose", False))
		self.config.daemon = bool(attrs.get("daemon", False))

		queuePool = QueuePool()

	def handle_queue_tag(self, attrs):
		global queuePool

		name = attrs["name"]
		type = attrs.get("type", "fifo")
		size = int(attrs.get("size", "10"))
		overflow = attrs.get("overflow", "deny")

		queuePool.createQueue(name, type, size, overflow)

class Config:
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
			configParser = ConfigParser()
			configParser.config = self
			parser = xmlproc.XMLProcessor()
			parser.set_application(configParser)
			parser.parse_resource(finalConfigFile)
		else:
			raise IOError

		for configOverride in configOverrides:
			setattr(self, configOverride, configOverrides[configOverride])

if __name__ == "__main__":
	global optlist 
	global config

	try:
		params, args = getopt.getopt(sys.argv[1:], 'a:p:c:vVd')
	except getopt.error, errMsg:
		print errMsg
		print __doc__
		print 'usage : %s %s' % (sys.argv[0], usageStr)
		sys.exit(-1)    

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
			configOverrides["verbose"] = True

		if a[0] == "-v":
			print "msgserv v0.1. (C) 2005, Ferry Boender"
			sys.exit(0)

	try:
		config = Config(configFiles, configOverrides)
	except IOError:
		print "No config file found.. Aborting."
		sys.exit(-1)

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
		sys.exit(-1)
