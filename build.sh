#!/bin/bash

cd $(dirname $0)/src

echo building 'msaview._renderers' extension
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -I/usr/include/python2.6 -c msaview/renderers.cpp -o msaview/renderers.o -O3
g++ -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions msaview/renderers.o -o msaview/_renderers.so -Wl,-O3
echo building 'msaview_plugin_cscore._cscore' extension
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -Imsaview_plugin_substitution_matrix -I/usr/include/python2.6 -c msaview_plugin_cscore/cscore.cpp -o msaview_plugin_cscore/cscore.o -O3
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -Imsaview_plugin_substitution_matrix -I/usr/include/python2.6 -c msaview_plugin_substitution_matrix/substitution_matrix.cpp -o msaview_plugin_substitution_matrix/substitution_matrix.o -O3
g++ -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions msaview_plugin_cscore/cscore.o msaview_plugin_substitution_matrix/substitution_matrix.o -o msaview_plugin_cscore/_cscore.so -Wl,-O3
echo building 'msaview_plugin_substitution_matrix._substitution_matrix' extension
swig -python -c++ -o msaview_plugin_substitution_matrix/substitution_matrix_wrap.cpp msaview_plugin_substitution_matrix/substitution_matrix.i
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -I/usr/include/python2.6 -c msaview_plugin_substitution_matrix/substitution_matrix_wrap.cpp -o msaview_plugin_substitution_matrix/substitution_matrix_wrap.o -O3
gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -fPIC -I/usr/include/python2.6 -c msaview_plugin_substitution_matrix/substitution_matrix.cpp -o msaview_plugin_substitution_matrix/substitution_matrix.o -O3
g++ -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions msaview_plugin_substitution_matrix/substitution_matrix_wrap.o msaview_plugin_substitution_matrix/substitution_matrix.o -o msaview_plugin_substitution_matrix/_substitution_matrix.so -Wl,-O3

