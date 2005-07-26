#!/bin/sh

if [ "$1" != "" ]; then
	TESTS="$1"
else
	TESTS="test*"
fi

for TEST in `ls -1 -d $TESTS| grep -v 'test.sh'`; do
	echo -n "Running test in $TEST... "
	../src/dataq.py -dV -c $TEST/dataq.xml > dataq.out
	
	if [ "$?" -ne 0 ]; then
		echo "DataQ server returned an error. Please check that is correctly working. Aborting the testrun."
		exit
	fi
		

	TEMP=`grep 'PID:' dataq.out`
	PID=`echo $TEMP | cut -d':' -f2`

	cat $TEST/in | while read; 
		do echo $REPLY | netcat localhost 49999 >> test.out; 
	done

	kill $PID

	echo "" >> test.out # Append a newline

	LINES=`diff test.out $TEST/out | wc -l`
	if [ $LINES -gt 0 ]; then
		echo "Failed. (See $TEST/failed.log for information)"
		
		echo "INPUT" > $TEST/failed.log
		echo "--------------------------------------------------------------------------" >> $TEST/failed.log
		cat $TEST/in >> $TEST/failed.log
		echo "EXPECTED CLIENT OUTPUT" >> $TEST/failed.log
		echo "--------------------------------------------------------------------------" >> $TEST/failed.log
		cat $TEST/out >> $TEST/failed.log
		echo "ACTUAL CLIENT OUTPUT" >> $TEST/failed.log
		echo "--------------------------------------------------------------------------" >> $TEST/failed.log
		cat test.out >> $TEST/failed.log
		echo "SERVER OUTPUT LOG" >> $TEST/failed.log
		echo "--------------------------------------------------------------------------" >> $TEST/failed.log
		cat dataq.out >> $TEST/failed.log

	else
		echo "Passed."
		if [ -e $TEST/failed.log ]; then
			rm $TEST/failed.log
		fi
	fi
	
	rm test.out
	rm dataq.out
done

# Wait for dataq servers to exit
sleep 2
