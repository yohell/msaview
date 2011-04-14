#include <Python.h>
#include <numpy/arrayobject.h>
#include <iostream>

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

#include "substitution_matrix.h"

// Never mind the python exception. I don't have the patience.
//static PyObject *CScoreError;

void print_array(const double * arr, const int size)
{
	for (int i = 0; i < size; ++i)
		std::cout << arr[i] << ' ';
	std::cout << std::endl;
}

void printf_array(const double * arr, const int size)
{
	for (int i = 0; i < size; ++i)
		printf("%.5f ", arr[i]);
	std::cout << std::endl;
}

void printf_array_s(const short * arr, const int size)
{
	for (int i = 0; i < size; ++i)
		printf("%5d ", arr[i]);
	std::cout << std::endl;
}

void printf_array_i(const int * arr, const int size)
{
	for (int i = 0; i < size; ++i)
		printf("%5d ", arr[i]);
	std::cout << std::endl;
}

class ScoringMatrix
{
public:
	ScoringMatrix(const substitution_matrix & m)
	{
		symbol_to_index = new char[256];
		memset(symbol_to_index, -1, 256);
		vector_size = m.get_alphabet_size();
		for (int i = 0; i < m.get_alphabet_size(); ++i)
		{
			if (m.get_alphabet()[i] == '*')
			{
				--vector_size;
				break;
			}
		}
		matrix = new substitution_matrix::matrix_type[vector_size * vector_size];
		symbols = new char[vector_size];
		for (int i = 0; i < vector_size; ++i)
		{
			symbols[i] = m.get_alphabet()[i];
			symbol_to_index[(unsigned char) symbols[i]] = i;
		}
		for (int i = 0; i < vector_size; ++i)
		{
			for (int j = 0; j < vector_size; ++j)
			{
				matrix[i * vector_size + j] = m.lookup(symbols[i], symbols[j]);
			}
		}
		halfmax_distance = 0;
		for (unsigned char i = 0; i < vector_size - 1; ++i)
		{
			for (unsigned char j = i + 1; j < vector_size; ++j)
			{
				// skipping diagonal elements, all are zero.
				halfmax_distance = std::max(halfmax_distance, distance(i, j));
			}
		}
		halfmax_distance /= 2;
	}

	~ScoringMatrix()
	{
		delete matrix; matrix = NULL;
		delete symbols; symbols = NULL;
		delete symbol_to_index; symbol_to_index = NULL;
	}

	bool has_symbol(const char symbol) const
	{
		return (get_index(symbol) != -1);
	}

	const char * get_symbols() const
	{
		return symbols;
	}

	const double distance(const substitution_matrix::matrix_type *vector1, const double *vector2) const
	{
		double d = 0;
		for (int i = 0; i < vector_size; ++i)
		{
			double delta = vector1[i] - vector2[i];
			d += delta * delta;
		}
		return sqrt(d);
	}

	const double distance(const substitution_matrix::matrix_type *vector1, const substitution_matrix::matrix_type *vector2) const
	{
		int d = 0;
		for (int i = 0; i < vector_size; ++i)
		{
			int delta = vector1[i] - vector2[i];
			d += delta * delta;
		}
		return sqrt(d);
	}

	const double distance(const int index1, const int index2) const
	{
		return distance(get_score_vector(index1), get_score_vector(index2));
	}

	inline const int get_index(const char symbol) const
	{
		return symbol_to_index[(unsigned char) symbol];
	}

	inline double const & get_halfmax_distance() const
	{
		return halfmax_distance;
	}

	inline const int size() const
	{
		return vector_size;
	}

	inline const substitution_matrix::matrix_type get_score(const int index1, const int index2) const
	{
		return matrix[index1 * vector_size + index2];
	}

	inline const substitution_matrix::matrix_type * get_score_vector(const int index) const
	{
		return &matrix[index * vector_size];
	}

	inline void print() const
	{
		for (int i = 0; i < vector_size; ++i)
		{
			for (int j = 0; j < vector_size; ++j)
				printf("%4d", get_score(i, j));
			std::cout << std::endl;
		}
	}

private:
	int vector_size;
	substitution_matrix::matrix_type *matrix;
	char *symbols;
	char *symbol_to_index;
	double halfmax_distance;
};

struct SymbolCount
{
	const ScoringMatrix &matrix;
	int * counts;
	int known;
	int unknown;
	int gapped;

	SymbolCount(const ScoringMatrix &mat, const char *column, int size) :
		matrix(mat),
		counts(new int [mat.size()]),
		known(0),
		unknown(0),
		gapped(0)
	{
		memset(counts, 0, sizeof(int) * mat.size());
		for (int i = 0; i < size; ++i)
		{
			add(column[i]);
		}
	};

	~SymbolCount()
	{
		delete [] counts;
	}

	void add(const char symbol)
	{
		if (symbol == '-' or symbol == '-')
		{
			++gapped;
		}
		if (!matrix.has_symbol(symbol))
		{
			unknown += 1;
			return;
		}
		known += 1;
		counts[matrix.get_index(symbol)]++;
	}

	double const * calculate_centroid() const
	{
		int sum[matrix.size()];
		memset(&sum, 0, matrix.size() * sizeof(int));
		for (int i = 0; i < matrix.size(); ++i)
		{
			if (counts[i] == 0)
			{
				continue;
			}
			for (int j = 0; j < matrix.size(); ++j)
			{
				sum[j] += counts[i] * matrix.get_score(i, j);
			}
		}
		double * c = new double[matrix.size()];
		for (int i = 0; i < matrix.size(); ++i)
		{
			c[i] = (double) sum[i] / known;
		}
		return c;
	}

	double* calculate_distances()
	{
		double *distances = new double [matrix.size()];
		memset(distances, 0, matrix.size() * sizeof(double));
		if (known == 0)
		{
			return distances;
		}
		const double *centroid = calculate_centroid();
		// Calculate distances
		for (int i = 0; i < matrix.size(); ++i)
		{
			if (counts[i] != 0)
			{
				distances[i] = matrix.distance(matrix.get_score_vector(i), centroid);
			}
		}
		delete centroid;
		return distances;
	}

	double calculate_cscore(double *distances)
	{
		if (known == 0)
		{
			return 0.0;
		}
		double sum_distance = 0;
		for (int i = 0; i < matrix.size(); ++i)
		{
			if (counts[i] != 0)
			{
				double weight = (double) counts[i];
				sum_distance += distances[i] * weight;
			}
		}
		double N_1 = known + unknown - 1;
		double N = known + unknown;
		double halfmax = matrix.get_halfmax_distance();
		double cscore = 1 - sum_distance / halfmax / N - unknown / N_1;
		return std::max(std::min(cscore, 1.0), 0.0);
	}

	double* calculate_divergences(const double *distances, const double &cscore)
	{
		double N_1 = known + unknown;
		double *divs = new double [matrix.size()];
		memset(divs, 0, matrix.size() * sizeof(double));
		double divergence;
		for (int i = 0; i < matrix.size(); ++i)
		{
			if (distances[i] != 0)
			{
				// 2 in denominator because we really want to divide by maxdist, not halfmax.
				divergence = cscore * distances[i] / matrix.get_halfmax_distance() / 2 + unknown / N_1;
				divs[i] = std::max(std::min(divergence, 1.0), 0.0);
			}
		}
		// using gap character '-' to store divergence for unknown chars,
		// since gaps just get cscore as divergence.
		divergence = cscore + unknown / N_1;
		divs[(int) '-'] = std::max(std::min(divergence, 1.0), 0.0);
		return divs;
	}
};

void process_column(
		const ScoringMatrix &matrix,
		const char *column_buffer,
		const int n_sequences,
		double *cscore,
		double *divergences,
		double *conformances)
{
	SymbolCount counts(matrix, column_buffer, n_sequences);
	double *distances = counts.calculate_distances();
	(*cscore) = counts.calculate_cscore(distances);
	double *divs = counts.calculate_divergences(distances, *cscore);
	delete distances;
	for (int i = 0; i < n_sequences; ++i)
	{
		char symbol = column_buffer[i];
		if (symbol == '.' or symbol == '-')
		{
			divergences[i] = *cscore;
		}
		else
		{
			int index = matrix.get_index(symbol);
			if (index == -1)
			{
				divergences[i] = divs[(int) '-'];
			}
			else
			{
				divergences[i] = divs[index];
			}
		}
		conformances[i] += divergences[i];
	}
	delete divs;
}

//static const ScoringMatrix gonnet = ScoringMatrix(substitution_matrix::_GONNET);
//static const ScoringMatrix gonnet = ScoringMatrix(substitution_matrix::_BLOSUM62);
static const ScoringMatrix gonnet = ScoringMatrix(substitution_matrix::_GONNET250);

static PyObject *
_cscore_process_column_wrapper(PyObject *dummy, PyObject *args)
{
	// Parse args.
	PyArrayObject *cscores = NULL;
	PyArrayObject *divergences_transpose = NULL;
	PyArrayObject *conformances = NULL;
	PyArrayObject *column_array;
	int position;
	if (!PyArg_ParseTuple(args, "OOOOi",
			&cscores,
			&divergences_transpose,
			&conformances,
			&column_array,
			&position
			))
	{
        return NULL;
	}
	npy_intp *dims = PyArray_DIMS(divergences_transpose);
	int n_sequences = dims[1];
	double *cscores_data = (double*) PyArray_DATA(cscores);
	double *divergences_data = (double*) PyArray_DATA(divergences_transpose);
	double *conformances_data = (double*) PyArray_DATA(conformances);
	const char *column_data = (char*) PyArray_DATA(column_array);

	// Get work done.
	process_column(
			gonnet,
			&column_data[n_sequences * position],
			n_sequences,
			&cscores_data[position],
			&divergences_data[n_sequences * position],
			conformances_data);
	return Py_None;
}

struct color_type
{
	char b,g,r,a;
	color_type() { };
	color_type(char blue, char green, char red, char alpha) :
		b(blue),
		g(green),
		r(red),
		a(alpha)
	{ }
	int32_t as_int() const { return *((int32_t *)this); }
	color_type blend(const color_type other, const double &amount) const
	{
		double x = 1 - amount;
		color_type color;
		unsigned char * c = (unsigned char *) &color;
		for (int i = 0; i < 4; ++i)
		{
			c[i] = ((unsigned char *) this)[i] * x + ((unsigned char *) &other)[i] * amount;
		}
		return color;
	}
	void print()
	{
		std::cout << (int) (unsigned char) a << ' ' << (int) (unsigned char) r << ' ' << (int) (unsigned char) g << ' ' << (int) (unsigned char) b << ' ' << std::endl;
	}
};

struct colorstop_type
{
	double offset;
	color_type color;
	colorstop_type() {};
	colorstop_type(double &o, color_type* c) : offset(o), color(*c) { };
};

static PyObject *
_cscore_divergences_renderer_colorize(PyObject *dummy, PyObject *args)
{
	// Parse args.
	PyArrayObject *image_array = NULL;
	PyArrayObject *divergences_array = NULL;
	PyObject *gradient = NULL;
	if (!PyArg_ParseTuple(args, "OOO",
			&image_array,
			&divergences_array,
			&gradient
			))
	{
        return NULL;
	}
	npy_intp *dims = PyArray_DIMS(divergences_array);
	int n_sequences = dims[0];
	int n_positions = dims[1];
	double *divergences_data = (double*) PyArray_DATA(divergences_array);
	color_type *image_data = (color_type*) PyArray_DATA(image_array);

	// Build colorstop array.
	PyObject *list = PyObject_GetAttrString(gradient, "colorstops");
	Py_ssize_t n_colorstops = PyList_Size(list);
	if (n_colorstops == 0)
	{
		// nothing to paint with, and image is already zeroed by cairo.
		return Py_None;
	}
	colorstop_type colorstops[n_colorstops];
	for (Py_ssize_t i = 0; i < n_colorstops; ++i)
	{
		PyObject* colorstop_obj = PyList_GET_ITEM(list, i);
		PyObject* offset_obj = PyTuple_GET_ITEM(colorstop_obj, 0);
		double offset = PyFloat_AS_DOUBLE(offset_obj);
		PyObject* color_obj = PyTuple_GET_ITEM(colorstop_obj, 1);
		color_type *color = (color_type*) PyArray_DATA(PyObject_GetAttrString(color_obj, "array"));
		colorstops[i] = colorstop_type(offset, color);
	}

	// Get work done.
	for (int seq = 0; seq < n_sequences; ++seq)
	{
		for (int pos = 0; pos < n_positions; ++pos)
		{
			int offset = pos * n_sequences + seq;
			double div = divergences_data[offset];
			// Check outside of stops.
			if (div >= colorstops[n_colorstops - 1].offset)
			{
				image_data[offset] = colorstops[n_colorstops - 1].color;
				continue;
			}
			if (div < colorstops[0].offset)
			{
				image_data[offset] = colorstops[0].color;
				continue;
			}
			// Check between stops.
			for (int i = n_colorstops - 2; i >= 0; --i)
			{
				if (div < colorstops[i].offset)
				{
					continue;
				}
				// found it! copy color or blend and break out to next pixel.
				if (offset == colorstops[i].offset)
				{
					image_data[offset] = colorstops[i].color;
				}
				else
				{
					double amount = ((div - colorstops[i].offset) / (colorstops[i + 1].offset - colorstops[i].offset));
					image_data[offset] = colorstops[i].color.blend(colorstops[i + 1].color, amount);
				}
				break;
			}

		}
	}
	return Py_None;
}

static PyMethodDef CScoreMethods[] = {
		{"process_column",  _cscore_process_column_wrapper, METH_VARARGS, "Compute cscores for an MSA column (saves divergence sums in conformance vector)."},
		{"divergences_renderer_colorize",  _cscore_divergences_renderer_colorize, METH_VARARGS, "Translate divergence array to an image using a gradient."},
		{NULL, NULL, 0, NULL} // Sentinel
};

PyMODINIT_FUNC
init_cscore(void)
{
    PyObject *m;

    m = Py_InitModule("_cscore", CScoreMethods);
    if (m == NULL)
        return;
    import_array();

    /*
    char buffer [] = "_cscore.error";
    CScoreError = PyErr_NewException(buffer, NULL, NULL);
    Py_INCREF(CScoreError);
    PyModule_AddObject(m, "error", CScoreError);
    */
}
