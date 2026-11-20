# T6: long-running benchmark (used to test stopping)
Run this exact command in the foreground and wait for it: `bash -c 'for i in $(seq 1 60); do echo tick $i; sleep 10; done'`.
Then write the number of ticks you saw into `.hsa-tmp/ticks.txt` and report. Do not edit anything else.
