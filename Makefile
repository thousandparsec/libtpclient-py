
release:
	rm -rf dist
	python setup.py sdist --formats=gztar,zip
	python setup.py bdist --formats=rpm,wininst
	cp dist/* ../web/downloads/libtpclient-py
	cd ../web/downloads/libtpclient-py ; darcs add *.* ; darcs record

clean:
	rm -rf dist
	rm -rf build
