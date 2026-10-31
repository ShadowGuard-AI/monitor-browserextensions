import argparse
import json
import logging
import os
import sys
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define browser extension directories (platform-specific)
CHROME_EXTENSIONS_DIR_WINDOWS = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default', 'Extensions')
CHROME_EXTENSIONS_DIR_LINUX = os.path.expanduser("~/.config/google-chrome/Default/Extensions")
CHROME_EXTENSIONS_DIR_MAC = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Extensions")


FIREFOX_EXTENSIONS_DIR_WINDOWS = os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles') # requires profile parsing
FIREFOX_EXTENSIONS_DIR_LINUX = os.path.expanduser("~/.mozilla/firefox")  #requires profile parsing
FIREFOX_EXTENSIONS_DIR_MAC = os.path.expanduser("~/Library/Application Support/Firefox/Profiles") # requires profile parsing



def setup_argparse():
    """Sets up the command line argument parser."""
    parser = argparse.ArgumentParser(description='Monitor browser extensions for changes.')
    parser.add_argument('--browser', type=str, choices=['chrome', 'firefox'],
                        help='The browser to monitor (chrome or firefox).', required=False)
    parser.add_argument('--interval', type=int, default=60,
                        help='The interval (in seconds) between checks.', required=False)
    parser.add_argument('--report', type=str,
                        help='File to save extension change reports.', required=False)
    parser.add_argument('--alert-on-change', action='store_true', help='Alert and log on extension change')
    parser.add_argument('--extensions_dir', type=str, help='Specify the extensions directory', required=False)
    return parser.parse_args()

def get_chrome_extensions_status(extensions_dir):
    """
    Gets the monitored state of Chrome extensions, with a read status
    that keeps a missing or unreadable directory distinct from one
    that was read and found empty.

    The state holds one entry per installed version of each
    extension, including the modification time of its manifest.json
    when one is present, so a change inside an installed extension
    (a new version folder or a changed manifest) changes the state,
    not only the arrival or removal of a top level ID folder.

    Returns (entries, status): entries is None when the directory
    could not be read, and status is "read", "missing", or "error".
    """
    if not os.path.exists(extensions_dir):
        logging.warning(f"Chrome extensions directory not found: {extensions_dir}")
        return None, "missing"
    try:
        extensions = []
        for entry in sorted(os.listdir(extensions_dir)):
            entry_path = os.path.join(extensions_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            versions = [d for d in sorted(os.listdir(entry_path)) if os.path.isdir(os.path.join(entry_path, d))]
            if not versions:
                extensions.append(entry)
            for version in versions:
                manifest = os.path.join(entry_path, version, "manifest.json")
                marker = ""
                if os.path.exists(manifest):
                    marker = f"@{os.path.getmtime(manifest)}"
                extensions.append(f"{entry}/{version}{marker}")
        logging.debug(f"Found chrome extensions: {extensions}")
        return extensions, "read"
    except OSError as e:
        logging.error(f"Error accessing Chrome extensions directory: {e}")
        return None, "error"


def get_chrome_extensions(extensions_dir):
    """Gets the Chrome extension state list, or an empty list when unreadable."""
    extensions, _status = get_chrome_extensions_status(extensions_dir)
    return extensions if extensions is not None else []


def _firefox_profile_addons(profile_path, profile_name):
    """Parses one profile's extensions.json into monitored addon entries."""
    extensions_json = os.path.join(profile_path, "extensions.json")
    if not os.path.exists(extensions_json):
        return []
    try:
        with open(extensions_json, "r") as file:
            data = json.load(file)
    except (OSError, ValueError) as e:
        logging.error(f"Error reading extensions.json in profile {profile_name}: {e}")
        return []
    entries = []
    addons = data.get("addons", []) if isinstance(data, dict) else []
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        addon_id = addon.get("id")
        if not addon_id:
            default_locale = addon.get("defaultLocale") or {}
            addon_id = default_locale.get("name")
        if not addon_id:
            continue
        entries.append(f"{profile_name}:{addon_id}@{addon.get('version', '')}")
    return entries


def get_firefox_extensions_status(extensions_dir):
    """
    Gets the installed addons from Firefox profile directories, with
    a read status like the Chrome getter's.

    extensions.json in each profile is parsed and the addons inside
    it are monitored by ID and version. Every directory under the
    profiles directory is treated as a profile, whatever its name
    suffix, and the extensions directory itself is accepted as a
    single profile directory when it holds extensions.json directly.

    Returns (entries, status): entries is None when the directory
    could not be read, and status is "read", "missing", or "error".
    """
    if not os.path.exists(extensions_dir):
        logging.warning(f"Firefox profiles directory not found: {extensions_dir}")
        return None, "missing"
    try:
        extensions = []
        if os.path.exists(os.path.join(extensions_dir, "extensions.json")):
            profile_name = os.path.basename(os.path.normpath(extensions_dir))
            extensions.extend(_firefox_profile_addons(extensions_dir, profile_name))
        else:
            for item in sorted(os.listdir(extensions_dir)):
                profile_path = os.path.join(extensions_dir, item)
                if os.path.isdir(profile_path):
                    extensions.extend(_firefox_profile_addons(profile_path, item))
        logging.debug(f"Found Firefox addons: {extensions}")
        return extensions, "read"
    except OSError as e:
        logging.error(f"Error accessing Firefox profiles directory: {e}")
        return None, "error"


def get_firefox_extensions(extensions_dir):
    """Gets the Firefox addon state list, or an empty list when unreadable."""
    extensions, _status = get_firefox_extensions_status(extensions_dir)
    return extensions if extensions is not None else []


def get_any_extensions_status(extensions_dir):
    """
    Monitors an extensions directory whose browser was not named, by
    inferring the format from the directory itself: a directory that
    holds extensions.json, directly or inside profile subfolders, is
    read as Firefox; anything else is read as Chrome.
    """
    if os.path.isdir(extensions_dir):
        if os.path.exists(os.path.join(extensions_dir, "extensions.json")):
            return get_firefox_extensions_status(extensions_dir)
        try:
            for item in os.listdir(extensions_dir):
                if os.path.exists(os.path.join(extensions_dir, item, "extensions.json")):
                    return get_firefox_extensions_status(extensions_dir)
        except OSError as e:
            logging.error(f"Error accessing extensions directory: {e}")
            return None, "error"
    return get_chrome_extensions_status(extensions_dir)



def main():
    """Main function to monitor browser extensions."""
    args = setup_argparse()

    # Validate input
    if args.interval <= 0:
        logging.error("Interval must be a positive integer.")
        sys.exit(1)
    if args.report and not args.report.endswith(".txt"):
         logging.warning("Report file should end with .txt extension")


    browser = args.browser
    interval = args.interval
    report_file = args.report
    alert_on_change = args.alert_on_change

    if args.extensions_dir:
        extensions_dir = args.extensions_dir
    else:
        # Platform tests use sys.platform: darwin is a sys.platform
        # value, never an os.name value, and it is tested before the
        # generic posix case so macOS does not fall into the Linux paths.
        if browser == 'chrome':
            if sys.platform == 'win32':
                extensions_dir = CHROME_EXTENSIONS_DIR_WINDOWS
            elif sys.platform == 'darwin':
                extensions_dir = CHROME_EXTENSIONS_DIR_MAC
            else:
                extensions_dir = CHROME_EXTENSIONS_DIR_LINUX

        elif browser == 'firefox':
            if sys.platform == 'win32':
                extensions_dir = FIREFOX_EXTENSIONS_DIR_WINDOWS
            elif sys.platform == 'darwin':
                extensions_dir = FIREFOX_EXTENSIONS_DIR_MAC
            else:
                extensions_dir = FIREFOX_EXTENSIONS_DIR_LINUX
        else:
            logging.error("Please specify a browser (--browser) or extensions directory (--extensions_dir).")
            sys.exit(1)

    if browser == 'chrome':
        get_extensions_status = get_chrome_extensions_status
        browser_label = 'chrome'
    elif browser == 'firefox':
        get_extensions_status = get_firefox_extensions_status
        browser_label = 'firefox'
    elif args.extensions_dir:
        # --extensions_dir on its own works: the format is inferred
        # from the directory, as the selection code and error text
        # above present it.
        get_extensions_status = get_any_extensions_status
        browser_label = 'custom (format inferred from the directory)'
    else:
        logging.error("Invalid browser specified.")
        sys.exit(1)


    initial_extensions, initial_status = get_extensions_status(extensions_dir)
    if initial_status != "read" or initial_extensions is None:
        logging.error(
            f"Coverage at startup: extensions directory {extensions_dir} could not be read "
            f"({initial_status}); it is not an empty directory. Monitors nothing; exiting."
        )
        sys.exit(1)
    previous_extensions = set(initial_extensions)

    logging.info(
        f"Coverage at startup: extensions directory {extensions_dir} read; "
        f"{len(previous_extensions)} extension state(s) found."
    )
    logging.info(f"Monitoring {browser_label} extensions directory: {extensions_dir} every {interval} seconds.")

    try:
        while True:
            current_list, current_status = get_extensions_status(extensions_dir)
            if current_status != "read" or current_list is None:
                logging.warning(
                    f"Coverage this cycle: extensions directory {extensions_dir} could not be read "
                    f"({current_status}); keeping the previous state and not treating it as empty."
                )
                time.sleep(interval)
                continue
            current_extensions = set(current_list)

            added_extensions = current_extensions - previous_extensions
            removed_extensions = previous_extensions - current_extensions

            if added_extensions or removed_extensions:
                logging.info("Extension changes detected!")

                if added_extensions:
                    logging.info(f"Added extensions: {added_extensions}")
                if removed_extensions:
                    logging.info(f"Removed extensions: {removed_extensions}")

                if alert_on_change:
                    if added_extensions:
                        print(f"Alert: Added extensions: {added_extensions}")
                    if removed_extensions:
                        print(f"Alert: Removed extensions: {removed_extensions}")


                if report_file:
                    try:
                        with open(report_file, 'a') as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: Extension changes detected:\n")
                            if added_extensions:
                                f.write(f"  Added: {added_extensions}\n")
                            if removed_extensions:
                                f.write(f"  Removed: {removed_extensions}\n")
                            f.write("\n")
                        logging.info(f"Extension changes written to report file: {report_file}")
                    except IOError as e:
                        logging.error(f"Error writing to report file: {e}")

            previous_extensions = current_extensions
            time.sleep(interval)

    except KeyboardInterrupt:
        logging.info("Monitoring stopped.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # Usage Examples:
    # 1. Monitor Chrome extensions every 60 seconds, reporting changes to chrome_report.txt
    #    python main.py --browser chrome --interval 60 --report chrome_report.txt
    # 2. Monitor Firefox extensions and alert on any changes.
    #    python main.py --browser firefox --alert-on-change
    # 3. Monitor Chrome extensions with a specific extensions directory:
    #    python main.py --browser chrome --extensions_dir "/path/to/chrome/extensions"
    main()