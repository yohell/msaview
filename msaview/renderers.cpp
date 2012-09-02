#include <Python.h>
#include <numpy/arrayobject.h>
#include <iostream>
#include <stdint.h>
#include <vector>

//static PyObject *RenderersError;

struct color_type {
	char b,g,r,a;
	int32_t as_int() const { return *((int32_t *)this); }
};

static PyObject *
_residue_colors_colorize(PyObject *dummy, PyObject *args)
{
	// Parse python args.
	PyArrayObject *image_array = NULL;
	PyArrayObject *sequence_array = NULL;
	PyObject *color_dict = NULL;
	PyArrayObject *unrecognized_array = NULL;
	if (!PyArg_ParseTuple(args, "OOOO",
			&image_array,
			&sequence_array,
			&color_dict,
			&unrecognized_array
			))
	{
        return NULL;
	}
	color_type *image_data = (color_type*) PyArray_DATA(image_array);
	char *sequence_data = (char*) PyArray_DATA(sequence_array);
	color_type *unrecognized_color = (color_type*) PyArray_DATA(unrecognized_array);
	npy_intp *dims = PyArray_DIMS(sequence_array);
	int n_sequences = dims[0];
	int n_positions = dims[1];

	// Build char-to-color lookup.
	color_type char_to_color [256] = {*unrecognized_color};
	PyObject *key, *value;
	Py_ssize_t pos = 0;
	while (PyDict_Next(color_dict, &pos, &key, &value)) {
	    char *symbol = PyString_AS_STRING(key);
	    PyObject *color_array = PyObject_GetAttrString(value, "array");
	    char_to_color[(unsigned char) symbol[0]] = (* (color_type*) PyArray_DATA(color_array));
	}

	// get down to business (finally!)
	for (int seq = 0; seq < n_sequences; ++seq)
	{
		for (int pos = 0; pos < n_positions; ++pos)
		{
			int offset = seq * n_positions + pos;
			image_data[offset] = char_to_color[(unsigned char) sequence_data[offset]];
		}
	}

	return Py_None;
}


static PyMethodDef RenderersMethods[] = {
		{"residue_colors_colorize",  _residue_colors_colorize, METH_VARARGS, "Populate an nseq*npos*ARGB byte array using a char -> ARGB dict lookup."},
		{NULL, NULL, 0, NULL} // Sentinel
};


PyMODINIT_FUNC
init_renderers(void)
{
    PyObject *m;

    m = Py_InitModule("_renderers", RenderersMethods);
    if (m == NULL)
        return;
    import_array();

    /*
    char buffer [] = "_renderers.error";
    RenderersError = PyErr_NewException(buffer, NULL, NULL);
    Py_INCREF(RenderersError);
    PyModule_AddObject(m, "error", RenderersError);
    */
}
