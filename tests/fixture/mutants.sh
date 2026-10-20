#!/usr/bin/env bash
# A stand-in for a mutation run: prints the table a mutation run prints and leaves a marker in
# its working directory, which the test uses to check the run happened in a scratch copy.
touch .mutated
printf '| row | file | result |\n| --- | --- | --- |\n'
printf '| alpha is checked | a.ts | caught: selected: a.test.ts |\n'
printf '| beta is checked | b.ts | NOT CAUGHT: no test failed |\n'
printf '| gamma is checked | c.ts | retired: removed |\n'
