%module substitution_matrix
%{
/* Includes the header in the wrapper code */
#include "substitution_matrix.h"
%}

/* Parse the header file to generate wrappers */
%include "substitution_matrix.h"
