PROG       = transformers_ocr
SHORT_PROG = trocr
PREFIX    ?= /usr
DESTDIR   ?=
BINDIR     = $(DESTDIR)$(PREFIX)/bin
PKGLIBDIR  = $(DESTDIR)$(PREFIX)/lib/$(PROG)
LICENSEDIR = $(DESTDIR)$(PREFIX)/share/licenses/$(PROG)
UNITDIR    = $(DESTDIR)$(PREFIX)/lib/systemd/user

PKGDIR     = src/transformers_ocr
VPATH      = src

MODULES = __init__.py __main__.py cli.py config.py download.py \
          exceptions.py fifo.py notify.py ocr_command.py \
          platform.py process.py wrapper.py preview.py screengrab.py

.PHONY: all install uninstall clean

all:
	@printf '\033[1;32m%s\033[0m\n' \
		'This program does not need to be built. Run "make install".'

install:
	@printf '\033[1;32m%s\033[0m\n' 'Installing $(PROG)...'
	# Entry-point script
	install -Dm755 $(VPATH)/$(PROG).py $(BINDIR)/$(PROG)
	ln -sf $(PROG) $(BINDIR)/$(SHORT_PROG)
	# Python package — lives under $(PREFIX)/lib/transformers_ocr/
	install -d $(PKGLIBDIR)/$(PROG)
	$(foreach m,$(MODULES),install -Dm644 $(PKGDIR)/$(m) $(PKGLIBDIR)/$(PROG)/$(m);)
	# Systemd unit
	install -Dm644 $(VPATH)/$(PROG).service $(UNITDIR)/$(PROG).service
	# License
	install -Dm644 LICENSE $(LICENSEDIR)/LICENSE

uninstall:
	@printf '\033[1;32m%s\033[0m\n' 'Uninstalling $(PROG)...'
	rm -f  $(BINDIR)/$(PROG)
	rm -f  $(BINDIR)/$(SHORT_PROG)
	rm -rf $(PKGLIBDIR)
	rm -f  $(UNITDIR)/$(PROG).service
	rm -rf $(LICENSEDIR)

clean:
	@printf '\033[1;32m%s\033[0m\n' 'Nothing to clean.'
