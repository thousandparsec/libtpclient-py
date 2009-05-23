
release:
	rm -rf dist
	python setup.py sdist --formats=bztar --ignore-deps
	python setup.py bdist --formats=egg --ignore-deps
	cp dist/* ../web/downloads/libtpclient-py

clean:
	rm -rf dist
	rm -rf build
	rm -rf libtpclient_py.egg-info
