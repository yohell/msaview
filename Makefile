# Makefile for developer use. It will probably not do what you want. 
# You should probably use src/setup.py instead.
 
prefix=~/apps
python=$(shell readlink `which python`)

generated_dirs=src/build src/dist
generated_code=src/msaview_plugin_substitution_matrix/substitution_matrix.py
generated=${generated_dirs} ${generated_code}
generated_patterns='*_wrap.*' '*.o' '*.pyc' '*.pyo' '*.so'

all:
	(cd src; python setup.py build)
	for extension in $$(cd src/build/lib.*; find -name '_*.so'); do \
		cp src/build/lib.*/$$extension src/$$extension; \
	done

install:
	rm -rf ${prefix}/lib/${python}/site-packages/msaview{,_ui,_plugin_*}
	(cd src; python setup.py install --prefix ${prefix})

clean:
	rm -rf pack
	rm -rf ${generated}
	for generated_pattern in ${generated_patterns}; do \
		find src -name $$generated_pattern -delete; \
	done

sdist:
	(cd src; python setup.py sdist)
	
pack: sdist
	mkdir -p pack/deb
	cp src/dist/msaview-*.tar.gz pack/deb
	rename 's/-/_/; s/.tar.gz/.orig.tar.gz/' pack/deb/msaview-* 
	(cd pack/deb; tar xf msaview_*)
	(cd pack/deb/*; \
	 [ ! -e ../../../debian ] && ( dh_make; mv debian ../../.. ); \
	 ln -s ../../../debian)  