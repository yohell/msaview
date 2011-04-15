/*
 * Written by Fredrik Lysholm
 *
 * Copyright (C) 2000 and later by Fredrik Lysholm
 *
 * The MIT license.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 */

#ifndef SUBSTITUTION_MATRIX_H_
#define SUBSTITUTION_MATRIX_H_

#include <cstdio>

class substitution_matrix
{
	public:
		enum builtin_matrixes { _BLOSUM30, _BLOSUM40, _BLOSUM50, _BLOSUM62, _BLOSUM80, _BLOSUM90, _PAM30, _PAM70, _PAM250, _GONNET, _GONNET250};
		//typedef float matrix_type;
		//typedef char matrix_type;
		typedef short matrix_type;

	private:
		int vector_size;
		char * alphabet;
		char * index_lookup;
		matrix_type * matrix_lookup;
	public:
		substitution_matrix(const builtin_matrixes matrix = _BLOSUM62);
		substitution_matrix(const char * matrix_file);
		virtual ~substitution_matrix();

		inline int get_alphabet_size() const { return vector_size; }
		inline const char * get_alphabet() const { return alphabet; }
		inline const int get_alphabet_index(const char a) const { return index_lookup[(unsigned char)a]; }

		//matrix_type lookup(const char a, matrix_type def = 0) const ;
		matrix_type lookup(const char a, const char b, matrix_type def = 0) const ;

		void load_builtin_matrix(const builtin_matrixes matrix);
		bool load(const char * file);
		bool save(const char * file) const ;

		void print_matrix_as_code(FILE * out = stdout) const;
};

#endif /* SUBSTITUTION_MATRIX_H_ */
