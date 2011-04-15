"""Basic support for substitution matrixes. 

Provided by convenience. The underlying C++ code is heavily used by the 
cscore plugin extension module, and a python interface is made available 
here simply for the sake of consistency if other people want to do stuff
with substitution matrixes. 

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

