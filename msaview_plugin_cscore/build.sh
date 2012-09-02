#!/bin/bash
cd $(dirname $0)

gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O3 -Wall -fPIC -I../msaview_plugin_substitution_matrix -I/usr/include/python2.6 -c cscore.cpp -o cscore.o
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O3 -Wall -fPIC -I../msaview_plugin_substitution_matrix -I/usr/include/python2.6 -c ../msaview_plugin_substitution_matrix/substitution_matrix.cpp -o substitution_matrix.o
g++ -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions cscore.o substitution_matrix.o -o _cscore.so

