PROG      = transformers_ocr
SHORT_PROG = trocr
PREFIX    ?= /usr
DESTDIR   ?=
BINDIR     = $(DESTDIR)$(PREFIX)/bin
LICENSEDIR = $(DESTDIR)$(PREFIX)/share/licenses/$(PROG)
UNITDIR    = $(DESTDIR)$(PREFIX)/lib/systemd/user

VPATH = src

.PHONY: all install uninstall clean

all:
	@printf '\033[1;32m%s\033[0m\n' \
		'This program does not need to be built. Run "make install".'

install:
	@printf '\033[1;32m%s\033[0m\n' 'Installing $(PROG)...'
	install -Dm755 $(VPATH)/$(PROG).py $(BINDIR)/$(PROG)
	ln -sf $(PROG) $(BINDIR)/$(SHORT_PROG)
	install -Dm644 $(VPATH)/$(PROG).service $(UNITDIR)/$(PROG).service
	install -Dm644 LICENSE $(LICENSEDIR)/LICENSE

uninstall:
	@printf '\033[1;32m%s\033[0m\n' 'Uninstalling $(PROG)...'
	rm -f $(BINDIR)/$(PROG)
	rm -f $(BINDIR)/$(SHORT_PROG)
	rm -f $(UNITDIR)/$(PROG).service
	rm -rf $(LICENSEDIR)

clean:
	@printf '\033[1;32m%s\033[0m\n' 'Nothing to clean.'
