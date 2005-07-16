<?php
#
# Copyright (C), 2005 Ferry Boender. Released under the General Public License
# For more information, see the COPYING file supplied with this program.                                                          
#
error_reporting(E_ALL);

// Todo:
//   * Set timeout on socket
//   * Cleanup
//   * Authentication
//   * stuff.

class Dataq {

	public $address;
	public $port;

	public function __construct($address = "", $port = 0) {

		if ($address === "") {
			$address = "127.0.0.1";
		}

		if ($port === 0) {
			$port = 50000;
		}

		$this->address = $address;
		$this->port = $port;

		// Try the connection to see if the DataQ server is there.
		$fp = @fsockopen($this->address, $this->port, $errno, $errstr, 30);
		if (!$fp) {
			throw new DataqException("Couldn't open a connection to the DataQ server.", 2);
		}

		fclose($fp);
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
			throw new DataqException("Couldn't open a connection to the DataQ server.", 2);
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

		$response = $this->doRequest("STAT");
		array_pop($response); // Remove last newline

		foreach($response as $queue) {
			$temp = explode(":", $queue, 2);
			$retQueues[] = $temp[1];
		}

		return($retQueues);
	}

	public function getQueueInfo($queueName) {
		$retQueueInfo = array();

		$response = $this->doRequest("STAT ".$queueName);
		array_pop($response); // Remove last newline.

		foreach($response as $queueInfo) {
			$temp = explode(":", $queueInfo, 2);
			$retQueueInfo[$temp[0]] = $temp[1];
		}

		return($retQueueInfo);
	}

	public function push($queueName, $message) {
		$response = $this->doRequest("PUSH ".$queueName. " ".$message);
	}

	public function pop($queueName) {
		$response = $this->doRequest("POP ".$queueName);

		return($response[0]);
	}

	public function clear($queueName) {
		$response = $this->doRequest("CLEAR ".$queueName);
	}
}

class DataqException extends Exception {

}

?>
