# standard Python project Makefile
progname = $(shell awk '/^Source/ {print $$2}' debian/control)
name=

prefix = /usr/local
PATH_BIN = $(prefix)/bin
PATH_INSTALL_LIB = $(prefix)/lib/$(progname)
PATH_DIST := $(progname)-$(shell date +%F)

truepath = $(shell echo $1 | sed -e 's/^debian\/$(progname)//')

all: help

debug:
	$(foreach v, $V, $(warning $v = $($v)))
	@true

dist: clean
	-mkdir -p $(PATH_DIST)

	-cp -a .git .gitignore $(PATH_DIST)
	-cp -a *.sh *.c *.py Makefile pylib/ libexec* $(PATH_DIST)

	tar jcvf $(PATH_DIST).tar.bz2 $(PATH_DIST)
	rm -rf $(PATH_DIST)

### Extendable targets

# target: help
help:
	@echo '=== Targets:'
	@echo 'install   [ prefix=path/to/usr ] # default: prefix=$(value prefix)'
	@echo 'uninstall [ prefix=path/to/usr ]'
	@echo
	@echo 'clean'
	@echo
	@echo 'dist                             # create distribution tarball'

# target: install
install:
	@echo
	@echo \*\* CONFIG: prefix = $(prefix) \*\*
	@echo 

	install -d $(PATH_BIN) $(PATH_INSTALL_LIB)
	cp *.py $(PATH_INSTALL_LIB)
	ln -fs $(call truepath,$(PATH_INSTALL_LIB))/$(progname).py $(PATH_BIN)/$(progname)

# target: uninstall
uninstall:
	rm -rf $(PATH_INSTALL_LIB)
	rm -f $(PATH_BIN)/$(progname)

# target: clean
clean:
	rm -f *.pyc *.pyo _$(progname)
