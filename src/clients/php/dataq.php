<?php
// 
// dataq.php v0.3
//
// A client library for the DataQ message queueing server.
// (http://www.electricmonk.nl/index.php?page=DataQ
//
// Copyright (C), 2005 Ferry Boender. 
// Contributions from: Michiel van Baak
//
// Released under the Lesser General Public License (LGPL):
//  
// This library is free software; you can redistribute it and/or modify it
// under the terms of the GNU Lesser General Public License as published by the
// Free Software Foundation; either version 2.1 of the License, or (at your
// option) any later version.
// 
// This library is distributed in the hope that it will be useful, but WITHOUT
// ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
// FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
// for more details.
// 
// You should have received a copy of the GNU Lesser General Public License
// along with this library; if not, write to the Free Software Foundation,
// Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
//

error_reporting(E_ALL);

class Dataq {

	public $address;
	public $port;
	public $username;
	public $password;

	public function __construct($address = "", $port = 0, $username = "", 
		                        $password = "") {

		if ($address === "") {
			$address = "127.0.0.1";
		}

		if ($port === 0) {
			$port = 50000;
		}

		$this->address = $address;
		$this->port = $port;
		$this->username = $username;
		$this->password = $password;

		// Try the connection to see if the DataQ server is there.
		$fp = @fsockopen($this->address, $this->port, $errno, $errstr, 30);
		if (!$fp) {
			throw new DataqException(
				"Couldn't open a connection to the DataQ server.", 
				2);
		}

		fclose($fp);
	}

	private function buildQueueURI($queueName = "") {
		$queueURI = $queueName;

		if ($this->password != "") {
			$queueURI = $this->password."@".$queueURI;
		}
		if ($this->username != "") {
			$queueURI = $this->username.":".$queueURI;
		}

		return($queueURI);

	}
	
	private function doRequest($request) {
		$fp = NULL;
		$response = "";
		$retResponse = array();

		// Requests should always end in a newline so the server knows when
		// to respond.
		if ($request[strlen($request) - 1] != "\n") {
			$request .= "\n";
		}

		$fp = @fsockopen($this->address, $this->port, $errno, $errstr, 30);
		if (!$fp) {
			throw new DataqException(
				"Couldn't open a connection to the DataQ server.", 
				2);
		}

		fwrite($fp, $request);
		while(!feof($fp)) {
			$response .= fgets($fp, 128);
		}
		fclose($fp);

		if (substr($response, 0, 5) === "ERROR") {
			$errorInfo = explode(" ", $response, 3);

			throw new DataqException($errorInfo[2], $errorInfo[1]);
		}

		$retResponse = explode("\n", $response);

		return($retResponse);
	}

	public function getQueues() {
		$retQueues = array();

		$queueURI = $this->buildQueueURI();
		$response = $this->doRequest("STAT ".$queueURI);

		array_pop($response); // Remove last newline

		foreach($response as $queue) {
			$temp = explode(":", $queue, 2);
			$retQueues[] = $temp[1];
		}

		return($retQueues);
	}

	public function getQueueInfo($queueName) {
		$retQueueInfo = array();

		$queueURI = $this->buildQueueURI($queueName);
		$response = $this->doRequest("STAT ".$queueURI);

		array_pop($response); // Remove last newline.

		foreach($response as $queueInfo) {
			$temp = explode(":", $queueInfo, 2);
			$retQueueInfo[$temp[0]] = $temp[1];
		}

		return($retQueueInfo);
	}

	public function push($queueName, $message) {
		$queueURI = $this->buildQueueURI($queueName);
		$response = $this->doRequest("PUSH ".$queueURI." ".$message);
	}

	public function pop($queueName) {
		$queueURI = $this->buildQueueURI($queueName);
		$response = $this->doRequest("POP ".$queueURI);

		return($response[0]);
	}

	public function peek($queueName) {
		$queueURI = $this->buildQueueURI($queueName);
		$response = $this->doRequest("PEEK ".$queueURI);

		return($response[0]);
	}

	public function clear($queueName) {
		$queueURI = $this->buildQueueURI($queueName);
		$response = $this->doRequest("CLEAR ".$queueURI);
	}
}

class DataqException extends Exception {

}

?>
