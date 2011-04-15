"""MSAView - Substitution matrix support.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. 

This package provides basic support for substitution matrixes, and is 
provided by convenience. The underlying C++ code is heavily used by the 
cscore plugin extension module, and a python interface is made available 
here simply for the sake of consistency if other people want to do stuff
with substitution matrixes. 
 
If you have problems with this package, please contact the author.

Copyright
=========
 
The MIT License

Copyright (c) 2011 Joel Hedlund.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

__version__ = "0.9.0"

# The substitution_matrix class is the only useful thing from the wrapper python module
from substitution_matrix import SubstitutionMatrix

# Provide builtin matrix enum (it is continuous) as a sorted list matrixes = [NAMES]
matrixes = [name.lstrip('_') for name in dir(SubstitutionMatrix) if name.startswith('_') and not name.startswith('__')]
matrixes.sort(key=lambda name: getattr(SubstitutionMatrix, '_' + name))
# Also provide them as module level constants, as MATRIX_* (e.g: MATRIX_BLOSUM62...)
for name in matrixes:
    locals()['MATRIX_' + name] = getattr(SubstitutionMatrix, '_' + name)

# Helper if you want to work with strings instead.
def get_matrix(name):
    try:
        matrix = matrixes.index(name.upper())
    except:
        raise ValueError('not a builtin matrix name')
    return SubstitutionMatrix(matrix)

