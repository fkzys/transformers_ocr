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

# ── Integration tests (require Xvfb) ──────────────────────────────

XVFB_DISPLAY      := :99
XVFB_SCREEN       := 0
XVFB_RES          := 1920x1080x24
XVFB_PIDFILE      := /tmp/xvfb_test.pid
INTEGRATION_TESTS := tests/test_screengrab_integration.py

.PHONY: test test-unit test-xvfb kill-xvfb

test: test-unit test-xvfb

test-unit:
	python -m pytest tests/ -x -q --ignore=$(INTEGRATION_TESTS) --timeout=10

kill-xvfb:
	@if [ -f $(XVFB_PIDFILE) ]; then \
		PID=$$(cat $(XVFB_PIDFILE)); \
		kill "$$PID" 2>/dev/null || true; \
		rm -f $(XVFB_PIDFILE); \
		echo "  Xvfb stopped (pid $$PID)"; \
	fi
	@killall Xvfb 2>/dev/null || true
	@rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

test-xvfb: kill-xvfb
	@if ! command -v Xvfb >/dev/null 2>&1; then \
		echo "ERROR: Xvfb not installed. Install: sudo pacman -S xorg-server-xvfb"; \
		exit 1; \
	fi
	@echo "==> Starting Xvfb on $(XVFB_DISPLAY)"
	@Xvfb $(XVFB_DISPLAY) -screen $(XVFB_SCREEN) $(XVFB_RES) -nolisten tcp \
		-noreset 2>/dev/null & \
	XPID=$$!; \
	echo "$$XPID" > $(XVFB_PIDFILE); \
	sleep 1; \
	if ! kill -0 "$$XPID" 2>/dev/null; then \
		echo "ERROR: Xvfb failed to start (pid $$XPID)"; \
		echo "  Check: ls -la /tmp/.X99-lock"; \
		rm -f $(XVFB_PIDFILE); \
		exit 1; \
	fi; \
	echo "  Xvfb started (pid $$XPID)"; \
	echo "==> Running X11 integration tests"; \
	env -u WAYLAND_DISPLAY DISPLAY=$(XVFB_DISPLAY) \
		python -m pytest $(INTEGRATION_TESTS) -x -v --timeout=30; \
	RC=$$?; \
	kill "$$XPID" 2>/dev/null || true; \
	rm -f $(XVFB_PIDFILE); \
	echo "  Xvfb stopped (pid $$XPID)"; \
	exit $$RC

# ── Smoke test in nspawn container ─────────────────────────────────

SMOKE_ROOT := /tmp/trocr-smoke

test-smoke:
	@if [ "$$(id -u)" -ne 0 ]; then echo "ERROR: needs root" >&2; exit 1; fi
	@echo "==> Creating test container"
	mkdir -p $(SMOKE_ROOT)
	pacstrap -cGM $(SMOKE_ROOT) base make python python-pytest python-pytest-timeout \
		xorg-server-xvfb libx11 sdl2 sdl2_image dbus 2>/dev/null
	@echo "==> Copying source"
	mkdir -p $(SMOKE_ROOT)/opt/trocr
	cp -a src tests Makefile $(SMOKE_ROOT)/opt/trocr/
	systemd-nspawn -q --register=no -D $(SMOKE_ROOT) /bin/bash -c \
		'cd /opt/trocr && make test-unit && make test-xvfb'
	@echo "==> Cleaning up"
	rm -rf $(SMOKE_ROOT)
	@echo "==> All smoke tests passed"
