import os

try:
    import psyco
    psyco.full()
except:
    pass

import numpy

from numpy import add, array, concatenate, sqrt, subtract, swapaxes
from numpy.linalg import norm

def row_distance(matrix):
    nMax = 0.0
    for i in range(matrix.shape[0] - 1):
        for j in range(i + 1, matrix.shape[0]):
            nMax = max(nMax, norm(matrix[i] - matrix[j]))
    return nMax

class ScoringMatrix(object):
    """A substitution scoring matrix.
    
    This class is basically a wrapper around a numpy array (.scores) but 
    also has a lot of (slower?) convenience functions if you aren't a speed
    devil. A few precomputed properties are also available and may be handy
    for casual users and for time critical applications.
    
    Data members:
    scores: <numpy.array>
        The actual scores. Operate on this for speed. Toy example: 
        [[24.0, 5.0], [5.0, 115.0]]
    residue_index: <dict str:int>
        Letter to column index dictionary. Toy example: {'A': 0, 'C': 1}
    max_distance: <float>
        The maximum distance between 2 residue types in the matrix.
    best_score: <float>
        The best score in the matrix.
    worst_score: <float>
        The worst score in the matrix.
        
    """
    def __init__(self, 
                 scores=None, 
                 residue_index=None, 
                 max_distance=None,
                 best_score=None,
                 worst_score=None):
        if scores is None:
            scores = numpy.array([])
        if residue_index is None:
            residue_index = {}
        if max_distance is None:
            if len(scores):
                max_distance = row_distance(scores)
        self.scores = scores
        self.residue_index = residue_index
        self.max_distance = max_distance
        self.best_score = best_score
        self.worst_score = worst_score
            
    def __contains__(self, residue):
        """Is the given residue described in the scoring matrix?"""
        return residue in self.residue_index

    def __getitem__(self, residues):
        """So you can write matrix['A', 'C']."""
        r1, r2 = residues
        return self.scores[r1][r2]
    
    def __len__(self):
        return self.scores.shape[0]
    
    def __str__(self):
        return self.to_str()
    
    @classmethod
    def from_fulltext(self, matrix_file):
        """Read a scoring matrix file.
        
        The format is as follows:
        Whitespace-only lines and lines starting with a # character are 
        ignored. The first non-ignored line should contain the residue 
        order. The following should contain whitespace separated float 
        literals which should form a square matrix of same length as the 
        residue order. This is compatible with the format of the matrix
        files in the ncbi blast package.
        
        IN:
        matrix_file <file>:
            The file to read. 
        
        OUT:
        A new ScoringMatrix instance. 
        
        """
        dsiResidueIndex = None
        laRows =[]
        for sLine in matrix_file:
            sStripped = sLine.strip()
            if not sStripped or sStripped.startswith('#'):
                continue
            if not dsiResidueIndex:
                dsiResidueIndex = dict((s, i) for i, s in enumerate(sLine.split()))
                continue
            laRows.append(array([[float(s) for s in sLine.split()[1:]]]))
        aMatrix = concatenate(laRows)
        return ScoringMatrix(aMatrix, dsiResidueIndex)

    def to_indices(self, residues):
        return [self.residue_index[s] for s in residues]

    def to_str(self, order=None, width=5, precision=1):
        """Return the matrix in a str format parsable by .from_fulltext().
        
        IN:
        order=None: <sequence str> or None
            The residue order in the output. None means use sorted order.
        width=4: <int>
            The field width wherin a matrix number should fit.
        precision=1: <int>
            The number of decimals presented.
            
        OUT:
        The matrix as a parsable str.
        
        """
        if order is None:
            order = self.residues()
            aScores = self.scores
        else:
            liOrder = self.to_indices(order)
            aScores = swapaxes(self.scores[liOrder], 0, 1)[liOrder]
        lsOut = [' ' * 2 + ' '.join('%*s' % (width, s) for s in order)]
        sFormat = "%%%d.%df" % (width, precision)
        for sAA, aRow in zip(order, aScores):
            lsOut.append(sAA + ' ' + ' '.join(sFormat % n for n in aRow))
        return '\n'.join(lsOut)
    
    def scale(self, factor):
        """Multiply all matrix elements by the given factor."""
        self.scores *= factor
    
    def offset(self, amount):
        """Add a constant to all matrix elements."""
        self.scores += amount

    def remove(self, residue):
        """Remove a residue from the matrix."""
        if residue not in self.residue_index:
            raise ValueError("no such residue")
        iResidue = self.to_indices(residue)[0]
        liIndices = range(self.scores.shape[0])
        del liIndices[iResidue]
        self.scores = swapaxes(self.scores[liIndices], 0, 1)[liIndices]
        self.residue_index.pop(residue)
    
    def score(self, residue1, residue2):
        """Return the score for substituting residue1 with residue2.
        
        This is identical to matrix[residue1, residue2].
        
        """
        return self[residue1, residue2]
    
    def eraseme_distance(self, residue1, residue2):
        """Return the distance between the score vectors for r1 and r2."""
        li = self.to_indices([residue1, residue2])
        return norm(self.scores[li[0]] - self.scores[li[1]])
    
    def residues(self):
        """Return the residues described by the matrix, in the matrix order."""
        return sorted(self.residue_index, key=lambda s: self.residue_index[s])
    
def _index_matrix_files():
    sMatrixDir = os.path.join(os.path.split(__file__)[0], 'matrices')
    sPath, lsDirs, lsFiles  = os.walk(sMatrixDir).next()
    dssMatrixFiles = {}
    for sFile in lsFiles :
        sName, sExt = os.path.splitext(sFile)
        if sExt != '.mat':
            continue
        dssMatrixFiles[sName] = os.path.join(sPath, sFile)
    return dssMatrixFiles

scoring_matrices = _index_matrix_files()

def get_matrix(name):
    """Read and return the corresponding matrix from the matrix dir."""
    f = open(scoring_matrices[name])
    dsdsnMatrix = ScoringMatrix.from_fulltext(f)
    f.close()
    return dsdsnMatrix

def distances(matrix):
    distances = []
    for i in range(matrix.shape[0] - 1):
        for j in range(i + 1, matrix.shape[0]):
            distances.append(norm(matrix[i] - matrix[j]))
    distances.sort()
    return distances
