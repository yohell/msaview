#!/bin/bash
swig -python -c++ -o substitution_matrix_wrap.cpp substitution_matrix.i
g++ -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -I/usr/include/python2.6 -c substitution_matrix_wrap.cpp -o substitution_matrix_wrap.o -O3
g++ -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -I/usr/include/python2.6 -c substitution_matrix.cpp -o substitution_matrix.o -O3
g++ -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions substitution_matrix_wrap.o substitution_matrix.o -o _substitution_matrix.so -O3

