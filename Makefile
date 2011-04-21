# Makefile for developer use. It will probably not do what you want. 
# You should probably use src/setup.py instead.
 
prefix=~/apps
python=$(shell readlink `which python`)

generated=src/build src/dist src/MANIFEST src/msaview_plugin_substitution_matrix/substitution_matrix.py
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
	(cd src; rm MANIFEST; python setup.py sdist)
	
pack: pack-deb

pack-deb: sdist 
	rm -rf pack/deb
	mkdir -p pack/deb
	cp src/dist/msaview-*.tar.gz pack/deb
	rename 's/-/_/; s/.tar.gz/.orig.tar.gz/' pack/deb/msaview-* 
	(cd pack/deb; tar xf msaview_*)
	(cd pack/deb/*; if [ ! -e ../../../debian ]; then dh_make; else cp -r ../../../debian . ; fi )
	 
deb: pack-deb
	(cd pack/deb/msaview-*; debuild -us -uc)
	