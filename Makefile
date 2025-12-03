.PHONY: test install uninstall clean help

help:
	@echo "Available targets:"
	@echo "  test       - Run unit tests"
	@echo "  install    - Run the installation script"
	@echo "  uninstall  - Run the uninstallation script"
	@echo "  clean      - Remove temporary files and build artifacts"

test:
	python3 -m unittest discover tests

install:
	chmod +x install.sh
	./install.sh

uninstall:
	chmod +x uninstaller.sh
	./uninstaller.sh

clean:
	rm -rf build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
