"""MSAView - Fast and flexible visualisation of multiple sequence alignments.

Copyright (c) 2011 Joel Hedlund.

Contact: Joel Hedlund <yohell@ifm.liu.se>

MSAView is a modular, configurable and extensible package for analysing and 
visualising multiple sequence alignments and sequence features. It can import 
and display data from online sources, and it can launch external viewers for 
additional details, such as structures and database pages. MSAView is highly
configurable and has a user extendable preset library, as well as a plugin 
architecture which allows for straightforward extension of the program's 
capabilities.

MSAVIew has a fast graphical user interface that remains responsive even for 
large datasets, as well as a powerful command line client which allows the user
to generate consistent views for hundreds of protein families at a time. All 
the program's functionality is also directly accessible via the python API for
more advanced operations. 
 
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

from distutils.core import Extension, setup
import os
import subprocess

packages = ['msaview', 
            'msaview_ui',
            'msaview_plugin_biomart', 
            'msaview_plugin_clustal', 
            'msaview_plugin_cscore', 
            'msaview_plugin_ensembl', 
            'msaview_plugin_hmmer', 
            'msaview_plugin_nexus', 
            'msaview_plugin_pdb', 
            'msaview_plugin_pfam', 
            'msaview_plugin_pymol', 
            'msaview_plugin_stockholm', 
            'msaview_plugin_substitution_matrix', 
            'msaview_plugin_uniprot',
            ]
py_modules = ['msaview_plugin_backbone', 
              'msaview_plugin_disopred', 
              ]

for name in packages + py_modules:
    getattr(__import__(name), '__version__')
    
versions = dict((name, getattr(__import__(name), '__version__')) for name in packages + py_modules)
provides = ["%s (%s)" % (name, versions[name]) for name in packages + py_modules]
__version__ = versions['msaview']

setup(name='msaview',
      version=__version__,
      description='Fast and flexible visualisation of multiple sequence alignments.',
      platforms='OS Independent',
      author='Joel Hedlund',
      author_email='yohell@ifm.liu.se',
      url='https://sourceforge.net/projects/msaview/',
      download_url='https://sourceforge.net/projects/msaview/',
      packages=packages,
      py_modules=py_modules,
      provides=provides,
      scripts=['msaview_ui/msaview'],
      ext_modules=[Extension('msaview._renderers', 
                             ['msaview/renderers.cpp'], 
                             extra_compile_args=['-O3'],
                             extra_link_args=['-Wl,-O3'],
                             ),
                   Extension('msaview_plugin_cscore._cscore', 
                             ['msaview_plugin_cscore/cscore.cpp', 
                              'msaview_plugin_substitution_matrix/substitution_matrix.cpp', 
                              ], 
                             include_dirs=['msaview_plugin_substitution_matrix'],
                             extra_compile_args=['-O3'],
                             extra_link_args=['-Wl,-O3'],
                             ),
                   Extension('msaview_plugin_substitution_matrix._substitution_matrix', 
                             ['msaview_plugin_substitution_matrix/substitution_matrix.i',
                              'msaview_plugin_substitution_matrix/substitution_matrix.cpp',
                              ],
                             swig_opts=['-c++'], 
                             extra_compile_args=['-O3'],
                             extra_link_args=['-Wl,-O3'],
                             ),
                   ],
      package_data={'msaview': ['data/*.mxml',
                                'data/*.txt',
                                ],
                    'msaview_plugin_cscore': ['*.mxml'],
                    'msaview_plugin_ensembl': ['*.mxml'],
                    'msaview_plugin_pymol': ['*.mxml'],
                    'msaview_plugin_substitution_matrix': ['matrices/*.mat'],
                    'msaview_plugin_uniprot': ['*.mxml'],
                    },
      license=open('LICENSE.txt').read(),
      long_description='\n' + open('README.txt').read(),
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: MIT License',
          'Operating System :: OS Independent',
          'Programming Language :: C++',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: Scientific/Engineering :: Bio-Informatics',
          ],
      )

