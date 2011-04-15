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
    try:
        getattr(__import__(name), '__version__')
    except:
        build_script = os.path.join(os.path.dirname(__file__), name, 'build.sh')
        if not os.path.isfile(build_script):
            raise
        subprocess.Popen([build_script])
    
versions = dict((name, getattr(__import__(name), '__version__')) for name in packages + py_modules)
provides = ["%s (%s)" % (name, versions[name]) for name in packages + py_modules]

setup(name='msaview',
      version=versions['msaview'],
      description='Fast and flexible visualisation of multiple sequence alignments.',
      platforms='OS Independent',
      author='Joel Hedlund',
      author_email='yohell@ifm.liu.se',
      url='https://sourceforge.net/projects/msaview/',
      download_url='https://sourceforge.net/projects/msaview/',
      packages=packages,
      py_modules=py_modules,
      provides=provides,
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

