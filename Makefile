install:
	@python setup.py sdist
	@pip install dist/clara-1.0.tar.gz

uninstall:
	@pip uninstall clara

reinstall:
	make uninstall
	make install

build:
	@python setup.py build

clean:
	@find . \( -name \*.pyc -o -name \*~ -o -name \*.so \) -exec rm -fv {} \;
	@find clara/ -name \*.c -exec rm -fv {} \;
	@rm -fv MANIFEST
	@rm -rvf build/ dist/
