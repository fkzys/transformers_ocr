PROG       = transformers_ocr
SHORT_PROG = trocr
PREFIX    ?= /usr
DESTDIR   ?=
BINDIR     = $(DESTDIR)$(PREFIX)/bin
LICENSEDIR = $(DESTDIR)$(PREFIX)/share/licenses/$(PROG)
UNITDIR    = $(DESTDIR)$(PREFIX)/lib/systemd/user

PKGDIR     = src/transformers_ocr
VPATH      = src

# Detect the Python site-packages directory.
PYTHON    ?= python3
SITEPKGS   = $(DESTDIR)$(shell $(PYTHON) -c \
    "import sysconfig; print(sysconfig.get_path('purelib'))")

.PHONY: all install uninstall clean

all:
	@printf '\033[1;32m%s\033[0m\n' \
		'This program does not need to be built. Run "make install".'

install:
	@printf '\033[1;32m%s\033[0m\n' 'Installing $(PROG)...'
	# Entry-point script
	install -Dm755 $(VPATH)/$(PROG).py $(BINDIR)/$(PROG)
	ln -sf $(PROG) $(BINDIR)/$(SHORT_PROG)
	# Python package
	install -d $(SITEPKGS)/$(PROG)
	install -Dm644 $(PKGDIR)/__init__.py   $(SITEPKGS)/$(PROG)/__init__.py
	install -Dm644 $(PKGDIR)/__main__.py   $(SITEPKGS)/$(PROG)/__main__.py
	install -Dm644 $(PKGDIR)/cli.py        $(SITEPKGS)/$(PROG)/cli.py
	install -Dm644 $(PKGDIR)/config.py     $(SITEPKGS)/$(PROG)/config.py
	install -Dm644 $(PKGDIR)/download.py   $(SITEPKGS)/$(PROG)/download.py
	install -Dm644 $(PKGDIR)/exceptions.py $(SITEPKGS)/$(PROG)/exceptions.py
	install -Dm644 $(PKGDIR)/fifo.py       $(SITEPKGS)/$(PROG)/fifo.py
	install -Dm644 $(PKGDIR)/notify.py     $(SITEPKGS)/$(PROG)/notify.py
	install -Dm644 $(PKGDIR)/ocr_command.py $(SITEPKGS)/$(PROG)/ocr_command.py
	install -Dm644 $(PKGDIR)/platform.py   $(SITEPKGS)/$(PROG)/platform.py
	install -Dm644 $(PKGDIR)/process.py    $(SITEPKGS)/$(PROG)/process.py
	install -Dm644 $(PKGDIR)/wrapper.py    $(SITEPKGS)/$(PROG)/wrapper.py
	install -Dm644 $(VPATH)/$(PROG).service $(UNITDIR)/$(PROG).service
	install -Dm644 LICENSE $(LICENSEDIR)/LICENSE

uninstall:
	@printf '\033[1;32m%s\033[0m\n' 'Uninstalling $(PROG)...'
	rm -f  $(BINDIR)/$(PROG)
	rm -f  $(BINDIR)/$(SHORT_PROG)
	rm -rf $(SITEPKGS)/$(PROG)
	rm -f  $(UNITDIR)/$(PROG).service
	rm -rf $(LICENSEDIR)

clean:
	@printf '\033[1;32m%s\033[0m\n' 'Nothing to clean.'
