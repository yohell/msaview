/*
 * Written by Fredrik Lysholm
 *
 * Copyright (C) 2000 and later by Fredrik Lysholm
 *
 * All rights reserved.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the
 * Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA
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
