DataQ
=====

Introduction
------------

DataQ is a simple data and message queuing server which uses a simple
plain-text protocol. It is therefor very easy to implement clients for. The
server is multi-threaded and implements FIFO (First In, First Out) and FILO
(First In, Last Out) queues, has queue size restrictions and overflow
handling.

In the future authentication will be implemented on an IP/Username/Password
basis. For now the server only understands single-line plain-text messages,
but binary queue data will also be supported.

*NOTICE*: This is a work in progress. Please check out doc/TODO for things
that are buggy.


Installation
------------

1.   Copy config/dataq.xml.example to /etc/dataq.xml and modify (see 
	 Configuration)
2.   Copy src/dataq.py to /usr/local/sbin


Configuration
-------------

dataq searches for a configuration file:

    /etc/dataq.xml
    ./dataq.xml

and, if the -c flag is specified, for the file specified as a parameter to
the -c flag.

An example configuration file can be found in the config/ directory. It
contains descriptions of the available configuration directives.

### Queue Definitions

For information on how to define queues and all the possibilities for
queues, please see the config/dataq.xml.example file.

### Access Control

Access Control works on a global Server level (all queues) and on
individual queues.

Each access block is in the form of:

    <access [sense='...']>
        [<host>IP[/NETMASK]</host>]
        [<username>USERNAME</username>]
        [<password>PASSWORD</password>]
    </access>
		
Where everything between brackets ( '[' and ']' ) is optional.

By placing these blocks inside the <dataq></dataq> and <queue></queue>
blocks, one will eventually end up with two states after access has been
checked for a connection:

*   Server Access
*   Queue Access

Both can have three states:

    Deny
    Allow
    Unspecified

When the Queue Access state is unspecified (Not explicitly allowed or
denied), then DataQ will look at the Server Access. If this is Deny or
Unspecified, access to the queue will be denied.

Access is checked on a first-match basis. The first <Access> block that
explicitly denies or allows a user will be authoritative. This is seperate
for Server Access and Queue Access. (i.e. Queue Access can override Server
Access).

So, for example, user 'john' at 127.0.0.1, with password 'johnspw', will be
matched by:

    <access sense='deny'>
        <host>127.0.0.1</host>
    </access>

and

    <access sense='deny'>
        <username>john</username>
    </access>

but not by:

    <access sense='deny'>
        <host>127.0.0.1</host>
        <username>pete</username>
    </access>

Pretty obvious, I'd say.


### Running

Usage:

	usage : ./dataq.py [-v] [-V] [-c path] [-a address] [-p port]

	  -c Configuration file to use
	  -a IP address to listen on. (overrides config) Default: All IPs
	  -p Port to listen on. (overrides config) Default: 50000.
	  -d Run in daemon mode (detach from terminal)
	  -V Verbose mode. Lots-o-output.
	  -v Print version information

	
Stopping the daemon:

    kill `cat /var/run/dataq.pid`

License
-------

Copyright (C) 2005, Ferry Boender <f DOT boender AT electricmonk DOT nl>
Licensed under the General Public License (GPL), see COPYING file 
provided with this program.

Contributions from: 

*   Michiel van Baak - Testing, idea's and PHP client patches.

Client libraries (src/client/) are licensed under the Lesser General Public
License (LGPL), see src/client/COPYING file.

